"""CLI: python -m conference_analysis.insights <cmd>. Run order is in the README."""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="insights", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scrape", help="fetch API pages into the cache, then rebuild corpus.db")
    sub.add_parser("ingest-scribe", help="load the provisional 2026-10 transcripts")
    sub.add_parser("corpus-check", help="reconcile against legacy index -> docs/CORPUS_CHECK.md")
    sub.add_parser("index", help="build n-gram, quote and scripture indexes")
    p = sub.add_parser("topics", help="fit the frozen topic model / assign paragraphs to it")
    p.add_argument("action", choices=["fit", "assign"])
    p = sub.add_parser("signals", help="compute every signal for a conference")
    p.add_argument("conf")
    p = sub.add_parser("report", help="write reports/<conf>.html")
    p.add_argument("conf")
    p = sub.add_parser("phrase", help="history of any phrase")
    p.add_argument("text")
    p = sub.add_parser("quote", help="lineage of a quote")
    p.add_argument("text")
    args = parser.parse_args(argv)

    if args.cmd == "scrape":
        from .build import build
        from .fetch import fetch_all
        fetch_all()
        build()
    elif args.cmd == "ingest-scribe":
        from .scribe import ingest
        ingest()
    elif args.cmd == "corpus-check":
        from .check import corpus_check
        corpus_check()
    elif args.cmd == "index":
        from .ngrams import build_index
        from .quotes import build_quotes
        build_index()
        build_quotes()
    elif args.cmd == "topics":
        from . import topics
        topics.fit() if args.action == "fit" else topics.assign()
    elif args.cmd == "signals":
        from .signals import print_signals
        print_signals(args.conf)
    elif args.cmd == "report":
        from .report import write_report
        write_report(args.conf)
    elif args.cmd == "phrase":
        from .ngrams import print_phrase
        print_phrase(args.text)
    elif args.cmd == "quote":
        from .quotes import print_quote
        print_quote(args.text)


if __name__ == "__main__":
    sys.exit(main())
