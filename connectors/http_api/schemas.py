"""
Pydantic schemas for the HTTP API.
OpenAPI schema generation for GPT Actions integration.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class SearchHitSchema(BaseModel):
    """Schema for search result hit."""

    id: str = Field(description="Document ID")
    text: str = Field(description="Snippet text")
    score: float = Field(description="Relevance score")


class SearchResponseSchema(BaseModel):
    """Response schema for search endpoint."""

    hits: List[SearchHitSchema] = Field(description="Search results")
    index_version: str = Field(description="Knowledge base version")
    trace_id: str = Field(description="Request trace ID")


class PassageSchema(BaseModel):
    """Schema for document passage."""

    doc_id: str = Field(description="Document ID")
    text: str = Field(description="Passage text")
    github_url: str = Field(description="GitHub URL for citation")
    content_sha256: str = Field(description="Content hash for reproducibility")
    index_version: str = Field(description="Knowledge base version", default="")


class RetrieveRequestSchema(BaseModel):
    """Request schema for retrieve endpoint."""

    doc_id: str = Field(description="Document ID to retrieve from")
    start: int = Field(description="Starting line number (1-based)")
    end: int = Field(description="Ending line number (inclusive)")


class RetrieveBatchRequestSchema(BaseModel):
    """Request schema for batch retrieve endpoint."""

    items: List[RetrieveRequestSchema] = Field(description="List of retrieve requests")


class RetrieveResponseSchema(BaseModel):
    """Response schema for retrieve endpoint."""

    passage: PassageSchema = Field(description="Retrieved passage")
    trace_id: str = Field(description="Request trace ID")


class RetrieveBatchResponseSchema(BaseModel):
    """Response schema for batch retrieve endpoint."""

    passages: List[PassageSchema] = Field(description="Retrieved passages")
    trace_id: str = Field(description="Request trace ID")


class TreeEntrySchema(BaseModel):
    """Schema for tree entry."""

    path: str = Field(description="Document path")
    type: str = Field(description="Entry type (file/directory)")
    size: Optional[int] = Field(description="Size in bytes", default=None)


class TreeResponseSchema(BaseModel):
    """Response schema for tree endpoint."""

    entries: List[TreeEntrySchema] = Field(description="Tree entries")
    trace_id: str = Field(description="Request trace ID")


class SetWeightRequestSchema(BaseModel):
    """Request schema for weight setting."""

    doc_id: str = Field(description="Document ID to weight")
    multiplier: float = Field(description="Weight multiplier")
    namespace: str = Field(description="Weight namespace", default="global")
    ttl_days: Optional[int] = Field(description="TTL in days", default=None)


class VersionResponseSchema(BaseModel):
    """Response schema for version endpoint."""

    index_version: str = Field(description="Knowledge base version")
    build_sha: str = Field(description="Build commit SHA")
    built_at: str = Field(description="Build timestamp")
    trace_id: str = Field(description="Request trace ID")


class HealthResponseSchema(BaseModel):
    """Response schema for health endpoint."""

    status: str = Field(description="Health status")
    trace_id: str = Field(description="Request trace ID")


class ErrorResponseSchema(BaseModel):
    """Error response schema."""

    error: str = Field(description="Error message")
    trace_id: str = Field(description="Request trace ID")
    detail: Optional[str] = Field(description="Detailed error info", default=None)


# OpenAPI examples for documentation
SEARCH_EXAMPLE = {
    "summary": "Search for MulensModel documentation",
    "value": {
        "query": "MulensModel PSPL parameters",
        "limit": 6,
        "toolkit": "mulensmodel",
        "doctype": "docs",
    },
}

RETRIEVE_EXAMPLE = {
    "summary": "Retrieve specific lines from a document",
    "value": {
        "doc_id": "microlensing_tools/MulensModel/README.md",
        "start": 45,
        "end": 60,
    },
}
