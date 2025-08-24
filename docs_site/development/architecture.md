# Architecture Guide

This guide explains how Nancy Brain works internally and how its components interact.

## Overview

Nancy Brain is designed as a modular system for turning GitHub repositories into AI-searchable knowledge bases. The architecture consists of several key components that work together to provide efficient semantic search capabilities.

## System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Interfaces    │    │   Core Services │    │   Data Layer    │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • CLI Commands  │    │ • RAG Service   │    │ • Text Store    │
│ • MCP Server    │───▶│ • Search Engine │───▶│ • Embeddings    │
│ • HTTP API      │    │ • Registry      │    │ • Metadata      │
│ • Web UI        │    │ • Builder       │    │ • Weights       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   External      │
                       │   Sources       │
                       ├─────────────────┤
                       │ • GitHub Repos  │
                       │ • Local Files   │
                       │ • PDFs          │
                       │ • Web Content   │
                       └─────────────────┘
```

## Core Components

### 1. RAG Service (`rag_core/service.py`)

The central orchestrator that coordinates all operations:

- **Search Operations**: Semantic search across the knowledge base
- **Document Retrieval**: Fetch specific document passages
- **Weight Management**: Apply dynamic relevance weights
- **Health Monitoring**: System status and diagnostics

```python
class RAGService:
    def __init__(self, embeddings_path, config_path, weights_path):
        self.search = SearchEngine(embeddings_path, weights_path)
        self.store = TextStore(embeddings_path)
        self.registry = DocumentRegistry(config_path)
```

### 2. Search Engine (`rag_core/search.py`)

Handles semantic search and relevance scoring:

- **Embedding Generation**: Convert text to vector representations
- **Similarity Search**: Find relevant documents using cosine similarity
- **Score Adjustment**: Apply weights and filters to results
- **Caching**: Optimize repeated queries

**Key Features:**
- Multi-model support (sentence-transformers, OpenAI, etc.)
- Dynamic weight application
- Threshold filtering
- Extension-based relevance boosting

### 3. Text Store (`rag_core/store.py`)

Manages document storage and retrieval:

- **Document Indexing**: Store and index text content
- **Line-level Access**: Retrieve specific line ranges
- **Content Hashing**: Track document changes
- **Efficient Storage**: Optimized file organization

### 4. Document Registry (`rag_core/registry.py`)

Tracks metadata and configuration:

- **Repository Configuration**: Manage source repositories
- **Document Metadata**: Track file types, URLs, checksums
- **Toolkit Classification**: Organize by project/domain
- **Change Detection**: Monitor for updates

### 5. Knowledge Base Builder (`scripts/build_knowledge_base.py`)

Processes source repositories into searchable format:

- **Repository Cloning**: Fetch latest code from GitHub
- **Content Extraction**: Process various file types
- **Embedding Generation**: Create vector representations
- **Index Building**: Construct searchable indexes

## Data Flow

### 1. Build Process

```
GitHub Repos → Clone → Extract → Process → Embed → Index → Knowledge Base
```

1. **Clone**: Download repositories to local storage
2. **Extract**: Read files and extract text content
3. **Process**: Clean and normalize text
4. **Embed**: Generate vector embeddings
5. **Index**: Build searchable indexes
6. **Store**: Save to knowledge base

### 2. Search Process

```
Query → Embed → Search → Score → Filter → Rank → Results
```

1. **Embed**: Convert query to vector representation
2. **Search**: Find similar document vectors
3. **Score**: Calculate relevance scores
4. **Filter**: Apply threshold and toolkit filters
5. **Rank**: Sort by adjusted relevance
6. **Results**: Return formatted results

### 3. Retrieval Process

```
Document ID → Locate → Extract → Format → Return
```

1. **Locate**: Find document in text store
2. **Extract**: Get requested line range
3. **Format**: Add metadata and formatting
4. **Return**: Provide structured response

## Interface Layers

### CLI Interface (`nancy_brain/cli.py`)

Command-line interface for direct interaction:

- `nancy-brain search` - Search the knowledge base
- `nancy-brain explore` - Browse document tree
- `nancy-brain build` - Rebuild knowledge base

### MCP Server (`connectors/mcp_server/`)

Model Context Protocol server for AI integration:

- Provides tools for LLMs to search and retrieve
- Integrates with Claude Desktop and VS Code
- Supports real-time knowledge base access

### HTTP API (`connectors/http_api/`)

REST API for programmatic access:

- RESTful endpoints for all operations
- JSON request/response format
- Rate limiting and error handling

### Web UI (`nancy_brain/admin_ui.py`)

Browser-based interface for management:

- Visual search interface
- Knowledge base statistics
- Configuration management

## Configuration System

### Repository Configuration (`config/repositories.yml`)

Defines source repositories:

```yaml
microlensing_tools:
  - name: MulensModel
    url: https://github.com/rpoleski/MulensModel.git
  - name: pyLIMA
    url: https://github.com/ebachelet/pyLIMA.git

general_tools:
  - name: numpy
    url: https://github.com/numpy/numpy.git
```

### Weights Configuration (`config/weights.yaml`)

Controls relevance scoring:

```yaml
extensions:
  ".py": 1.2
  ".md": 1.0
  ".rst": 0.9
  ".txt": 0.8

toolkits:
  microlensing_tools: 1.5
  general_tools: 1.0
```

## Performance Considerations

### Memory Management

- **Lazy Loading**: Load embeddings on demand
- **Caching**: Cache frequently accessed documents
- **Batch Processing**: Process multiple queries efficiently

### Storage Optimization

- **Compressed Embeddings**: Reduce storage requirements
- **Incremental Updates**: Only rebuild changed content
- **Efficient Indexing**: Optimized data structures

### Query Optimization

- **Parallel Processing**: Concurrent search operations
- **Result Caching**: Cache common query results
- **Smart Filtering**: Early filtering to reduce computation

## Extensibility

### Custom Embeddings

Add new embedding models:

```python
class CustomEmbedding:
    def embed_query(self, text):
        # Your embedding logic here
        return vector
```

### Custom Processors

Add support for new file types:

```python
class CustomProcessor:
    def process_file(self, filepath):
        # Extract text from custom format
        return text_content
```

### Custom Interfaces

Add new interaction methods:

```python
class CustomInterface:
    def __init__(self, rag_service):
        self.rag_service = rag_service
    
    def handle_request(self, request):
        # Process custom request format
        return response
```

## Security Considerations

### Access Control

- API authentication and authorization
- Resource usage limits
- Input validation and sanitization

### Data Protection

- Secure storage of sensitive content
- Encryption of embeddings
- Audit logging of access

### Network Security

- HTTPS for API endpoints
- Rate limiting and DDoS protection
- Secure credential management

## Monitoring and Debugging

### Logging

Comprehensive logging throughout the system:

- Query performance metrics
- Error tracking and debugging
- Usage analytics

### Health Checks

Built-in health monitoring:

- System status endpoints
- Performance metrics
- Resource utilization

### Debugging Tools

Development and troubleshooting utilities:

- Verbose logging modes
- Query explanation tools
- Performance profiling
