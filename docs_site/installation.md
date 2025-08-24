# Installation

## Requirements

- Python 3.10 or higher
- 4GB+ RAM (for embedding models)
- Git (for cloning repositories)

## Install from PyPI

```bash
pip install nancy-brain
```

## Verify Installation

```bash
nancy-brain --version
nancy-brain --help
```

## Development Setup

If you want to contribute or run from source:

```bash
# Clone the repository
git clone https://github.com/AmberLee2427/nancy-brain.git
cd nancy-brain

# Install in development mode with all optional dependencies
pip install -e ".[dev,docs,pdf]"

# Or install specific sets of dependencies
pip install -e ".[dev]"      # Development tools only
pip install -e ".[docs]"     # Documentation tools only  
pip install -e ".[pdf]"      # PDF processing only

# Run tests
pytest
```

## Troubleshooting

### Common Issues

**"Command not found: nancy-brain"**
- Make sure your Python PATH includes pip-installed scripts
- Try `python -m nancy_brain.cli` instead

**"CUDA out of memory"**
- Use CPU-only mode: set `CUDA_VISIBLE_DEVICES=""`
- Reduce batch size in configuration

**"Git clone failed"**
- Check internet connection
- Verify repository URLs in config
- Ensure Git is installed and accessible

### Getting Help

- Check our [GitHub Issues](https://github.com/AmberLee2427/nancy-brain/issues)
- Join the discussion in [GitHub Discussions](https://github.com/AmberLee2427/nancy-brain/discussions)
- See [troubleshooting guide](development/troubleshooting.md) for common solutions
