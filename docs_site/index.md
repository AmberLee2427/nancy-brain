<section class="nancy-hero">
  <div>
    <p class="nancy-kicker">Open-source MCP knowledge infrastructure</p>
    <h1>Build knowledge<br>your tools can<br>actually use.</h1>
    <p class="nancy-hero__lede">
      Turn repositories, papers, documentation, and notebooks into a searchable
      knowledge base for agents, applications, and research teams.
    </p>
    <div class="nancy-actions">
      <a class="nancy-button" href="quick-start/">Build your first index</a>
      <a class="nancy-button nancy-button--ghost" href="deployment/self-hosted/">Deploy a server</a>
    </div>
  </div>
  <img class="nancy-hero__mark" src="nancy-brain.png" alt="Nancy Brain, a bright brain wearing sunglasses">
</section>

<div class="nancy-statline">
  <div class="nancy-stat">
    <strong>Repositories</strong>
    <span>Code, docs, READMEs, and notebooks</span>
  </div>
  <div class="nancy-stat">
    <strong>Research papers</strong>
    <span>PDF extraction with external OCR support</span>
  </div>
  <div class="nancy-stat">
    <strong>Semantic retrieval</strong>
    <span>Search and retrieve precise source passages</span>
  </div>
  <div class="nancy-stat">
    <strong>MCP + HTTP</strong>
    <span>Serve agents, editors, and applications</span>
  </div>
</div>

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

## Choose your route

<div class="nancy-paths">
  <article class="nancy-path">
    <span class="nancy-path__number">01 / BUILD</span>
    <h3>Create an index</h3>
    <p>Install the package, configure source repositories, and build a local knowledge base.</p>
    <a href="quick-start/">Follow the quick start →</a>
  </article>
  <article class="nancy-path">
    <span class="nancy-path__number">02 / CONNECT</span>
    <h3>Give agents access</h3>
    <p>Connect VS Code, Claude Desktop, Gemini, or another MCP-capable client.</p>
    <a href="integrations/vscode-mcp/">Browse integrations →</a>
  </article>
  <article class="nancy-path">
    <span class="nancy-path__number">03 / OPERATE</span>
    <h3>Run it persistently</h3>
    <p>Deploy the MCP and HTTP service with authentication, monitoring, and an admin UI.</p>
    <a href="deployment/self-hosted/">Read the deployment guide →</a>
  </article>
</div>

<aside class="nancy-hosted">
  <img src="nancy-brain2.png" alt="">
  <div>
    <strong>Here for microlensing research?</strong>
    <p>The shared Nancy service is already built. Connect your client without installing this package.</p>
  </div>
  <a href="https://nancy.rges-pit.com/">Use Nancy for RGES-PIT</a>
</aside>

## Four ways in

| Interface | Best for |
| --- | --- |
| **MCP** | Remote and local agent clients using Streamable HTTP or stdio |
| **HTTP API** | Search, retrieve, tree, weighting, status, and custom applications |
| **CLI** | Building, inspecting, testing, and querying indexes |
| **Admin UI** | Operational inspection and controlled rebuilds |

Start with the [installation guide](installation.md) for prerequisites, use the
[research workflow](tutorials/research-workflow.md) for an end-to-end example,
or go directly to the [CLI reference](api/cli.md).

<p class="nancy-origin">
  Nancy Brain is named for Nancy Grace Roman, the astronomer who helped turn
  ambitious space observatories into working scientific infrastructure.
</p>
