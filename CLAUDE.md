# CLAUDE.md

This file provides **mandatory instructions** to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🌐 CENTRAL DOCUMENTATION

**BEFORE MAKING ANY CHANGES**, read the ecosystem documentation in ldt-data:

```
../ldt-data/docs/ECOSYSTEM.md  - All repos and architecture
../ldt-data/docs/ROADMAP.md    - Phases and priorities
```

Or on GitHub: https://github.com/cnoyes/ldt-data/tree/main/docs

This ensures you understand how this repo fits into the larger LatterDay Tools ecosystem.

---

## Project Overview

**conference-analysis** is a Python NLP toolkit for deep analysis of LDS General Conference talks.

**Features**:
- Web scraping from churchofjesuschrist.org (4,890 talks, 1971-2025)
- Sentence embeddings (sentence-transformers)
- Temporal word/phrase frequency analysis
- Trend discovery (increasing/decreasing terms over decades)
- Topic clustering with K-Means and DBSCAN
- Interactive Plotly visualizations

**Tech Stack**: Python, sentence-transformers, pandas, plotly, scikit-learn

**Relationship to ldt-conference**:
- This repo = NLP analysis engine (command line / Jupyter)
- ldt-conference = Web UI that displays results
- Future work will connect them via ldt-data exports

---

## Key Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Scrape talks (first time)
python -m conference_analysis.scraper

# Run analysis in Jupyter
jupyter notebook notebooks/

# Run trend analysis
python -c "from conference_analysis import trend_analysis; ..."
```

---

## Architecture

```
src/conference_analysis/
├── scraper.py           # Web scraping from Church website
├── embeddings.py        # Sentence embeddings and semantic search
├── temporal_analysis.py # Word frequency over time
├── trend_analysis.py    # Systematic trend discovery
└── example.py           # Usage examples

notebooks/
├── 01_exploration.ipynb     # Interactive tutorial
└── 02_trend_analysis.ipynb  # Comprehensive trend analysis

data/
├── raw/talks.csv            # Scraped talks (gitignored)
└── processed/embeddings*.pkl # Cached embeddings (gitignored)
```

---

## Key Capabilities

### Embeddings (embeddings.py)
```python
from conference_analysis.embeddings import EmbeddingsAnalyzer
analyzer = EmbeddingsAnalyzer()
results = analyzer.semantic_search("faith during trials", top_k=10)
```

### Temporal Analysis (temporal_analysis.py)
```python
from conference_analysis.temporal_analysis import TemporalAnalyzer
analyzer = TemporalAnalyzer()
analyzer.plot_word_frequency("repentance", by="decade")
```

### Trend Analysis (trend_analysis.py)
```python
from conference_analysis.trend_analysis import TrendAnalyzer
analyzer = TrendAnalyzer()
increasing = analyzer.find_increasing_words(top_n=20)
```

---

## Related Repos

- **ldt-data** - Central documentation hub; will receive exports from this repo
- **ldt-conference** - Web UI that will display analysis results
