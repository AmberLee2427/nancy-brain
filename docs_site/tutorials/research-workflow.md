# Research Workflow with Nancy Brain

Build searchable knowledge bases from scientific repositories, papers, and documentation for academic research.

## Quick Setup

```bash
# Create research project
nancy-brain init my-research
cd my-research

# Configure repositories in config/repositories.yml
research_tools:
  - name: astropy
    url: https://github.com/astropy/astropy.git
  - name: scipy  
    url: https://github.com/scipy/scipy.git

# Add papers in config/articles.yml
key_papers:
  - name: "Important Paper 2024"
    url: "https://arxiv.org/pdf/2401.12345.pdf"
    description: "Key methodology paper"

# Build knowledge base
nancy-brain build
nancy-brain build --articles-config config/articles.yml

# Start searching
nancy-brain ui  # Web interface
nancy-brain search "your research topic"
```

## Core Workflows

### Literature Review
```bash
# Seed with foundational papers
nancy-brain search "fundamental concepts your-field"
nancy-brain explore --prefix "key_papers"

# Find related work  
nancy-brain search "specific methodology"
nancy-brain search "recent developments"
```

### Code Discovery
```bash
# Find implementations
nancy-brain search "algorithm implementation"
nancy-brain explore --prefix "research_tools/astropy"

# Compare approaches
nancy-brain search "performance comparison methods"
nancy-brain search "numerical stability"
```

### Method Development
```bash
# Research background
nancy-brain search "machine learning your-domain"
nancy-brain search "current limitations"

# Find gaps and opportunities
nancy-brain search "computational bottlenecks"
nancy-brain search "unsolved problems"
```

## Advanced Features

### SQL-Like Queries
Nancy Brain supports direct database queries through the txtai backend:

```python
# From scripts or Python integration
results = embeddings.database.search("SELECT id, text FROM txtai WHERE id LIKE 'papers/%'")
results = embeddings.database.search("SELECT * FROM txtai WHERE id = 'specific_document_id'")
```

### Targeted Searches
```bash
# Use prefixes for specific collections
nancy-brain explore --prefix "simulation_tools"
nancy-brain explore --prefix "foundational_papers" 

# Limit scope and depth
nancy-brain explore --max-depth 2 --max-entries 20
nancy-brain search "specific query" --limit 5
```

### Cross-Domain Research
```bash
# Combine concepts
nancy-brain search "machine learning astronomical surveys"
nancy-brain search "Bayesian methods time series"
nancy-brain search "GPU acceleration scientific computing"
```

## Integration Examples

### Jupyter Notebooks
```python
import subprocess

def search_kb(query, limit=5):
    result = subprocess.run([
        'nancy-brain', 'search', query, '--limit', str(limit)
    ], capture_output=True, text=True)
    return result.stdout

# Use in research
background = search_kb("methodology background")
```

### LaTeX Writing
```bash
# Generate context for papers
nancy-brain search "survey methodology" --limit 3 > background.txt
nancy-brain search "implementation details" --limit 5 > methods.txt
```

### Research Documentation
Create research logs tracking your queries and findings:

```markdown
# Research Log
## 2025-01-15: Background Survey
- nancy-brain search "deep learning astronomy" 
  - Found 3 relevant implementations
  - TensorFlow examples in astropy ecosystem
```

## Performance & Collaboration

### Efficient Builds
```bash
# Incremental updates
nancy-brain build --config config/core-tools.yml
nancy-brain build --articles-config config/papers.yml

# Monitor size
du -sh knowledge_base/embeddings/
```

### Team Sharing
```bash
# Version control configurations
git add config/
git commit -m "Research KB configuration"

# Reproducible builds
git clone shared-config-repo
nancy-brain build
```

### Troubleshooting
```bash
# No results? Try broader terms
nancy-brain search "general-topic" # before "very-specific-implementation"

# Check what's indexed
nancy-brain explore --max-entries 10

# Performance issues? Use targeted queries
nancy-brain search "specific-term" --limit 3
nancy-brain explore --max-depth 2
```

## Next Steps

1. **Expand**: Add domain-specific repositories and papers
2. **Customize**: Edit `config/weights.yaml` for file type priorities  
3. **Automate**: Script regular updates with `--force-update`
4. **Integrate**: Use MCP server or HTTP API for deeper tool integration

See [MCP Integration](../integrations/vscode-mcp.md), [HTTP API](../integrations/http-api.md), and [Advanced Configuration](../configuration.md) for more details.
