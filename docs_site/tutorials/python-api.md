# Python API Tutorial

This tutorial shows how to use Nancy Brain programmatically through its Python API.

## Installation

```bash
pip install nancy-brain
```

## Basic Usage

### Initializing the RAG Service

```python
from pathlib import Path
from rag_core.service import RAGService

# Initialize the service
rag_service = RAGService(
    embeddings_path=Path("knowledge_base/embeddings"),
    config_path=Path("config/repositories.yml"),
    weights_path=Path("config/weights.yaml")
)
```

### Searching the Knowledge Base

```python
# Basic search
results = rag_service.search("machine learning optimization")

# Search with custom limits
results = rag_service.search(
    query="neural networks",
    limit=10
)

# Print results
for result in results:
    print(f"Score: {result.score:.3f}")
    print(f"Text: {result.text[:200]}...")
    print(f"Source: {result.id}")
    print("---")
```

### Building Knowledge Bases

```python
from scripts.build_knowledge_base import main as build_kb

# Build knowledge base programmatically
build_kb(
    config_file="config/repositories.yml",
    embeddings_path="knowledge_base/embeddings",
    force_update=True
)
```

### Exploring the Knowledge Base

```python
# List available documents
document_tree = rag_service.list_tree(max_depth=3)

for item in document_tree:
    if item.is_directory:
        print(f"📁 {item.path}/")
    else:
        print(f"📄 {item.path}")
```

## Advanced Usage

### Custom Search Configuration

```python
from rag_core.search import Search

# Custom search with dual embedding models
search = Search(
    embeddings_path=Path("knowledge_base/embeddings"),
    dual=True,  # Use both general and code embeddings
    code_model="microsoft/codebert-base"
)

# Search with namespace filtering
results = search.search(
    query="optimization algorithms",
    namespace="microlensing_tools"
)
```

### Working with Weights

```python
from rag_core.registry import ModelWeights

# Load and customize search weights
weights = ModelWeights(Path("config/weights.yaml"))

# Get weights for specific file types
py_weight = weights.get_file_weight(".py")
md_weight = weights.get_file_weight(".md")

print(f"Python files weight: {py_weight}")
print(f"Markdown files weight: {md_weight}")
```

### Store Operations

```python
from rag_core.store import Store

# Initialize store
store = Store(Path("knowledge_base"))

# Get repository information
repos = store.list_repositories()
for repo in repos:
    print(f"Repository: {repo.name}")
    print(f"Path: {repo.path}")
    print(f"Last updated: {repo.last_updated}")
```

## Integration Examples

### Flask Web App

```python
from flask import Flask, request, jsonify
from rag_core.service import RAGService
from pathlib import Path

app = Flask(__name__)

# Initialize Nancy Brain
rag_service = RAGService(
    embeddings_path=Path("knowledge_base/embeddings"),
    config_path=Path("config/repositories.yml"),
    weights_path=Path("config/weights.yaml")
)

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query', '')
    limit = data.get('limit', 5)
    
    results = rag_service.search(query, limit=limit)
    
    return jsonify([{
        'score': r.score,
        'text': r.text,
        'source': r.id
    } for r in results])

if __name__ == '__main__':
    app.run(debug=True)
```

### Jupyter Notebook Integration

```python
# Cell 1: Setup
from rag_core.service import RAGService
from pathlib import Path
import pandas as pd

rag_service = RAGService(
    embeddings_path=Path("knowledge_base/embeddings"),
    config_path=Path("config/repositories.yml"),
    weights_path=Path("config/weights.yaml")
)

# Cell 2: Interactive Search
query = "deep learning architectures"
results = rag_service.search(query, limit=10)

# Convert to DataFrame for better display
df = pd.DataFrame([{
    'Score': r.score,
    'Source': r.id.split('/')[-1],  # Just filename
    'Preview': r.text[:100] + '...'
} for r in results])

display(df)
```

### Batch Processing

```python
import asyncio
from typing import List
from rag_core.service import RAGService

class BatchProcessor:
    def __init__(self, rag_service: RAGService):
        self.rag_service = rag_service
    
    def process_queries(self, queries: List[str], limit: int = 5):
        """Process multiple queries in batch."""
        results = {}
        
        for query in queries:
            try:
                search_results = self.rag_service.search(query, limit=limit)
                results[query] = search_results
                print(f"✅ Processed: {query}")
            except Exception as e:
                print(f"❌ Error processing {query}: {e}")
                results[query] = []
        
        return results

# Usage
processor = BatchProcessor(rag_service)
queries = [
    "machine learning optimization",
    "neural network architectures",
    "data preprocessing techniques"
]

batch_results = processor.process_queries(queries)
```

## Error Handling

```python
from rag_core.service import RAGService
from rag_core.types import SearchError

try:
    rag_service = RAGService(
        embeddings_path=Path("knowledge_base/embeddings"),
        config_path=Path("config/repositories.yml"),
        weights_path=Path("config/weights.yaml")
    )
    
    results = rag_service.search("your query here")
    
except FileNotFoundError as e:
    print(f"Configuration file not found: {e}")
except SearchError as e:
    print(f"Search error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Performance Tips

### 1. Reuse Service Instances

```python
# ✅ Good: Reuse the service
rag_service = RAGService(...)

for query in many_queries:
    results = rag_service.search(query)
```

### 2. Batch Operations

```python
# ✅ Good: Process multiple queries together
queries = ["query1", "query2", "query3"]
all_results = [rag_service.search(q) for q in queries]
```

### 3. Configure Search Limits

```python
# ✅ Good: Use appropriate limits
results = rag_service.search(query, limit=5)  # Usually sufficient
```

## Next Steps

- Explore the [CLI Commands](../api/cli.md) for command-line usage
- Check out [Core Services API](../api/core.md) for detailed API reference
- See [Research Workflow](./research-workflow.md) for academic use cases
- Review [Claude Desktop Integration](../integrations/claude-desktop.md) for AI assistant setup
