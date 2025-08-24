# Research Workflow with Nancy Brain

This tutorial walks through using Nancy Brain for academic research, from initial setup to advanced queries. Perfect for researchers who want to build searchable knowledge bases from scientific repositories and papers.

## Overview

Nancy Brain excels at creating searchable knowledge bases from:
- **Scientific code repositories** (Python, R, MATLAB, etc.)
- **Documentation and papers** (Markdown, RST, LaTeX)
- **Research notebooks** (Jupyter, R Markdown)
- **PDF articles and preprints** (arXiv, journal papers)

## Quick Start: Microlensing Research Example

Let's build a knowledge base for microlensing research tools and papers.

### 1. Project Setup

```bash
# Create new research project
nancy-brain init microlensing-research
cd microlensing-research

# Verify structure
ls -la
# config/repositories.yml - for code repositories
# knowledge_base/ - will contain embeddings
```

### 2. Configure Research Repositories

Edit `config/repositories.yml` to include key microlensing tools:

```yaml
# Microlensing analysis tools
microlensing_tools:
  - name: MulensModel
    url: https://github.com/rpoleski/MulensModel.git
  - name: pyLIMA
    url: https://github.com/ebachelet/pyLIMA.git
  - name: VBMicrolensing
    url: https://github.com/valboz/VBMicrolensing.git
  - name: RTModel
    url: https://github.com/AedenElder/RTModel.git

# Data analysis frameworks
analysis_tools:
  - name: astropy
    url: https://github.com/astropy/astropy.git
  - name: scipy
    url: https://github.com/scipy/scipy.git

# Simulation tools
simulation_tools:
  - name: synthpop
    url: https://github.com/synthpop-galaxy/synthpop.git
  - name: PopSyCLE
    url: https://github.com/jluastro/PopSyCLE.git
```

### 3. Add Research Papers

Create `config/articles.yml` for important papers:

```yaml
# Key microlensing papers
foundational_papers:
  - name: "Paczynski 1986 - Gravitational Microlensing"
    url: "https://ui.adsabs.harvard.edu/link_gateway/1986ApJ...304....1P/ADS_PDF"
    description: "Original gravitational microlensing paper"
  
  - name: "Gould 2000 - Microlensing Survey Strategies"
    url: "https://arxiv.org/pdf/astro-ph/0001421.pdf"
    description: "Survey design and optimization strategies"

recent_reviews:
  - name: "Mao 2012 - Microlensing Review"
    url: "https://arxiv.org/pdf/1206.2557.pdf"
    description: "Comprehensive review of microlensing techniques"
    
  - name: "Gaudi 2012 - Exoplanet Microlensing"
    url: "https://arxiv.org/pdf/1002.0332.pdf"
    description: "Microlensing for exoplanet detection"

# Add your own papers
my_research:
  - name: "Your Recent Paper"
    url: "https://arxiv.org/pdf/2301.12345.pdf"
    description: "Brief description of your work"
```

### 4. Build Knowledge Base

```bash
# Build from repositories (takes 5-15 minutes)
nancy-brain build

# Add PDF articles
nancy-brain build --articles-config config/articles.yml

# Check what was indexed
nancy-brain explore --max-entries 20
```

### 5. Start Researching

```bash
# Launch web interface
nancy-brain ui

# Or search from command line
nancy-brain search "binary lens modeling"
nancy-brain search "finite source effects"
nancy-brain search "galactic bulge survey optimization"
```

## Research Workflow Patterns

### Literature Review Workflow

**1. Seed with Core Papers**
```bash
# Add foundational papers to articles.yml
nancy-brain add-article https://arxiv.org/pdf/astro-ph/0001421.pdf "Gould Survey Strategy"
nancy-brain build --articles-config config/articles.yml
```

**2. Explore Related Topics**
```bash
# Search for methodology
nancy-brain search "microlensing event detection algorithms"
nancy-brain search "photometric precision requirements"
nancy-brain search "stellar variability background"

# Browse by category
nancy-brain explore --prefix "foundational_papers"
```

**3. Find Implementation Details**
```bash
# Search for specific techniques
nancy-brain search "finite source effects implementation"
nancy-brain search "binary lens caustic calculation"
nancy-brain search "limb darkening coefficients"
```

### Code Discovery Workflow

**1. Find Relevant Functions**
```bash
# Search for specific capabilities
nancy-brain search "photometric error modeling"
nancy-brain search "event fitting optimization"
nancy-brain search "parallax calculation"
```

**2. Explore Implementation**
```bash
# Browse specific tools
nancy-brain explore --prefix "microlensing_tools/MulensModel"
nancy-brain explore --prefix "microlensing_tools/pyLIMA"

# Search within specific tools
nancy-brain search "MulensModel Event class"
nancy-brain search "pyLIMA fitting methods"
```

**3. Compare Approaches**
```bash
# Compare implementations across tools
nancy-brain search "binary lens solver comparison"
nancy-brain search "optimization algorithms microlensing"
nancy-brain search "numerical precision finite source"
```

### Method Development Workflow

**1. Research Background**
```bash
# Understand current state
nancy-brain search "machine learning microlensing classification"
nancy-brain search "deep learning stellar variability"
nancy-brain search "neural networks time series astronomy"
```

**2. Find Related Implementations**
```bash
# Look for similar approaches
nancy-brain search "CNN light curve analysis"
nancy-brain search "RNN astronomical time series"
nancy-brain search "transformer models astronomy"
```

**3. Identify Gaps and Opportunities**
```bash
# Search for limitations
nancy-brain search "computational bottlenecks microlensing"
nancy-brain search "systematic uncertainties galactic bulge"
nancy-brain search "false positive rejection methods"
```

## Advanced Research Queries

### Cross-Domain Searches

```bash
# Combine multiple concepts
nancy-brain search "Bayesian inference gravitational lensing"
nancy-brain search "MCMC parameter estimation microlensing"
nancy-brain search "Gaussian processes stellar variability"

# Search for interdisciplinary approaches
nancy-brain search "computer vision astronomical surveys"
nancy-brain search "signal processing microlensing detection"
nancy-brain search "statistical methods rare events"
```

### Technical Implementation Queries

```bash
# Performance optimization
nancy-brain search "GPU acceleration astronomy"
nancy-brain search "parallel processing large datasets"
nancy-brain search "memory efficient algorithms"

# Numerical methods
nancy-brain search "root finding algorithms"
nancy-brain search "integration methods precision"
nancy-brain search "numerical stability considerations"

# Data handling
nancy-brain search "large scale data processing"
nancy-brain search "time series data structures"
nancy-brain search "efficient file formats astronomy"
```

### Validation and Testing

```bash
# Find testing approaches
nancy-brain search "unit testing scientific software"
nancy-brain search "validation synthetic data"
nancy-brain search "benchmark datasets microlensing"

# Error analysis
nancy-brain search "uncertainty propagation"
nancy-brain search "systematic error analysis"
nancy-brain search "robustness testing"
```

## Research Documentation Workflow

### 1. Document Methodology Searches

Create a research log with your queries:

```markdown
# Research Log: Machine Learning for Microlensing

## 2025-08-24: Background Research
- nancy-brain search "machine learning microlensing"
  - Found 3 recent papers on CNN approaches
  - MulensModel has preliminary ML modules
  
## 2025-08-24: Implementation Survey  
- nancy-brain search "CNN time series classification astronomy"
  - TensorFlow implementations in astropy ecosystem
  - PyTorch examples in several repositories
```

### 2. Track Useful Document IDs

```bash
# Save important document references
nancy-brain search "tensorflow astronomy" > search-results-ml.txt
nancy-brain explore --prefix "analysis_tools/astropy" > astropy-structure.txt
```

### 3. Export Context for Papers

Use Nancy Brain to gather context for your writing:

```bash
# Get comprehensive background
nancy-brain search "microlensing survey efficiency" --limit 10

# Find specific implementation details
nancy-brain search "pyLIMA optimization algorithms" --limit 5

# Gather comparison data
nancy-brain search "VBMicrolensing vs MulensModel performance"
```

## Collaboration Workflow

### Sharing Knowledge Bases

**1. Export Configuration**
```bash
# Share your repository configuration
cp config/repositories.yml shared-config.yml
cp config/articles.yml shared-articles.yml

# Document your setup
echo "# Research KB Setup" > README.md
echo "Built: $(date)" >> README.md
echo "Repositories: $(wc -l < config/repositories.yml) sources" >> README.md
```

**2. Reproducible Builds**
```bash
# Version your knowledge base
git init
git add config/
git commit -m "Initial knowledge base configuration"

# Others can rebuild
git clone your-repo
nancy-brain build
nancy-brain build --articles-config config/articles.yml
```

### Team Research Queries

**1. Onboarding New Team Members**
```bash
# Essential background
nancy-brain search "microlensing fundamentals"
nancy-brain search "observational strategies"
nancy-brain search "data analysis pipeline"

# Tool orientation
nancy-brain explore --prefix "microlensing_tools" --max-depth 2
nancy-brain search "MulensModel tutorial"
nancy-brain search "pyLIMA getting started"
```

**2. Project Planning**
```bash
# Assess current capabilities
nancy-brain search "existing implementations survey optimization"
nancy-brain search "computational requirements large surveys"

# Identify knowledge gaps
nancy-brain search "unsolved problems microlensing"
nancy-brain search "future survey challenges"
```

## Performance Tips for Large Knowledge Bases

### Efficient Building

```bash
# Build incrementally
nancy-brain build --config config/core-tools.yml
nancy-brain build --config config/extended-tools.yml --force-update

# Separate articles for faster iteration
nancy-brain build --articles-config config/core-papers.yml
nancy-brain build --articles-config config/recent-papers.yml
```

### Targeted Searching

```bash
# Use specific categories
nancy-brain explore --prefix "simulation_tools"
nancy-brain explore --prefix "foundational_papers"

# Limit search depth for overview
nancy-brain explore --max-depth 2 --max-entries 50

# Focus searches with technical terms
nancy-brain search "algorithm implementation" --limit 3
```

### Resource Management

```bash
# Monitor knowledge base size
du -sh knowledge_base/embeddings/

# Clean up if needed
rm -rf knowledge_base/embeddings/
nancy-brain build  # Rebuild fresh
```

## Integration with Research Tools

### Jupyter Notebooks

```python
# Use Nancy Brain from Python
import subprocess
import json

def search_knowledge_base(query, limit=5):
    """Search Nancy Brain from Jupyter"""
    result = subprocess.run([
        'nancy-brain', 'search', query, '--limit', str(limit)
    ], capture_output=True, text=True)
    return result.stdout

# Example usage
background = search_knowledge_base("microlensing detection efficiency")
print(background)
```

### LaTeX Writing

```bash
# Generate context for paper sections
nancy-brain search "microlensing survey design principles" --limit 3 > background.txt
nancy-brain search "computational performance comparison" --limit 5 > methods.txt

# Find specific citations
nancy-brain search "Paczynski 1986" 
nancy-brain search "Gould 2000 survey optimization"
```

### Reference Management

```bash
# Extract paper information
nancy-brain explore --prefix "foundational_papers"
nancy-brain explore --prefix "recent_reviews"

# Find methodological papers
nancy-brain search "statistical methods parameter estimation"
nancy-brain search "Bayesian analysis astronomical data"
```

## Troubleshooting Research Workflows

### No Results for Specific Topics

```bash
# Try broader terms first
nancy-brain search "lensing" instead of "gravitational microlensing parallax"

# Check what's actually indexed
nancy-brain explore --prefix "microlensing_tools" --max-entries 10

# Verify papers were indexed
nancy-brain explore --prefix "foundational_papers"
```

### Finding Implementation Details

```bash
# Look for specific file types
nancy-brain search "python class definition"
nancy-brain search "function documentation"
nancy-brain search "example usage"

# Browse code structure
nancy-brain explore --prefix "microlensing_tools/MulensModel" --max-depth 4
```

### Performance Issues

```bash
# Use more specific queries
nancy-brain search "finite source FSPL" --limit 3
# Instead of: nancy-brain search "finite source effects"

# Limit exploration depth
nancy-brain explore --max-depth 2 --max-entries 20
```

## Next Steps

1. **Expand Your Knowledge Base**: Add more repositories and papers relevant to your research
2. **Customize Weights**: Edit `config/weights.yaml` to prioritize certain file types
3. **Automate Updates**: Set up scripts to regularly rebuild with `--force-update`
4. **Share with Collaborators**: Version control your configuration files
5. **Integrate with Tools**: Use the HTTP API or MCP server for deeper integration

## Further Reading

- [MCP Server Integration](../integrations/vscode-mcp.md) - Use with VS Code and Claude
- [HTTP API Reference](../integrations/http-api.md) - Programmatic access
- [Advanced Configuration](../configuration.md) - Customize weights and settings
- [Troubleshooting](../development/troubleshooting.md) - Common issues and solutions
