#!/usr/bin/env python3
"""Nancy Brain CLI interface."""

import click
import os
import sys
import subprocess
import yaml
from pathlib import Path

# Add the package root to sys.path to handle relative imports
package_root = Path(__file__).parent.parent
sys.path.insert(0, str(package_root))

from rag_core.service import RAGService

# Get version from package
try:
    from nancy_brain import __version__
except ImportError:
    __version__ = "unknown"


@click.group()
@click.version_option(version=__version__)
def cli():
    """Nancy Brain - Turn GitHub repos into AI-searchable knowledge bases."""
    pass


@cli.command()
@click.argument("project_name")
def init(project_name):
    """Initialize a new Nancy Brain project."""
    project_path = Path(project_name)
    project_path.mkdir(exist_ok=True)

    # Create basic config structure
    config_dir = project_path / "config"
    config_dir.mkdir(exist_ok=True)

    # Basic repositories.yml
    repos_config = config_dir / "repositories.yml"
    repos_config.write_text(
        """# Add your repositories here
# example_tools:
#   - name: example-repo
#     url: https://github.com/org/example-repo.git
"""
    )

    click.echo(f"✅ Initialized Nancy Brain project in {project_name}/")
    click.echo(f"📝 Edit {repos_config} to add repositories")
    click.echo("🏗️  Run 'nancy-brain build' to create the knowledge base")


@cli.command()
@click.option("--config", default="config/repositories.yml", help="Repository config file")
@click.option("--articles-config", help="PDF articles config file")
@click.option(
    "--embeddings-path",
    default="knowledge_base/embeddings",
    help="Embeddings output path",
)
@click.option("--force-update", is_flag=True, help="Force update all repositories")
def build(config, articles_config, embeddings_path, force_update):
    """Build the knowledge base from configured repositories."""
    click.echo("🏗️  Building knowledge base...")

    # Convert paths to absolute paths relative to current working directory
    config_path = Path.cwd() / config
    embeddings_path = Path.cwd() / embeddings_path

    # Build command arguments
    cmd = [
        sys.executable,
        str(package_root / "scripts" / "build_knowledge_base.py"),
        "--config",
        str(config_path),
        "--embeddings-path",
        str(embeddings_path),
    ]
    if articles_config:
        articles_config_path = Path.cwd() / articles_config
        cmd.extend(["--articles-config", str(articles_config_path)])
    if force_update:
        cmd.append("--force-update")

    # Run the build script from the package directory
    try:
        result = subprocess.run(cmd, check=True)
        click.echo("✅ Knowledge base built successfully!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Build failed with exit code {e.returncode}")
        sys.exit(e.returncode)


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
def serve(host, port):
    """Start the HTTP API server."""
    try:
        import uvicorn
    except ImportError:
        click.echo("❌ uvicorn not installed. Install with: pip install uvicorn")
        return

    click.echo(f"🚀 Starting Nancy Brain server on {host}:{port}")

    # Add package root to Python path for imports
    sys.path.insert(0, str(package_root))

    # Use the app from the package
    uvicorn.run("connectors.http_api.app:app", host=host, port=port, reload=False)


@cli.command()
@click.argument("query")
@click.option("--limit", default=5, help="Number of results")
@click.option("--embeddings-path", default="knowledge_base/embeddings", help="Embeddings path")
@click.option("--config", default="config/repositories.yml", help="Config path")
@click.option("--weights", default="config/weights.yaml", help="Weights path")
def search(query, limit, embeddings_path, config, weights):
    """Search the knowledge base."""
    import asyncio

    async def do_search():
        # Convert paths to absolute paths relative to current working directory
        embeddings_path_abs = Path.cwd() / embeddings_path
        config_path_abs = Path.cwd() / config
        weights_path_abs = Path.cwd() / weights

        # Initialize service with proper paths
        service = RAGService(
            embeddings_path=embeddings_path_abs,
            config_path=config_path_abs,
            weights_path=weights_path_abs,
        )
        results = await service.search_docs(query, limit=limit)

        if not results:
            click.echo("No results found.")
            return

        for i, result in enumerate(results, 1):
            click.echo(f"\n{i}. {result['id']} (score: {result['score']:.3f})")
            click.echo(f"   {result['text'][:200]}...")

    # Run the async search
    try:
        asyncio.run(do_search())
    except Exception as e:
        click.echo(f"❌ Search failed: {e}")
        sys.exit(1)


@cli.command()
@click.option("--port", default=8501, help="Port to run Streamlit on")
def ui(port):
    """Launch the web admin interface."""
    try:
        import streamlit
    except ImportError:
        click.echo("❌ Streamlit not installed. Install with: pip install streamlit")
        return

    ui_script = package_root / "nancy_brain" / "admin_ui.py"
    click.echo(f"🌐 Starting Nancy Brain Admin UI on port {port}")
    click.echo(f"🔗 Open http://localhost:{port} in your browser")

    # Use subprocess to run streamlit
    cmd = [
        "streamlit",
        "run",
        str(ui_script),
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to start Streamlit: {e}")
    except FileNotFoundError:
        click.echo("❌ Streamlit command not found. Try: pip install streamlit")


@cli.command()
@click.argument("repo_url")
@click.option("--category", default="tools", help="Category to add repo to")
def add_repo(repo_url, category):
    """Add a repository to the configuration."""
    config_file = Path("config/repositories.yml")
    if not config_file.exists():
        click.echo("❌ No config/repositories.yml found. Run 'nancy-brain init' first.")
        return

    # Parse repo name from URL
    repo_name = repo_url.split("/")[-1].replace(".git", "")

    # Load existing config
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        click.echo(f"❌ Error reading {config_file}: {e}")
        return

    # Add category if it doesn't exist
    if category not in config:
        config[category] = []

    # Create repo entry
    repo_entry = {"name": repo_name, "url": repo_url}

    # Check if repo already exists
    existing = [r for r in config[category] if r.get("name") == repo_name]
    if existing:
        click.echo(f"❌ Repository '{repo_name}' already exists in category '{category}'")
        return

    # Add the new repository
    config[category].append(repo_entry)

    # Write back to file
    try:
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        click.echo(f"✅ Added {repo_name} to {category} category")
        click.echo("📝 Run 'nancy-brain build --force-update' to fetch the new repository")

    except Exception as e:
        click.echo(f"❌ Error writing to {config_file}: {e}")


@cli.command()
@click.argument("article_url")
@click.argument("article_name")
@click.option("--category", default="articles", help="Category to add article to")
@click.option("--description", help="Description of the article")
def add_article(article_url, article_name, category, description):
    """Add a PDF article to the configuration."""
    config_file = Path("config/articles.yml")

    # Create articles config if it doesn't exist
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        articles_config = {}
    else:
        try:
            with open(config_file, "r") as f:
                articles_config = yaml.safe_load(f) or {}
        except Exception as e:
            click.echo(f"❌ Error reading {config_file}: {e}")
            return

    # Add category if it doesn't exist
    if category not in articles_config:
        articles_config[category] = []

    # Create article entry
    article_entry = {"name": article_name, "url": article_url}

    if description:
        article_entry["description"] = description

    # Check if article already exists
    existing = [a for a in articles_config[category] if a.get("name") == article_name]
    if existing:
        click.echo(f"❌ Article '{article_name}' already exists in category '{category}'")
        return

    # Add the new article
    articles_config[category].append(article_entry)

    # Write back to file
    try:
        with open(config_file, "w") as f:
            yaml.dump(articles_config, f, default_flow_style=False, sort_keys=False)

        click.echo(f"✅ Added article '{article_name}' to category '{category}'")
        click.echo(f"📝 Run 'nancy-brain build --articles-config {config_file}' to index the new article")

    except Exception as e:
        click.echo(f"❌ Error writing to {config_file}: {e}")


if __name__ == "__main__":
    cli()
