"""Nancy Brain Web UI - Simple admin interface for knowledge base management."""

import asyncio
from pathlib import Path
from typing import Optional

import streamlit as st
import yaml
import subprocess
import sys
import os

# Add package root to path
package_root = Path(__file__).parent.parent
sys.path.insert(0, str(package_root))

from rag_core.service import RAGService

st.set_page_config(
    page_title="Nancy Brain Admin",
    page_icon="🧠",
    layout="wide"
)

# Initialize session state
if 'search_results' not in st.session_state:
    st.session_state.search_results = []

def load_config(config_path: str = "config/repositories.yml"):
    """Load repository configuration."""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}

def save_config(config: dict, config_path: str = "config/repositories.yml"):
    """Save repository configuration."""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

def run_build_command(force_update: bool = False, articles: bool = False):
    """Run the knowledge base build command."""
    cmd = [
        sys.executable, 
        str(package_root / "scripts" / "build_knowledge_base.py"),
        "--config", "config/repositories.yml",
        "--embeddings-path", "knowledge_base/embeddings"
    ]
    
    if articles and Path("config/articles.yml").exists():
        cmd.extend(["--articles-config", "config/articles.yml"])
    
    if force_update:
        cmd.append("--force-update")
    
    return subprocess.run(cmd, capture_output=True, text=True, cwd=package_root)

# Main UI
st.title("🧠 Nancy Brain Admin")
st.markdown("*Turn GitHub repos into AI-searchable knowledge bases*")

# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.selectbox(
    "Choose a page:",
    ["🔍 Search", "📚 Repository Management", "🏗️ Build Knowledge Base", "📊 Status"]
)

if page == "🔍 Search":
    st.header("🔍 Search Knowledge Base")
    
    # Search interface
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Search query:", placeholder="Enter your search query...")
    with col2:
        limit = st.number_input("Results:", min_value=1, max_value=20, value=5)
    
    if st.button("🔍 Search") and query:
        with st.spinner("Searching..."):
            try:
                service = RAGService(
                    embeddings_path=Path("knowledge_base/embeddings"),
                    config_path=Path("config/repositories.yml"),
                    weights_path=Path("config/weights.yaml")
                )
                results = asyncio.run(service.search_docs(query, limit=limit))
                st.session_state.search_results = results
            except Exception as e:
                st.error(f"Search failed: {e}")
    
    # Display results
    if st.session_state.search_results:
        st.subheader("Search Results")
        for i, result in enumerate(st.session_state.search_results, 1):
            with st.expander(f"{i}. {result['id']} (score: {result['score']:.3f})"):
                st.code(result['text'][:500] + "..." if len(result['text']) > 500 else result['text'])

elif page == "📚 Repository Management":
    st.header("📚 Repository Management")
    
    # Load current config
    config = load_config()
    
    # Add new repository
    st.subheader("Add New Repository")
    with st.form("add_repo"):
        col1, col2 = st.columns(2)
        with col1:
            category = st.text_input("Category:", placeholder="e.g., microlensing_tools")
            repo_name = st.text_input("Repository Name:", placeholder="e.g., MulensModel")
        with col2:
            repo_url = st.text_input("Repository URL:", placeholder="https://github.com/user/repo.git")
            description = st.text_input("Description (optional):", placeholder="Brief description")
        
        if st.form_submit_button("➕ Add Repository"):
            if category and repo_name and repo_url:
                if category not in config:
                    config[category] = []
                
                new_repo = {"name": repo_name, "url": repo_url}
                if description:
                    new_repo["description"] = description
                
                config[category].append(new_repo)
                save_config(config)
                st.success(f"Added {repo_name} to {category}")
                st.experimental_rerun()
            else:
                st.error("Please fill in category, name, and URL")
    
    # Display current repositories
    st.subheader("Current Repositories")
    if config:
        for category, repos in config.items():
            st.write(f"**{category}**")
            for repo in repos:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.write(f"• {repo['name']}")
                with col2:
                    st.write(repo.get('description', ''))
                with col3:
                    if st.button("🗑️", key=f"delete_{category}_{repo['name']}"):
                        config[category] = [r for r in config[category] if r['name'] != repo['name']]
                        if not config[category]:
                            del config[category]
                        save_config(config)
                        st.experimental_rerun()
    else:
        st.info("No repositories configured yet.")

elif page == "🏗️ Build Knowledge Base":
    st.header("🏗️ Build Knowledge Base")
    
    col1, col2 = st.columns(2)
    with col1:
        force_update = st.checkbox("Force update existing repositories")
        include_articles = st.checkbox("Include PDF articles (if configured)")
    
    with col2:
        st.info("**Build Options:**\n- Force update: Re-downloads all repositories\n- Include articles: Downloads PDFs from articles.yml")
    
    if st.button("🚀 Start Build"):
        with st.spinner("Building knowledge base... This may take several minutes."):
            result = run_build_command(force_update=force_update, articles=include_articles)
            
            if result.returncode == 0:
                st.success("✅ Knowledge base built successfully!")
                if result.stdout:
                    with st.expander("Build Output"):
                        st.text(result.stdout)
            else:
                st.error("❌ Build failed!")
                if result.stderr:
                    with st.expander("Error Details"):
                        st.text(result.stderr)

elif page == "📊 Status":
    st.header("📊 System Status")
    
    # Check if embeddings exist
    embeddings_path = Path("knowledge_base/embeddings")
    config_path = Path("config/repositories.yml")
    weights_path = Path("config/weights.yaml")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Files")
        st.write("📁 Embeddings:", "✅" if embeddings_path.exists() else "❌")
        st.write("⚙️ Config:", "✅" if config_path.exists() else "❌")
        st.write("⚖️ Weights:", "✅" if weights_path.exists() else "❌")
    
    with col2:
        st.subheader("Knowledge Base")
        if embeddings_path.exists():
            try:
                # Try to count files in embeddings
                index_files = list(embeddings_path.glob("**/*"))
                st.write(f"📄 Index files: {len(index_files)}")
            except:
                st.write("📄 Index files: Unknown")
        else:
            st.write("📄 Index files: No embeddings found")
    
    with col3:
        st.subheader("Configuration")
        config = load_config()
        total_repos = sum(len(repos) for repos in config.values()) if config else 0
        st.write(f"📚 Total repositories: {total_repos}")
        st.write(f"📁 Categories: {len(config) if config else 0}")

# Footer
st.markdown("---")
st.markdown("*Nancy Brain - AI-powered knowledge base for research*")
