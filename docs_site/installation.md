# Installation

## Requirements

- Python 3.12 or higher
- 4GB+ RAM (for embedding models)
- Git (for cloning repositories)

## Install from PyPI

The default install is the **core runtime**. It is designed to run on CPU-only
machines and does not require GPU OCR dependencies.

```bash
pip install nancy-brain
```

This is the recommended install for:

- local development on laptops and desktops
- MCP hosts
- CPU-only servers
- scoped rebuilds that consume cached OCR artifacts

## Verify Installation

```bash
nancy-brain --version
nancy-brain --help
```

## Optional OCR Worker Runtime

PDF OCR runs best as a separate worker env or container.

### CPU OCR Worker

```bash
pip install "nancy-brain[ocr]"
```

### GPU OCR Worker

```bash
pip install "nancy-brain[ocr-gpu]"
```

Use a dedicated env or container for the OCR worker if you plan to run DeepSeek
or Nougat. The OCR runtime is intentionally kept separate from the main
`txtai`-based indexing env.

Typical worker deployments:

- separate conda env on the same machine
- GPU cluster node
- Apptainer/Singularity image on HPC

## Development Setup

If you want to contribute or run from source:

```bash
# Clone the repository
git clone https://github.com/AmberLee2427/nancy-brain.git
cd nancy-brain

# Install the core development stack
pip install -e ".[dev,docs]"

# Optional OCR worker envs should be installed separately
pip install -e ".[dev]"      # Development tools only
pip install -e ".[docs]"     # Documentation tools only  

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

**"OCR worker dependency conflicts"**
- Keep OCR in a separate env or container
- Do not force the main `txtai` env to use the OCR worker's `transformers` stack
- Build from cache on the main host with `nancy-brain build --use-cached-ocr-only`

**"Git clone failed"**
- Check internet connection
- Verify repository URLs in config
- Ensure Git is installed and accessible

### Getting Help

- Check our [GitHub Issues](https://github.com/AmberLee2427/nancy-brain/issues)
- Join the discussion in [GitHub Discussions](https://github.com/AmberLee2427/nancy-brain/discussions)
- See [troubleshooting guide](development/troubleshooting.md) for common solutions
