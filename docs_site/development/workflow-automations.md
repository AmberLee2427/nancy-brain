# Workflow Automations

This page documents all the automated workflows and release processes we've set up. **Don't lose these!**

## PyPI Release Automation

### Setup (Already Configured)

We're using **GitHub Actions with Trusted Publishing** - no API tokens needed!

1. **PyPI Trusted Publisher Setup**:
   - Owner: `AmberLee2427` 
   - Repository: `nancy-brain`
   - Workflow: `publish.yml`
   - Environment: `release`

2. **GitHub Actions Workflow**: `.github/workflows/publish.yml`
   - Triggers on git tags (`v*`)
   - Builds package with Python `build`
   - Publishes to PyPI using trusted publishing
   - Runs on `ubuntu-latest` with Python 3.12

### Release Process

```bash
# 1. Make sure you're on main with clean working directory
cd /Users/malpas.1/Code/slack-bot/src/nancy-brain
git checkout main
git pull origin main

# 2. Activate the right environment
mamba activate nancy-brain

# 3. Create release (patch/minor/major)
./release.sh patch
```

**What `release.sh` does:**
1. Uses `bump-my-version` to increment version in `pyproject.toml` and `nancy_brain/__init__.py`
2. Creates git commit with version bump
3. Creates git tag (e.g., `v0.1.3`)
4. Pushes commit and tag to GitHub
5. GitHub Actions automatically publishes to PyPI

### Version History

- **v0.1.1** - Initial PyPI release
- **v0.1.2** - Fixed CLI path resolution for packaged installations
- **v0.1.3** - Fixed embeddings path consistency between build and search commands

### Troubleshooting Releases

**`bump-my-version: command not found`**
```bash
mamba activate nancy-brain
pip install bump-my-version
```

**Release fails to push to GitHub**
```bash
# Check git remote and authentication
git remote -v
git status
```

**GitHub Actions fails**
```bash
# Check the actions tab: https://github.com/AmberLee2427/nancy-brain/actions
# Common issues:
# - Trusted publishing configuration
# - Workflow file syntax
# - Python version compatibility
```

## Documentation Build Automation

### Setup (Current)

We're using **MkDocs Material** with auto-deploy capabilities.

**Local Development:**
```bash
# 1. Activate environment and install docs dependencies
mamba activate nancy-brain
pip install ".[docs]"

# 2. Start development server
python -m mkdocs serve --config-file mkdocs.yml --dev-addr localhost:8001

# 3. Preview at http://localhost:8001
```

### Future: Read the Docs Integration

**TODO**: Set up automatic documentation deployment:

1. **Connect Read the Docs**:
   - Link GitHub repository
   - Configure webhook for auto-builds
   - Set Python version to 3.12+

2. **GitHub Actions for Docs** (alternative):
   ```yaml
   # .github/workflows/docs.yml
   name: Deploy Documentation
   on:
     push:
       branches: [main]
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Setup Python
           uses: actions/setup-python@v4
           with:
             python-version: '3.12'
         - name: Install dependencies
           run: pip install ".[docs]"
         - name: Deploy docs
           run: mkdocs gh-deploy --force
   ```

## Testing Automation

### Current CI/CD (Already Working)

**GitHub Actions**: `.github/workflows/test.yml`
- Runs on push and PR
- Tests Python 3.12
- Runs `pytest` with coverage
- Checks code formatting with `black`
- Linting with `flake8`

**Test Coverage**: Currently at **67%** (exceeding 60% target)

### Running Tests Locally

```bash
# 1. Install dev dependencies
pip install ".[dev]"

# 2. Run tests with coverage
pytest --cov=nancy_brain --cov-report=html

# 3. Check coverage report
open htmlcov/index.html
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Environment Management

### Development Environments

**Primary Environment**: `nancy-brain`
```bash
# Activate and verify
mamba activate nancy-brain
python -c "import nancy_brain; print(nancy_brain.__version__)"
```

**Testing Environment**: `nancy-test`
```bash
# For testing PyPI releases
mamba activate nancy-test
pip install nancy-brain  # Install from PyPI
nancy-brain --version
```

### Environment Recreation

If environments get corrupted:

```bash
# Remove old environment
mamba env remove -n nancy-brain

# Recreate from project
cd /Users/malpas.1/Code/slack-bot/src/nancy-brain
mamba create -n nancy-brain python=3.12
mamba activate nancy-brain
pip install -e ".[dev,docs]"
```

## Dependency Management

### Core Dependencies

Managed in `pyproject.toml`:
- **Runtime**: `txtai`, `fastapi`, `click`, `streamlit`, etc.
- **Development**: `pytest`, `black`, `flake8`, `pre-commit`
- **Documentation**: `mkdocs-material`, `mkdocstrings`
- **PDF Processing**: `tika`, `PyPDF2`, `pdfplumber` (optional)

### Dependency Updates

```bash
# Check for outdated packages
pip list --outdated

# Update specific package
pip install --upgrade package-name

# Update all dev dependencies
pip install --upgrade ".[dev]"
```

## Monitoring & Health Checks

### Package Health

```bash
# Check package can be imported
python -c "import nancy_brain; print('✅ Import successful')"

# Test CLI
nancy-brain --version
nancy-brain --help

# Test web UI
nancy-brain ui --help
```

### Build Health

```bash
# Test knowledge base build
cd /tmp && mkdir test-kb && cd test-kb
nancy-brain init test-project
cd test-project
# Add minimal config and test build
```

## Backup & Recovery

### Important Files to Backup

- **Configuration**: `config/*.yml`, `config/*.yaml`
- **Custom Code**: Any local modifications to scripts
- **Documentation**: The `docs/` folder content
- **Environments**: Export conda environment specs

```bash
# Export environment
mamba env export -n nancy-brain > environment.yml

# Backup important configs
tar -czf nancy-brain-backup.tar.gz config/ docs/ scripts/
```

### Disaster Recovery

If everything breaks:

1. **Fresh Clone**:
   ```bash
   git clone https://github.com/AmberLee2427/nancy-brain.git
   cd nancy-brain
   ```

2. **Environment Setup**:
   ```bash
   mamba create -n nancy-brain python=3.12
   mamba activate nancy-brain
   pip install -e ".[dev,docs]"
   ```

3. **Verify Installation**:
   ```bash
   pytest -q
   nancy-brain --version
   python -m mkdocs serve
   ```

## Useful Commands Reference

```bash
# Release workflow
mamba activate nancy-brain
./release.sh patch

# Documentation workflow  
python -m mkdocs serve --dev-addr localhost:8001

# Testing workflow
pytest --cov=nancy_brain

# Environment check
python -c "import nancy_brain, txtai, fastapi; print('✅ All good')"

# Package verification
nancy-brain init test && cd test && nancy-brain build
```

---

*Last updated: August 24, 2025 - Document these workflows so we don't forget the automation magic!*
