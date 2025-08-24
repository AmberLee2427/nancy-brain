# PyPI Publishing Setup

## Prerequisites

1. **Create PyPI Account**: https://pypi.org/account/register/
2. **Create API Token**: 
   - Go to https://pypi.org/manage/account/token/
   - Create a new token for the `nancy-brain` project
   - Copy the token (starts with `pypi-`)

## GitHub Setup

1. **Repository Settings** → **Secrets and variables** → **Actions**
2. **Add repository secret**:
   - Name: `PYPI_API_TOKEN`
   - Value: Your PyPI token

## Publishing Environments (Recommended)

For extra security, set up a publishing environment:

1. **Repository Settings** → **Environments**
2. **Create environment**: `release`
3. **Add protection rules**:
   - Required reviewers (optional)
   - Deployment branches: `main` only
4. **Add environment secret**:
   - Name: `PYPI_API_TOKEN`
   - Value: Your PyPI token

## Trusted Publishing (Alternative)

Instead of API tokens, you can use PyPI's trusted publishing:

1. **PyPI Project Settings** → **Publishing**
2. **Add trusted publisher**:
   - Owner: `AmberLee2427`
   - Repository: `nancy-brain`
   - Workflow: `publish.yml`
   - Environment: `release` (if using)

## Release Process

```bash
# Make sure you're on main with clean working directory
git checkout main
git pull origin main

# Release new version (patch/minor/major)
./release.sh patch

# This will:
# 1. Bump version in pyproject.toml and nancy_brain/__init__.py
# 2. Create git commit and tag
# 3. Push to GitHub
# 4. Trigger GitHub Actions to publish to PyPI
```

## Manual Release (if needed)

```bash
# Build package
python -m build

# Check package
twine check dist/*

# Upload to PyPI
twine upload dist/*
```

## Test on TestPyPI first

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ nancy-brain
```
