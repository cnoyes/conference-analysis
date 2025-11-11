# conference-analysis

General Conference topic analysis with temporal trends and NLP embeddings

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

## Usage

```python
# Add usage examples here
```

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
├── src/                    # Source code
│   └── conference-analysis/       # Main package
│       └── __init__.py
├── tests/                  # Test files
│   └── test_example.py
├── data/                   # Data files
│   ├── raw/                # Raw data (not committed)
│   └── processed/          # Processed data (not committed)
├── notebooks/              # Jupyter notebooks (optional)
├── scripts/                # Utility scripts
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Development dependencies
├── pyproject.toml          # Project configuration
└── README.md               # This file
```

## License

MIT
