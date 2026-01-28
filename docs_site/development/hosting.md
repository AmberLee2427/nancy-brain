# Documentation Hosting Guide

This guide shows you how to host your Nancy Brain documentation using different platforms. Choose the option that best fits your needs.

## 🚀 Quick Start: GitHub Pages (Recommended)

**Best for**: Open source projects, simple setup, free hosting

### 1. Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** → **Pages** 
3. Under **Source**, select **GitHub Actions**
4. That's it! The workflow will run automatically.

### 2. Access Your Docs

After the workflow completes, your docs will be available at:
```
https://your-username.github.io/nancy-brain/
```

### 3. Custom Domain (Optional)

Add a `CNAME` file to enable custom domains:

```bash
echo "docs.yourdomain.com" > docs_site/CNAME
git add docs_site/CNAME
git commit -m "Add custom domain"
git push
```

## 📚 Read the Docs (Like Sphinx)

**Best for**: Projects familiar with RTD, advanced features, free for open source

### 1. Connect Your Repository

1. Go to [readthedocs.org](https://readthedocs.org)
2. Sign in with GitHub
3. Click **Import a Project**
4. Select your `nancy-brain` repository

### 2. Configure Build

The `.readthedocs.yaml` file is already configured! RTD will:
- Use Python 3.12
- Install Nancy Brain with docs dependencies
- Build with MkDocs
- Deploy automatically on push

### 3. Access Your Docs

Your docs will be available at:
```
https://nancy-brain.readthedocs.io/
```

### RTD vs GitHub Pages

| Feature | Read the Docs | GitHub Pages |
|---------|---------------|--------------|
| **Cost** | Free (open source) | Free |
| **Setup** | Web interface | GitHub Actions |
| **Custom domains** | ✅ Easy | ✅ Manual |
| **Analytics** | ✅ Built-in | Requires setup |
| **PDF exports** | ✅ Built-in | ❌ None |
| **Versioning** | ✅ Automatic | Manual |
| **Build time** | Slower | Faster |

## 🌐 Netlify (Modern Alternative)

**Best for**: Teams, advanced features, generous free tier

### 1. Connect Repository

1. Go to [netlify.com](https://netlify.com)
2. Click **New site from Git**
3. Connect your GitHub account
4. Select your repository

### 2. Configure Build

Netlify will automatically detect the `netlify.toml` configuration:
- Build command: `pip install -e '.[docs]' && mkdocs build`
- Publish directory: `site/`
- Python version: 3.12

### 3. Features You Get

- **Deploy previews** for pull requests
- **Form handling** (if you add contact forms)
- **Edge functions** for dynamic content
- **Analytics** built-in

## ⚡ Vercel (Alternative)

**Best for**: Next.js familiarity, edge performance

### Quick Setup

1. Install Vercel CLI: `npm i -g vercel`
2. In your repository: `vercel --prod`
3. Follow the prompts

### Vercel Configuration

Create `vercel.json`:

```json
{
  "buildCommand": "pip install -e '.[docs]' && mkdocs build",
  "outputDirectory": "site",
  "installCommand": "pip install -e '.[docs]'",
  "framework": null
}
```

## 🔧 Local Development Workflow

### Standard Development

```bash
# Start development server
mkdocs serve --dev-addr localhost:8001

# Build for production
mkdocs build

# Deploy to GitHub Pages (manual)
mkdocs gh-deploy
```

### Advanced Development

```bash
# Watch for changes with auto-reload
mkdocs serve --dev-addr localhost:8001 --livereload

# Build with strict mode (catch all warnings)
mkdocs build --strict

# Clean build
rm -rf site/ && mkdocs build
```

## 🎯 Recommended Setup

For most projects, I recommend this progression:

### Phase 1: GitHub Pages
- **Start here**: Free, simple, automatic
- Set up the GitHub Actions workflow
- Perfect for getting docs online quickly

### Phase 2: Read the Docs (if needed)
- **Upgrade to**: Better analytics, PDF exports, versioning
- Keep GitHub Pages as backup
- Familiar if you've used Sphinx + RTD

### Phase 3: Custom Domain
- **When ready**: Professional appearance
- Works with any hosting option
- Set up SSL automatically

## 🚀 Automation Examples

### Multi-environment Deployment

Deploy to multiple platforms:

```yaml
# .github/workflows/docs-multi.yml
name: Deploy to Multiple Platforms

on:
  push:
    branches: [main]

jobs:
  deploy-github:
    # ... GitHub Pages deployment
    
  deploy-netlify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - # ... build steps
      - name: Deploy to Netlify
        uses: nwtgck/actions-netlify@v1.2
        with:
          publish-dir: './site'
```

### Documentation Staging

Test docs before going live:

```yaml
# Deploy PR previews
on:
  pull_request:
    branches: [main]

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - # ... build steps
      - name: Deploy PR preview
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
          destination_dir: pr-${{ github.event.number }}
```

## 📊 Monitoring & Analytics

### GitHub Pages + Google Analytics

Add to `mkdocs.yml`:

```yaml
extra:
  analytics:
    provider: google
    property: G-XXXXXXXXXX
```

### Read the Docs Analytics

Built-in analytics at:
```
https://readthedocs.org/projects/nancy-brain/analytics/
```

### Custom Analytics

For Netlify/Vercel, add tracking code to `docs_site/overrides/main.html`:

```html
{% extends "base.html" %}

{% block analytics %}
  <!-- Your analytics code -->
{% endblock %}
```

## 🔍 SEO Optimization

### Site Configuration

Update `mkdocs.yml`:

```yaml
site_name: Nancy Brain
site_description: Turn GitHub repos into AI-searchable knowledge bases
site_url: https://nancy-brain.readthedocs.io/
site_author: Your Name

extra:
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/AmberLee2427/nancy-brain
    - icon: fontawesome/brands/python
      link: https://pypi.org/project/nancy-brain/
```

### Meta Tags

MkDocs Material automatically generates:
- Open Graph tags
- Twitter cards  
- JSON-LD structured data
- Proper meta descriptions

## 🛠️ Troubleshooting

### Build Fails

**Check Python dependencies**:
```bash
pip install -e ".[docs]"
mkdocs build --strict
```

**Check for broken links**:
```bash
# Install link checker
pip install mkdocs-linkcheck

# Add to mkdocs.yml
plugins:
  - linkcheck
```

### Slow Builds

**Optimize images**:
```bash
# Install optimization plugin
pip install mkdocs-optimize

# Add to mkdocs.yml
plugins:
  - optimize
```

**Cache dependencies**:
```yaml
# In GitHub Actions
- name: Cache pip
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
```

### Deploy Fails

**Check secrets**:
- GitHub: No secrets needed for GitHub Pages
- Netlify: Connect account in Netlify dashboard
- Read the Docs: Connect GitHub account

**Debug locally**:
```bash
# Test build exactly like CI
pip install -e ".[docs]"
mkdocs build --strict
python -m http.server 8000 --directory site/
```

## 📈 Next Steps

1. **Pick a hosting platform** (GitHub Pages recommended to start)
2. **Set up the workflow** (files already created!)
3. **Test the deployment** by pushing changes
4. **Add custom domain** when ready
5. **Monitor and iterate** based on usage

The documentation is now ready for professional hosting! 🎉
