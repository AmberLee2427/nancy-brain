# Nancy Brain

Build and operate an MCP-accessible knowledge base from repositories, research
papers, documentation, and notebooks.

!!! info "Looking for the shared microlensing knowledge base?"
    These are the package and self-hosting docs. To connect an AI client to the
    existing Nancy microlensing service, use
    [nancy.rges-pit.com](https://nancy.rges-pit.com/). You do not need to
    install this package or build an index.

## What is Nancy Brain?

Nancy Brain is a powerful tool that helps researchers, developers, and teams create searchable knowledge bases from:

- **Repositories** - Index code, documentation, and READMEs
- **PDF articles** - Process papers, documentation, and reports
- **Semantic retrieval** - Search an indexed corpus and retrieve precise passages
- **MCP and HTTP** - Serve the resulting knowledge base to agents and applications

## Quick start

```bash
# Install
pip install nancy-brain

# Initialize a project
nancy-brain init my-knowledge-base
cd my-knowledge-base

# Edit config/repositories.yml to add your repos
nancy-brain build

# Search your knowledge base
nancy-brain search "machine learning algorithms"
```

## Choose the right path

| Goal | Documentation |
| --- | --- |
| Connect to the hosted microlensing corpus | [Nancy for RGES-PIT](https://nancy.rges-pit.com/) |
| Build your own index | [Quick Start](quick-start.md) |
| Connect a client to your own server | [Integrations](integrations/vscode-mcp.md) |
| Deploy a persistent server | [Self-Hosting Guide](deployment/self-hosted.md) |

## Interfaces

Nancy Brain works seamlessly with your existing tools:

- **MCP** - Streamable HTTP for remote clients and stdio for local clients
- **HTTP API** - Search, retrieve, tree, weighting, and status endpoints
- **CLI** - Build, inspect, and query indexes
- **Web UI** - Administrative inspection and build controls

## Next steps

- [Installation Guide](installation.md) - Get up and running
- [VS Code Integration](integrations/vscode-mcp.md) - Code alongside your knowledge base
- [Research Workflow](tutorials/research-workflow.md) - Academic use cases
- [API Reference](api/cli.md) - Complete CLI documentation

Nancy Brain is named after Nancy Grace Roman, the "Mother of Hubble."
