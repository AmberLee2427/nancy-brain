#!/usr/bin/env python3
"""
Quick manual test to start the HTTP API server.
Run this to test the server manually.
"""

import sys
from pathlib import Path

# Add the nancy-brain directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from connectors.http_api.app import app

if __name__ == "__main__":
    print("🚀 Starting Nancy RAG HTTP API...")
    print("📝 Note: RAG service not initialized - expect 503 errors for most endpoints")
    print("✅ OpenAPI docs available at: http://localhost:8000/docs")
    print("✅ OpenAPI JSON at: http://localhost:8000/openapi.json")
    print()

    try:
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    except ImportError:
        print("❌ uvicorn not available. Install with: pip install uvicorn")
        print("📋 Alternatively, use: python -m uvicorn connectors.http_api.app:app --host 127.0.0.1 --port 8000")
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
