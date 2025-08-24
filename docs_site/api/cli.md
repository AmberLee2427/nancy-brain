# Command Line Interface

Nancy Brain provides a comprehensive command-line interface for managing your knowledge bases. All commands are automatically documented below.

## Installation

```bash
pip install nancy-brain
```

## CLI Reference

::: mkdocs-click
    :module: nancy_brain.cli
    :command: cli
    :prog_name: nancy-brain
    :depth: 2

## Configuration Files

Nancy Brain uses YAML configuration files:

### repositories.yml
```yaml
# Repository categories and sources
microlensing_tools:
  - name: MulensModel
    url: https://github.com/rpoleski/MulensModel.git
  - name: pyLIMA
    url: https://github.com/ebachelet/pyLIMA.git

general_tools:
  - name: numpy
    url: https://github.com/numpy/numpy.git
```

### articles.yml
```yaml
# PDF articles to index
research_papers:
  - name: "Microlensing Survey Methods"
    url: "https://arxiv.org/pdf/astro-ph/0123456.pdf"
    description: "Comprehensive survey methods review"

reviews:
  - name: "Neural Networks in Astronomy"
    url: "https://example.com/nn-astro.pdf"
```

### weights.yaml
```yaml
# File type weights for search ranking
file_weights:
  ".py": 1.2    # Boost Python files
  ".md": 1.0    # Standard weight for docs
  ".rst": 1.0   # Sphinx documentation
  ".txt": 0.8   # Lower weight for plain text
```

## Tips and Best Practices

### Project Setup
1. Always start with `nancy-brain init project-name`
2. Configure `config/repositories.yml` before building
3. Use meaningful category names for organization

### Building Knowledge Bases
- Use `--force-update` when repositories have been updated
- Large repositories may take time to process
- Monitor disk space for embeddings storage

### Searching Effectively
- Use specific technical terms for better results
- Combine multiple keywords: `"neural networks optimization"`
- Use `--limit` to get more diverse results

### Exploring Content
- Start broad with `nancy-brain explore`
- Use `--prefix` to focus on specific areas
- Adjust `--max-depth` based on repository structure

### Development Workflow
1. `nancy-brain init my-project`
2. Edit `config/repositories.yml`
3. `nancy-brain build`
4. `nancy-brain search "test query"`
5. `nancy-brain ui` for interactive exploration

## Troubleshooting

### Common Issues

**Build fails with permission errors:**
```bash
# Ensure write permissions for embeddings directory
chmod -R 755 knowledge_base/
```

**Search returns no results:**
```bash
# Verify embeddings were built successfully
ls -la knowledge_base/embeddings/
nancy-brain explore --max-entries 5
```

**UI won't start:**
```bash
# Install Streamlit dependency
pip install streamlit
nancy-brain ui
```

**Memory issues during build:**
- Process smaller repositories first
- Use `--articles-config` separately for PDFs
- Monitor system resources during build

For more troubleshooting tips, see [Troubleshooting Guide](../development/troubleshooting.md).
