# CLAUDE.md Template

Copy this template to new repositories and customize the Project Overview section.

---

# CLAUDE.md

This file provides **mandatory instructions** to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ MANDATORY PRACTICES

**READ FIRST**: Before starting any work, read `.claude/BEST_PRACTICES.md` for comprehensive development guidelines.

**You MUST:**
1. ✅ Create feature branches for all non-trivial work (NEVER commit directly to main)
2. ✅ Create GitHub issues before starting features
3. ✅ Use plan mode for features requiring 3+ file changes
4. ✅ Invoke code-reviewer agent before creating PRs
5. ✅ Follow conventional commit format
6. ✅ Write tests for new features
7. ✅ Update documentation for user-facing changes

**Branch naming**: `<type>/<issue-number>-<brief-description>`
**Commit format**: `<type>(<scope>): <subject>` (see BEST_PRACTICES.md)

---

## Project Overview

**General Conference Topic Analysis** - Advanced NLP analysis of LDS General Conference talks (1971-present).

This project goes beyond simple word clouds to provide deep semantic understanding using modern NLP techniques:

- **Web Scraping**: Automated collection of all General Conference talks from churchofjesuschrist.org
- **Temporal Analysis**: Track how words, phrases, and themes change over decades
- **Embeddings-based Analysis**: Use semantic embeddings to understand meaning beyond keywords
- **Topic Discovery**: Automatically discover and cluster recurring themes across 50+ years
- **Semantic Search**: Find talks by concept, not just keyword matching

**Technology Stack**: Python, BeautifulSoup, sentence-transformers, scikit-learn, pandas, plotly

**Based on**: Original R Shiny word cloud application (~/Projects/conference)

## Key Commands

### Development Setup
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download required NLP models
python -c "import nltk; nltk.download('stopwords')"

# Install spaCy model (optional, for advanced NLP)
python -m spacy download en_core_web_sm
```

### Running the Analysis
```bash
# Scrape talks (first time only, ~30-60 minutes)
python src/conference-analysis/scraper.py

# Run interactive notebook
jupyter notebook notebooks/01_exploration.ipynb

# Or run individual modules
python src/conference-analysis/temporal_analysis.py
python src/conference-analysis/embeddings.py
```

### Testing
```bash
pytest tests/
```

## Development Workflow

For this project, always:
- Create feature branches from main
- Write tests before implementation (TDD)
- Run full test suite before creating PRs
- Reference issue numbers in commits and PRs

### Branch Naming
Use descriptive branch names with prefixes:
- `feature/` - New features or enhancements
- `fix/` - Bug fixes
- `refactor/` - Code improvements without behavior changes
- `docs/` - Documentation updates

### Commit Messages
Follow conventional commit format:
```
type(scope): brief description

- Reference issue numbers with #123
- Explain what changed and why
- Keep first line under 72 characters
```

## Architecture

### Key Components
1. **Scraper** (`src/conference-analysis/scraper.py`): Web scraping of General Conference talks
2. **Temporal Analyzer** (`src/conference-analysis/temporal_analysis.py`): Word/phrase frequency tracking over time
3. **Embeddings Analyzer** (`src/conference-analysis/embeddings.py`): Semantic analysis using neural embeddings
4. **Notebooks** (`notebooks/`): Interactive exploration and visualization

### Data Flow
```
ChurchofJesusChrist.org → Scraper → CSV Cache → Analysis Modules → Visualizations
                                         ↓
                                   Embeddings Cache
```

### Important Files
- `data/raw/talks.csv`: Cached talks data (not in git)
- `data/processed/embeddings_*.pkl`: Cached embeddings (not in git)
- `notebooks/01_exploration.ipynb`: Main interactive notebook
- `src/conference-analysis/scraper.py`: Web scraping logic
- `src/conference-analysis/temporal_analysis.py`: Temporal trend analysis
- `src/conference-analysis/embeddings.py`: Semantic embeddings analysis

### Data Storage
```
data/
├── raw/
│   └── talks.csv              # Scraped talks (generated, not in git)
├── processed/
│   ├── embeddings_*.pkl       # Cached embeddings (generated, not in git)
│   └── *.html                 # Generated visualizations
└── public/                    # Any shareable datasets (optional)
```

## Important Configuration

### Embedding Models

The project uses sentence-transformers models for embeddings. You can configure which model to use:

- `'all-MiniLM-L6-v2'` (default): Fast and efficient, good quality (384 dimensions)
- `'all-mpnet-base-v2'`: Slower but higher quality (768 dimensions)
- See [SBERT models](https://www.sbert.net/docs/pretrained_models.html) for more options

### Scraping Configuration

- **Delay between requests**: Default 1.0 second (be respectful to the server)
- **Date range**: Default 1971-04-01 to present
- **Cache file**: `data/raw/talks.csv`

### No Environment Variables Required

This project doesn't require API keys or secrets.

## Common Patterns

### Pattern 1: Incremental Scraping

The scraper automatically detects what's already cached and only fetches new talks:

```python
from conference_analysis.scraper import ConferenceScraper

scraper = ConferenceScraper(cache_file='data/raw/talks.csv')
talks = scraper.update_cache()  # Only fetches new talks
```

### Pattern 2: Cached Embeddings

Embeddings are computationally expensive to generate, so always use caching:

```python
from conference_analysis.embeddings import EmbeddingsAnalyzer

analyzer = EmbeddingsAnalyzer(talks, cache_dir='data/processed')
analyzer.generate_embeddings()  # Fast if cached, slow on first run
```

### Pattern 3: Interactive vs Static Plots

Most plotting functions support both interactive (Plotly) and static (Matplotlib):

```python
# Interactive (for notebooks and web apps)
fig = temporal.plot_word_trends(words, interactive=True)
fig.show()

# Static (for reports and papers)
fig = temporal.plot_word_trends(words, interactive=False)
plt.savefig('output.png')
```

## Troubleshooting

### Common Issues

1. **Issue**: Scraper failing with 404 errors
   **Solution**: Website HTML structure may have changed. Check selector patterns in `scraper.py`:
   - Line 98: `talk_element.find('a', class_='item-U_5Ca')`
   - Line 105: `link.find(class_='subtitle-LKtQp')`
   - Line 153: `soup.select('.body-block p')`

2. **Issue**: Out of memory when generating embeddings
   **Solution**: Reduce batch size or process talks in chunks:
   ```python
   # In embeddings.py, line 75, reduce batch_size from 32 to 16 or 8
   self.embeddings = self.model.encode(texts, batch_size=16)
   ```

3. **Issue**: NLTK stopwords not found
   **Solution**: Download NLTK data:
   ```python
   import nltk
   nltk.download('stopwords')
   ```

4. **Issue**: Jupyter kernel crashes when generating embeddings
   **Solution**: PyTorch may be using too much memory. Use a smaller model:
   ```python
   # Use the lightweight model
   analyzer = EmbeddingsAnalyzer(talks, model_name='all-MiniLM-L6-v2')
   ```

5. **Issue**: Scraping takes too long
   **Solution**: For testing, scrape a smaller date range:
   ```python
   from datetime import date
   talks = scraper.scrape_all(
       start_date=date(2020, 1, 1),
       end_date=date(2024, 12, 31)
   )
   ```
