# General Conference Topic Analysis

Advanced NLP analysis of LDS General Conference talks (1971-present) using temporal analysis and semantic embeddings.

This project goes beyond simple word clouds to provide deep semantic understanding of how topics, themes, and language evolve over 50+ years of General Conference.

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

## Features

### 🕸️ Web Scraping
- Automated scraping of all General Conference talks from churchofjesuschrist.org
- Incremental updates (only fetch new talks)
- Robust caching to avoid re-scraping

### 📊 Temporal Analysis
- Track word and phrase frequency over time
- Compare different time periods (decades, years, conferences)
- Generate word clouds for specific time periods
- Analyze speaker evolution over their ministry

### 🧠 Embeddings-based Semantic Analysis
- **Semantic search**: Find talks by meaning, not just keywords
- **Topic clustering**: Discover natural groupings of talks
- **Similar talk discovery**: Find related content across decades
- **Temporal semantic shifts**: See how discussion of concepts evolves

### 📈 Visualization
- Interactive Plotly visualizations
- Static matplotlib plots for reports
- 2D embeddings visualization (PCA/t-SNE)
- Word clouds and trend lines

## Quick Start

### 1. Setup Environment

```bash
# Clone and enter the repository
cd ~/code/conference-analysis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (this may take a few minutes)
pip install -r requirements.txt

# Download NLP resources
python -c "import nltk; nltk.download('stopwords')"
```

### 2. Run the Interactive Notebook

```bash
jupyter notebook notebooks/01_exploration.ipynb
```

The notebook provides a guided tour through:
- Scraping conference talks
- Temporal analysis examples
- Embeddings concepts and usage
- Interactive visualizations

### 3. Or Use Modules Directly

```python
from conference_analysis.scraper import ConferenceScraper
from conference_analysis.temporal_analysis import TemporalAnalyzer
from conference_analysis.embeddings import EmbeddingsAnalyzer

# Scrape talks
scraper = ConferenceScraper(cache_file='data/raw/talks.csv')
talks = scraper.update_cache()

# Temporal analysis
temporal = TemporalAnalyzer(talks)
fig = temporal.plot_word_trends(['faith', 'hope', 'charity'], time_grouping='decade')
fig.show()

# Semantic search
embeddings = EmbeddingsAnalyzer(talks)
embeddings.generate_embeddings()  # Cached after first run
results = embeddings.semantic_search("overcoming adversity", top_k=10)
print(results[['speaker', 'title', 'similarity']])
```

## Understanding Embeddings

**What are embeddings?**

Embeddings are dense vector representations of text that capture semantic meaning. Each talk becomes a point in high-dimensional space where:
- Similar meanings are close together
- Different meanings are far apart
- Mathematical operations reveal relationships

**Why use embeddings?**

Traditional keyword search:
- Query: "car" → Only finds talks mentioning "car"
- Misses talks about "automobile", "vehicle", "transportation"

Embedding-based search:
- Query: "car" → Finds all semantically related concepts
- Understands that "faith" ≈ "belief" ≈ "trust in God"

**Learn more:**
- [Illustrated Word2Vec](https://jalammar.github.io/illustrated-word2vec/) - Visual introduction
- [Sentence Transformers Documentation](https://www.sbert.net/) - The library we use
- [Hugging Face NLP Course](https://huggingface.co/learn/nlp-course) - Comprehensive NLP learning

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
# Format code with black
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

### Project Structure

```
conference-analysis/
├── src/conference-analysis/
│   ├── scraper.py              # Web scraping module
│   ├── temporal_analysis.py    # Temporal trend analysis
│   └── embeddings.py           # Semantic embeddings analysis
├── notebooks/
│   └── 01_exploration.ipynb    # Interactive tutorial notebook
├── data/
│   ├── raw/                    # Scraped talks (generated, gitignored)
│   ├── processed/              # Cached embeddings (generated, gitignored)
│   └── public/                 # Shareable datasets (optional)
├── tests/                      # Test files
├── requirements.txt            # Python dependencies
└── CLAUDE.md                   # Project-specific instructions for Claude Code
```

## Examples

### Temporal Analysis

```python
# Track how specific words change over time
analyzer = TemporalAnalyzer(talks)

words = ['faith', 'hope', 'charity', 'service']
freq_df = analyzer.word_frequency_over_time(words, time_grouping='decade')

# Plot trends
fig = analyzer.plot_word_trends(words, time_grouping='decade')
fig.show()

# Compare different decades
unique_70s, unique_2020s, common = analyzer.compare_periods(1970, 2020)
print(f"Unique to 1970s: {unique_70s[:10]}")
print(f"Unique to 2020s: {unique_2020s[:10]}")
```

### Semantic Search

```python
# Find talks about a concept
embeddings = EmbeddingsAnalyzer(talks)
embeddings.generate_embeddings()

# Search by meaning, not keywords
results = embeddings.semantic_search("overcoming trials and adversity", top_k=10)
for _, row in results.iterrows():
    print(f"{row['similarity']:.3f} - {row['title']} ({row['speaker']})")
```

### Topic Clustering

```python
# Automatically discover topics
clustered = embeddings.cluster_talks(n_clusters=15)

# Examine a cluster
summary = embeddings.get_cluster_summary(clustered, cluster_id=0)
print(f"Cluster size: {summary['size']}")
print("Representative talks:")
for talk in summary['representative_talks'][:5]:
    print(f"  - {talk['title']} by {talk['speaker']}")
```

### Visualize Semantic Space

```python
# See how talks relate in 2D
fig = embeddings.visualize_embeddings_2d(color_by='decade', sample_size=1000)
fig.show()
```

## Performance Notes

- **First scrape**: ~30-60 minutes (all talks since 1971)
- **Incremental updates**: ~1-2 minutes (only new talks)
- **Embedding generation**: ~5-10 minutes on first run (then cached)
- **Semantic search**: Nearly instant (once embeddings are cached)

## Based On

This project is inspired by the original R Shiny word cloud application in `~/Projects/conference`, but significantly enhanced with:
- Python ecosystem for better NLP libraries
- Semantic embeddings for deeper understanding
- Temporal trend analysis
- Interactive visualizations
- Modular, extensible architecture

## License

MIT
