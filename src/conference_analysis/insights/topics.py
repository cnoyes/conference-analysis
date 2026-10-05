"""Frozen topic model (SPEC F3): embed passages, cluster once, assign forever.

fit    - embed every passage of the official corpus (1971 -> 2026-04) with a local
         sentence-transformers model, cluster BERTopic-style (UMAP -> HDBSCAN), keep each
         topic's centroid in embedding space, extract c-TF-IDF keywords, have `claude -p`
         write labels. Everything lands in data/topics/v1/ and is never refit implicitly.
assign - give every passage (including a new provisional conference) to its nearest
         frozen centroid, or to no topic when nothing is close enough.

A "passage" is one or more consecutive paragraphs of a talk merged up to >= 60 words,
so one-line paragraphs do not become their own noisy data points.
"""
import hashlib
import itertools
import json

import numpy as np

from .config import DATA, TOPICS_DIR
from .db import conf_ordinal, connect
from .lexicon import stopwords
from .llm import ask_json

MODEL = "BAAI/bge-large-en-v1.5"
VERSION = "v1"
FIT_THROUGH = "2026-04"      # the model is fit on conferences up to and including this one
MIN_WORDS = 60               # merge paragraphs until a passage has this many words
MAX_WORDS = 300              # passages are truncated to this many words before embedding
NO_TOPIC_QUANTILE = 0.10     # the loosest 10% of training passages count as "no topic"
EMB_DIR = DATA / "embeddings" / MODEL.split("/")[-1]

SCHEMA = """
DROP TABLE IF EXISTS chunks;
CREATE TABLE chunks (
    chunk_id INTEGER PRIMARY KEY,       -- talk_id * 1000 + sequence
    talk_id INTEGER, first_pos INTEGER, last_pos INTEGER, words INTEGER,
    sha TEXT, text TEXT
);
CREATE INDEX chunks_talk ON chunks(talk_id);
"""
TOPIC_SCHEMA = """
DROP TABLE IF EXISTS chunk_topics;
CREATE TABLE chunk_topics (
    chunk_id INTEGER PRIMARY KEY, talk_id INTEGER,
    topic_id INTEGER,                   -- -1 = no topic
    sim REAL                            -- cosine similarity to the nearest centroid
);
CREATE INDEX chunk_topics_talk ON chunk_topics(talk_id);
"""


def model_dir():
    return TOPICS_DIR / VERSION


def split_passages(paragraphs):
    """[(position, text)] of one talk -> [(first_pos, last_pos, text)], each >= MIN_WORDS words."""
    groups, buf, words = [], [], 0
    for position, text in paragraphs:
        buf.append((position, text))
        words += len(text.split())
        if words >= MIN_WORDS:
            groups.append(buf)
            buf, words = [], 0
    if buf and groups:
        groups[-1] += buf  # a short tail joins the previous passage
    elif buf:
        groups.append(buf)
    return [(g[0][0], g[-1][0], " ".join(t for _, t in g)) for g in groups]


def build_chunks(con):
    """Rebuild the passages table from address paragraphs. Deterministic."""
    con.executescript(SCHEMA)
    rows = con.execute(
        "SELECT p.talk_id, p.position, p.text FROM paragraphs p JOIN talks t USING (talk_id) "
        "WHERE t.kind='address' ORDER BY p.talk_id, p.position")
    out = []
    for talk_id, group in itertools.groupby(rows, key=lambda r: r[0]):
        passages = split_passages([(r[1], r[2]) for r in group])
        for seq, (first, last, text) in enumerate(passages, 1):
            out.append((talk_id * 1000 + seq, talk_id, first, last, len(text.split()),
                        hashlib.sha1(text.encode()).hexdigest(), text))
    con.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?,?)", out)
    con.commit()
    return len(out)


def load_cache():
    """sha -> vector for everything embedded so far."""
    cache = {}
    for part in sorted(EMB_DIR.glob("part-*.npz")):
        data = np.load(part)
        cache.update(zip(data["shas"].tolist(), data["vectors"]))
    return cache


def embed_missing(con, log=print):
    """Embed every passage not yet in the cache. Resumable; retries smaller on GPU OOM."""
    cache = load_cache()
    todo = [(sha, text) for sha, text in con.execute("SELECT DISTINCT sha, text FROM chunks")
            if sha not in cache]
    if not todo:
        return cache
    import torch
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL, device="cuda" if torch.cuda.is_available() else "cpu")
    if torch.cuda.is_available():
        model.half()
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    batch, step = 64, 4096
    log(f"embedding {len(todo)} passages with {MODEL}")
    for start in range(0, len(todo), step):
        part = todo[start:start + step]
        texts = [" ".join(t.split()[:MAX_WORDS]) for _, t in part]
        while True:
            try:
                vectors = model.encode(texts, batch_size=batch, normalize_embeddings=True,
                                       show_progress_bar=False)
                break
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                batch = max(1, batch // 2)
                log(f"GPU out of memory; retrying with batch size {batch}")
        shas = np.array([s for s, _ in part])
        existing = len(list(EMB_DIR.glob("part-*.npz")))
        np.savez(EMB_DIR / f"part-{existing + 1:05d}.npz", shas=shas,
                 vectors=vectors.astype(np.float16))
        cache.update(zip(shas.tolist(), vectors.astype(np.float16)))
        log(f"  {min(start + step, len(todo))}/{len(todo)}")
    return cache


def chunk_matrix(con, cache, where="1=1", args=()):
    """(chunk_ids, talk_ids, texts, float32 matrix) for passages matching a talks filter."""
    rows = con.execute(
        "SELECT k.chunk_id, k.talk_id, k.sha, k.text FROM chunks k JOIN talks t USING (talk_id) "
        f"JOIN conferences c USING (conf_id) WHERE {where} ORDER BY k.chunk_id", args).fetchall()
    X = np.stack([cache[r[2]] for r in rows]).astype(np.float32)
    return [r[0] for r in rows], [r[1] for r in rows], [r[3] for r in rows], X


def ctfidf_terms(texts, labels, n_topics, top=15):
    """Top c-TF-IDF unigrams/bigrams per topic."""
    from sklearn.feature_extraction.text import CountVectorizer
    docs = [[] for _ in range(n_topics)]
    for text, label in zip(texts, labels):
        if label >= 0:
            docs[label].append(text)
    vec = CountVectorizer(stop_words=list(stopwords()), ngram_range=(1, 2), min_df=1,
                          max_features=60000, token_pattern=r"[a-zA-Z][a-zA-Z']+")
    counts = vec.fit_transform([" ".join(d) for d in docs]).toarray().astype(float)
    tf = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
    idf = np.log(1 + counts.sum(axis=1).mean() / np.maximum(counts.sum(axis=0), 1))
    scores = tf * idf
    vocab = np.array(vec.get_feature_names_out())
    return [vocab[np.argsort(-scores[k])[:top]].tolist() for k in range(n_topics)]


def cluster(X, log=print):
    """UMAP -> HDBSCAN labels with 40-120 topics; k-means (k=80) if that cannot be reached."""
    import umap
    from sklearn.cluster import HDBSCAN, KMeans
    low = umap.UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine",
                    random_state=42).fit_transform(X)
    for size in (150, 100, 220, 70, 320):
        labels = HDBSCAN(min_cluster_size=size, min_samples=10).fit_predict(low)
        n = labels.max() + 1
        log(f"HDBSCAN min_cluster_size={size}: {n} topics, {np.mean(labels < 0):.0%} unclustered")
        if 40 <= n <= 120:
            return labels, f"umap+hdbscan(min_cluster_size={size})"
    log("HDBSCAN did not give 40-120 topics; falling back to k-means (k=80)")
    return KMeans(n_clusters=80, n_init=4, random_state=42).fit_predict(X), "kmeans(k=80)"


def nearest(X, centroids):
    sims = X @ centroids.T
    return sims.argmax(axis=1), sims.max(axis=1)


def fit(log=print):
    """Fit and freeze topic model v1. Refuses to overwrite an existing model."""
    out = model_dir()
    if (out / "centroids.npy").exists():
        log(f"{out} already holds a frozen model; delete it by hand to refit")
        if not (out / "labels.json").exists():
            label_topics(log)
        return
    con = connect()
    log(f"{build_chunks(con)} passages")
    cache = embed_missing(con, log)
    ids, _, texts, X = chunk_matrix(con, cache, "c.ordinal <= ? AND t.provisional = 0",
                                    (conf_ordinal(FIT_THROUGH),))
    labels, method = cluster(X, log)
    n = labels.max() + 1
    centroids = np.stack([X[labels == k].mean(axis=0) for k in range(n)])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    topic, sim = nearest(X, centroids)
    threshold = float(np.quantile(sim, NO_TOPIC_QUANTILE))
    topic[sim < threshold] = -1
    terms = ctfidf_terms(texts, topic, n)
    topics = []
    for k in range(n):
        members = np.flatnonzero(topic == k)
        best = members[np.argsort(-sim[members])[:40:8]]  # 5 central but varied passages
        topics.append({"topic_id": k, "size": int(len(members)), "terms": terms[k],
                       "examples": [int(ids[i]) for i in best]})
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "centroids.npy", centroids)
    (out / "topics.json").write_text(json.dumps(topics, indent=1))
    (out / "meta.json").write_text(json.dumps({
        "version": VERSION, "model": MODEL, "method": method, "fit_through": FIT_THROUGH,
        "passages": len(ids), "topics": int(n), "no_topic_threshold": threshold,
        "min_words": MIN_WORDS}, indent=1))
    log(f"froze {n} topics ({method}) in {out}")
    label_topics(log)


def label_topics(log=print):
    """Ask `claude -p` for a label per topic (cached; written once to labels.json)."""
    out = model_dir()
    con = connect()
    topics = json.loads((out / "topics.json").read_text())
    labels = {}
    for start in range(0, len(topics), 10):
        blocks = []
        for t in topics[start:start + 10]:
            examples = [con.execute("SELECT text FROM chunks WHERE chunk_id=?", (c,)).fetchone()
                        for c in t["examples"]]
            sample = "\n".join("  - " + " ".join(e[0].split()[:70]) for e in examples if e)
            blocks.append(f"Topic {t['topic_id']}\nKeywords: {', '.join(t['terms'])}\n"
                          f"Representative passages:\n{sample}")
        prompt = (
            "These are topics found by clustering passages of Latter-day Saint General "
            "Conference talks (1971-2026). For each topic write a short, plain-English label "
            "(2 to 5 words, title case, specific enough to tell it apart from its neighbours, "
            "no jargon). Also set \"junk\": true when the topic is not a subject at all but "
            "boilerplate - greetings, sustaining votes, session logistics, thanks to the choir, "
            "generic testimony closings.\n\n" + "\n\n".join(blocks) +
            "\n\nReply with only a JSON array: "
            "[{\"topic_id\": 0, \"label\": \"...\", \"junk\": false}, ...]")
        for item in ask_json(prompt):
            labels[str(item["topic_id"])] = {"label": item["label"], "junk": bool(item["junk"])}
        log(f"  labelled {min(start + 10, len(topics))}/{len(topics)} topics")
    (out / "labels.json").write_text(json.dumps(labels, indent=1))
    write_topics_doc(log)


def load_model():
    """(centroids, topics list with label/junk merged in, meta)."""
    out = model_dir()
    topics = json.loads((out / "topics.json").read_text())
    labels = json.loads((out / "labels.json").read_text()) if (out / "labels.json").exists() else {}
    for t in topics:
        t.update(labels.get(str(t["topic_id"]), {"label": ", ".join(t["terms"][:3]), "junk": False}))
    return np.load(out / "centroids.npy"), topics, json.loads((out / "meta.json").read_text())


def assign(log=print):
    """Assign every passage in the corpus to the frozen model. Idempotent."""
    con = connect()
    centroids, _, meta = load_model()
    build_chunks(con)
    cache = embed_missing(con, log)
    ids, talk_ids, _, X = chunk_matrix(con, cache)
    topic, sim = nearest(X, centroids)
    topic[sim < meta["no_topic_threshold"]] = -1
    con.executescript(TOPIC_SCHEMA)
    con.executemany("INSERT INTO chunk_topics VALUES (?,?,?,?)",
                    zip(ids, talk_ids, topic.tolist(), [round(float(s), 4) for s in sim]))
    con.commit()
    log(f"assigned {len(ids)} passages; {np.mean(topic < 0):.1%} fit no topic")


def write_topics_doc(log=print):
    """docs/TOPICS.md: every topic of the frozen model with label, size and top terms."""
    from .config import REPO
    _, topics, meta = load_model()
    junk = sum(t["junk"] for t in topics)
    lines = [
        f"# Topic model {meta['version']}", "",
        f"Frozen model fit on conferences 1971-04 through {meta['fit_through']}: "
        f"{meta['passages']:,} passages embedded with `{meta['model']}`, clustered with "
        f"{meta['method']}, each passage then assigned to its nearest topic centroid "
        f"(cosine similarity below {meta['no_topic_threshold']:.3f} = no topic).", "",
        f"{meta['topics']} topics; {junk} are flagged as boilerplate and hidden from reports. "
        "Labels were written by `claude -p` from the terms and five representative passages. "
        "Size = training passages assigned.", "",
        "| ID | Label | Size | Boilerplate | Top terms |", "|---|---|---|---|---|",
    ]
    for t in sorted(topics, key=lambda t: -t["size"]):
        lines.append(f"| {t['topic_id']} | {t['label']} | {t['size']} | "
                     f"{'yes' if t['junk'] else ''} | {', '.join(t['terms'][:10])} |")
    out = REPO / "docs" / "TOPICS.md"
    out.write_text("\n".join(lines) + "\n")
    log(f"wrote {out}")
