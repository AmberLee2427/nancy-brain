"""
FastAPI HTTP connector for Nancy's RAG core.
Provides REST endpoints for search, retrieve, tree, weight, version, and health operations.
"""

import os
from pathlib import Path
import logging
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from connectors.http_api import auth

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Load .env file if present (dev convenience)
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parents[2] / "config" / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger = logging.getLogger(__name__)
        logger.info(f"Loaded environment overrides from {env_path}")
except Exception:
    pass

from fastapi.middleware.cors import CORSMiddleware
from fastapi import status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
import uuid
from pathlib import Path

from rag_core.service import RAGService
from rag_core.types import SearchHit, Passage

logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()


# Request/Response models
class SearchResponse(BaseModel):
    hits: List[SearchHit]
    index_version: str
    trace_id: str


class RetrieveRequest(BaseModel):
    doc_id: str
    start: int
    end: int


class RetrieveBatchRequest(BaseModel):
    items: List[RetrieveRequest]


class RetrieveResponse(BaseModel):
    passage: Passage
    trace_id: str


class RetrieveBatchResponse(BaseModel):
    passages: List[Passage]
    trace_id: str


class TreeResponse(BaseModel):
    entries: List[Dict[str, Any]]
    trace_id: str


class SetWeightRequest(BaseModel):
    doc_id: str
    multiplier: float
    namespace: str = "global"
    ttl_days: Optional[int] = None


class VersionResponse(BaseModel):
    index_version: str
    build_sha: str
    built_at: str
    python_version: str
    python_implementation: str
    environment: str
    dependencies: Dict[str, str]
    trace_id: str


class HealthResponse(BaseModel):
    status: str
    trace_id: str


# System status response model
class SystemStatusResponse(BaseModel):
    status: str
    index_version: str
    build_sha: str
    built_at: str
    python_version: str
    python_implementation: str
    environment: str
    dependencies: Dict[str, str]
    trace_id: str


# Error model
class ErrorResponse(BaseModel):
    error: str
    trace_id: str
    detail: Optional[str] = None


# --- SYSTEM STATUS ENDPOINT ---


# --- SYSTEM STATUS ENDPOINT ---

# --- SYSTEM STATUS ENDPOINT ---

# Initialize FastAPI app
app = FastAPI(
    title="Nancy RAG API",
    description="REST API for Nancy's knowledge base search and retrieval",
    version="2.0.0",
    openapi_version="3.0.3",
)
auth.create_user_table()  # Ensure user table exists at startup
auth.create_refresh_table()  # Ensure refresh token table exists

# Enforce secret key in non-dev mode
if (
    os.environ.get("NB_SECRET_KEY") in (None, "", "nancy-brain-dev-key")
    and os.environ.get("NB_ALLOW_INSECURE", "false").lower() != "true"
):
    raise RuntimeError("NB_SECRET_KEY not set. Set NB_SECRET_KEY or export NB_ALLOW_INSECURE=true for dev.")

# Middleware
# app.add_middleware(GzipMiddleware, minimum_size=1000)  # Commented out for now

# Global RAG service instance
rag_service: Optional[RAGService] = None


def reset_rag_service():
    """Test helper to clear the global rag_service (no-op if already None)."""
    global rag_service
    rag_service = None


def get_rag_service() -> RAGService:
    """Dependency to get RAG service instance."""
    if rag_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service not initialized",
        )
    return rag_service


def verify_auth(token: str = Depends(security)) -> str:
    """Simple bearer token auth - implement proper validation."""
    # TODO: Implement proper token validation
    return token.credentials


# --- SYSTEM STATUS ENDPOINT ---
@app.get("/system_status", response_model=SystemStatusResponse, operation_id="system_status")
async def system_status(rag: RAGService = Depends(get_rag_service), _token: str = Depends(verify_auth)):
    """Get full system status including health, version, environment, and dependencies."""
    trace_id = str(uuid.uuid4())
    try:
        health_info = await rag.health()
        version_info = await rag.version()
        # Ensure all expected fields are present
        version_info.setdefault("python_version", "unknown")
        version_info.setdefault("python_implementation", "unknown")
        version_info.setdefault("environment", "unknown")
        version_info.setdefault("dependencies", {})
        return SystemStatusResponse(
            status=health_info.get("status", "unknown"),
            index_version=version_info.get("index_version", "unknown"),
            build_sha=version_info.get("build_sha", "unknown"),
            built_at=version_info.get("built_at", "unknown"),
            python_version=version_info["python_version"],
            python_implementation=version_info["python_implementation"],
            environment=version_info["environment"],
            dependencies=version_info["dependencies"],
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error(f"System status failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"System status failed: {str(e)}",
        )


# --- Auth endpoints ---
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = auth.create_access_token(data={"sub": user["username"]})
    refresh_token = auth.create_refresh_token(data={"sub": user["username"]})
    # store refresh token for revocation support
    try:
        auth.store_refresh_token(user["username"], refresh_token)
    except Exception:
        logger.warning("Failed to store refresh token in DB")
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@app.post("/refresh")
def refresh_token_endpoint(payload: dict):
    token = payload.get("refresh_token")
    username = auth.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    # check DB for revocation
    if not auth.is_refresh_valid(token):
        raise HTTPException(status_code=401, detail="Refresh token revoked or unknown")
    new_access = auth.create_access_token(data={"sub": username})
    return {"access_token": new_access, "token_type": "bearer"}


@app.post("/revoke")
def revoke_token(payload: dict, current_user=Depends(auth.require_auth)):
    token = payload.get("refresh_token")
    if not token:
        raise HTTPException(status_code=400, detail="refresh_token required")
    owner = auth.get_refresh_owner(token)
    if owner is None:
        raise HTTPException(status_code=404, detail="token not found")
    if owner != current_user["username"]:
        raise HTTPException(status_code=403, detail="not allowed to revoke this token")
    auth.revoke_refresh_token(token)
    return {"revoked": True}


# Example protected endpoint
@app.get("/protected")
def protected_route(current_user=Depends(auth.require_auth)):
    return {"message": f"Hello, {current_user['username']}!"}


@app.get("/search", response_model=SearchResponse, operation_id="search_documents")
async def search(
    query: str,
    limit: int = 6,
    toolkit: Optional[str] = None,
    doctype: Optional[str] = None,
    threshold: float = 0.0,
    rag: RAGService = Depends(get_rag_service),
    _token: str = Depends(verify_auth),
):
    """Search the knowledge base for relevant documents."""
    trace_id = str(uuid.uuid4())
    try:
        hits = await rag.search_docs(
            query=query,
            limit=limit,
            toolkit=toolkit,
            doctype=doctype,
            threshold=threshold,
        )
        version_info = await rag.version()
        return SearchResponse(hits=hits, index_version=version_info["index_version"], trace_id=trace_id)
    except Exception as e:
        logger.error(f"Search failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@app.post("/retrieve", response_model=RetrieveResponse, operation_id="retrieve_passage")
async def retrieve(
    request: RetrieveRequest,
    rag: RAGService = Depends(get_rag_service),
    _token: str = Depends(verify_auth),
):
    """Retrieve a specific passage from a document."""
    trace_id = str(uuid.uuid4())
    try:
        passage = await rag.retrieve(doc_id=request.doc_id, start=request.start, end=request.end)
        return RetrieveResponse(passage=passage, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Retrieve failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieve failed: {str(e)}",
        )


@app.post(
    "/retrieve/batch",
    response_model=RetrieveBatchResponse,
    operation_id="retrieve_batch",
)
async def retrieve_batch(
    request: RetrieveBatchRequest,
    rag: RAGService = Depends(get_rag_service),
    _token: str = Depends(verify_auth),
):
    """Retrieve multiple passages in batch."""
    trace_id = str(uuid.uuid4())
    try:
        items = [{"doc_id": item.doc_id, "start": item.start, "end": item.end} for item in request.items]
        passages = await rag.retrieve_batch(items)
        return RetrieveBatchResponse(passages=passages, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Batch retrieve failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch retrieve failed: {str(e)}",
        )


@app.get("/tree", response_model=TreeResponse, operation_id="list_tree")
async def tree(
    prefix: str = "",
    depth: int = 2,
    max_entries: int = 500,
    rag: RAGService = Depends(get_rag_service),
    _token: str = Depends(verify_auth),
):
    """List knowledge base structure as a tree."""
    trace_id = str(uuid.uuid4())
    try:
        entries = await rag.list_tree(prefix=prefix, depth=depth, max_entries=max_entries)
        return TreeResponse(entries=entries, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Tree listing failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tree listing failed: {str(e)}",
        )


@app.post("/weight", operation_id="set_weight")
async def set_weight(
    request: SetWeightRequest,
    rag: RAGService = Depends(get_rag_service),
    _token: str = Depends(verify_auth),
):
    """Set weighting for a document in search results."""
    trace_id = str(uuid.uuid4())
    try:
        await rag.set_weight(
            doc_id=request.doc_id,
            multiplier=request.multiplier,
            namespace=request.namespace,
            ttl_days=request.ttl_days,
        )
        return {"status": "success", "trace_id": trace_id}
    except Exception as e:
        logger.error(f"Set weight failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Set weight failed: {str(e)}",
        )


@app.get("/version", response_model=VersionResponse, operation_id="get_version")
async def version(rag: RAGService = Depends(get_rag_service), _token: str = Depends(verify_auth)):
    """Get version information about the knowledge base, including environment and dependencies."""
    trace_id = str(uuid.uuid4())
    try:
        version_info = await rag.version()
        # Ensure all expected fields are present for backward compatibility
        version_info.setdefault("python_version", "unknown")
        version_info.setdefault("python_implementation", "unknown")
        version_info.setdefault("environment", "unknown")
        version_info.setdefault("dependencies", {})
        return VersionResponse(**version_info, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Version check failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Version check failed: {str(e)}",
        )


@app.get("/health", response_model=HealthResponse, operation_id="health_check")
async def health(rag: RAGService = Depends(get_rag_service), _token: str = Depends(verify_auth)):
    """Health check endpoint."""
    trace_id = str(uuid.uuid4())
    try:
        health_info = await rag.health()
        return HealthResponse(status=health_info["status"], trace_id=trace_id)
    except Exception as e:
        logger.error(f"Health check failed: {e}", extra={"trace_id": trace_id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {str(e)}",
        )


def initialize_rag_service(
    config_path: Path,
    embeddings_path: Path,
    weights_path: Path = None,
    use_dual_embedding: bool = True,
) -> RAGService:
    """Initialize the RAG service with given paths."""
    global rag_service

    # Default weights path if not provided
    if weights_path is None:
        weights_path = config_path.parent / "weights.yaml"
        if not weights_path.exists():
            weights_path.write_text("extensions: {}")

    rag_service = RAGService(
        config_path=config_path,
        embeddings_path=embeddings_path,
        weights_path=weights_path,
        use_dual_embedding=use_dual_embedding,
    )
    return rag_service


if __name__ == "__main__":
    import uvicorn

    # Initialize with default paths
    config_path = Path(__file__).parent.parent.parent / "config" / "repositories.yml"
    embeddings_path = Path(__file__).parent.parent.parent / "knowledge_base" / "embeddings"
    weights_path = Path(__file__).parent.parent.parent / "config" / "weights.yaml"

    initialize_rag_service(config_path, embeddings_path, weights_path)

    uvicorn.run(app, host="0.0.0.0", port=8000)
