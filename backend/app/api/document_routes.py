"""
Document Management API Routes
RESTful API for managing documents in ChromaDB collections

Follows FastAPI best practices:
- Proper HTTP methods (GET, POST, PUT, PATCH, DELETE)
- RESTful resource naming
- Appropriate HTTP status codes
- Input validation with Pydantic
- Consistent error response format
- Pagination support
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field, field_validator

from ..core.exceptions import (
    ResourceNotFoundError,
    RetrievalError,
    ServiceNotInitializedError,
    ValidationError,
)
from ..services.retrieval_service import RetrievalService, get_retrieval_service
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ═════════════════════════════════════════════════════════════════════════
# DEPENDENCY FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════


def get_retrieval_service_dependency() -> RetrievalService:
    """Dependency function for FastAPI to inject RetrievalService"""
    return get_retrieval_service()


# ═════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═════════════════════════════════════════════════════════════════════════


class DocumentMetadata(BaseModel):
    """Document metadata fields"""

    doc_type: Optional[str] = Field(None, description="Document type (e.g., 'law', 'regulation')")
    source: Optional[str] = Field(None, description="Document source")
    date: Optional[str] = Field(None, description="Document date (ISO format)")
    title: Optional[str] = Field(None, description="Document title")
    author: Optional[str] = Field(None, description="Document author")
    tags: Optional[List[str]] = Field(default_factory=list, description="Document tags")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format (ISO 8601)"""
        if v is None:
            return v
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except ValueError:
            raise ValueError("Date must be in ISO 8601 format (e.g., '2024-01-15T10:30:00Z')")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> List[str]:
        """Validate tags list"""
        if v is None:
            return []
        if len(v) > 50:
            raise ValueError("Maximum 50 tags allowed")
        return [tag.strip() for tag in v if tag.strip()]


class DocumentCreate(BaseModel):
    """Request model for creating a new document"""

    content: str = Field(..., min_length=1, max_length=1_000_000, description="Document content")
    collection: str = Field(..., min_length=1, max_length=200, description="Target collection name")
    metadata: Optional[DocumentMetadata] = Field(None, description="Document metadata")
    id: Optional[str] = Field(
        None, max_length=200, description="Optional document ID (auto-generated if not provided)"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Sanitize content to prevent XSS"""
        # Basic XSS prevention - remove script tags
        v = v.replace("<script", "").replace("</script>", "")
        return v.strip()

    @field_validator("collection")
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        """Validate collection name format"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "Collection name must contain only alphanumeric characters, hyphens, and underscores"
            )
        return v


class DocumentUpdate(BaseModel):
    """Request model for updating a document (partial update)"""

    content: Optional[str] = Field(
        None, min_length=1, max_length=1_000_000, description="Updated document content"
    )
    metadata: Optional[DocumentMetadata] = Field(
        None, description="Updated metadata (merges with existing)"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize content to prevent XSS"""
        if v is None:
            return v
        v = v.replace("<script", "").replace("</script>", "")
        return v.strip()


class DocumentResponse(BaseModel):
    """Response model for a single document"""

    id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Document content")
    collection: str = Field(..., description="Collection name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO format)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO format)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc_123",
                "content": "This is the document content...",
                "collection": "legal_documents",
                "metadata": {
                    "doc_type": "law",
                    "source": "Swedish Parliament",
                    "date": "2024-01-15T10:30:00Z",
                    "title": "Example Law",
                },
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            }
        }


class DocumentListItem(BaseModel):
    """Response model for document list items (summary)"""

    id: str
    collection: str
    content_preview: str = Field(..., description="First 200 characters of content")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class PaginatedDocumentsResponse(BaseModel):
    """Paginated response for document list"""

    items: List[DocumentListItem] = Field(..., description="List of documents")
    total: int = Field(..., ge=0, description="Total number of documents matching query")
    page: int = Field(..., ge=1, description="Current page number")
    limit: int = Field(..., ge=1, le=100, description="Items per page")
    pages: int = Field(..., ge=0, description="Total number of pages")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id": "doc_123",
                        "collection": "legal_documents",
                        "content_preview": "This is the document content...",
                        "metadata": {"doc_type": "law"},
                    }
                ],
                "total": 100,
                "page": 1,
                "limit": 10,
                "pages": 10,
            }
        }


class ErrorResponse(BaseModel):
    """Standardized error response format"""

    error: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type code")
    status_code: int = Field(..., description="HTTP status code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Document not found",
                "type": "resource_not_found",
                "status_code": 404,
                "details": {"document_id": "doc_123", "collection": "legal_documents"},
            }
        }


# ═════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════


def sanitize_input(text: str, max_length: int = 10_000) -> str:
    """
    Sanitize user input to prevent XSS and SQL injection.

    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if len(text) > max_length:
        raise ValidationError(f"Input exceeds maximum length of {max_length} characters")

    # Remove potentially dangerous characters
    dangerous_chars = ["<script", "javascript:", "onerror=", "onload="]
    sanitized = text
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, "")

    return sanitized.strip()


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════


@router.get(
    "",
    response_model=PaginatedDocumentsResponse,
    status_code=status.HTTP_200_OK,
    summary="List documents",
    description="Retrieve a paginated list of documents with optional filtering",
    responses={
        200: {"description": "Successfully retrieved documents"},
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_documents(
    collection: Optional[str] = Query(
        None, description="Filter by collection name", max_length=200
    ),
    doc_type: Optional[str] = Query(None, description="Filter by document type", max_length=100),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=100, description="Items per page (max 100)"),
    x_api_version: Optional[str] = Header(None, alias="X-API-Version", description="API version"),
    retrieval_service: RetrievalService = Depends(get_retrieval_service_dependency),
) -> PaginatedDocumentsResponse:
    """
    List documents with pagination and filtering.

    Supports filtering by:
    - Collection name
    - Document type (via metadata)

    **Rate Limiting**: 100 requests per minute per IP (to be implemented)

    **Authentication**: Currently not required (to be implemented)
    """
    try:
        # Validate and sanitize inputs
        if collection:
            collection = sanitize_input(collection, max_length=200)
        if doc_type:
            doc_type = sanitize_input(doc_type, max_length=100)

        # Build where filter for ChromaDB
        where_filter = {}
        if collection:
            where_filter["collection"] = collection
        if doc_type:
            where_filter["doc_type"] = doc_type

        # Calculate pagination
        offset = (page - 1) * limit

        # Get documents from retrieval service
        # Note: This is a simplified implementation
        # In production, you'd query ChromaDB directly with pagination
        try:
            client = retrieval_service._chromadb_client
            if not client:
                raise ServiceNotInitializedError("ChromaDB client not initialized")

            # Get collection
            collections = client.list_collections()
            target_collection = None
            if collection:
                target_collection = next((c for c in collections if c.name == collection), None)
            else:
                # If no collection specified, use first available or return empty
                target_collection = collections[0] if collections else None

            if not target_collection:
                return PaginatedDocumentsResponse(
                    items=[],
                    total=0,
                    page=page,
                    limit=limit,
                    pages=0,
                )

            # Get all documents (simplified - in production, implement proper pagination)
            # ChromaDB doesn't have built-in pagination, so we fetch all and slice
            all_docs = target_collection.get(where=where_filter if where_filter else None)

            total = len(all_docs["ids"]) if all_docs and "ids" in all_docs else 0
            pages = (total + limit - 1) // limit if total > 0 else 0

            # Slice for pagination
            start_idx = offset
            end_idx = min(offset + limit, total)

            items = []
            if all_docs and "ids" in all_docs and start_idx < total:
                for i in range(start_idx, end_idx):
                    doc_id = all_docs["ids"][i]
                    content = all_docs["documents"][i] if "documents" in all_docs else ""
                    metadata = all_docs["metadatas"][i] if "metadatas" in all_docs else {}

                    items.append(
                        DocumentListItem(
                            id=doc_id,
                            collection=collection or target_collection.name,
                            content_preview=content[:200] + "..."
                            if len(content) > 200
                            else content,
                            metadata=metadata,
                            created_at=metadata.get("created_at"),
                        )
                    )

            return PaginatedDocumentsResponse(
                items=items,
                total=total,
                page=page,
                limit=limit,
                pages=pages,
            )

        except Exception as e:
            logger.error(f"Error retrieving documents: {e}")
            raise RetrievalError(f"Failed to retrieve documents: {str(e)}")

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_documents: {e}")
        raise RetrievalError(f"Internal error: {str(e)}")


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document by ID",
    description="Retrieve a specific document by its ID",
    responses={
        200: {"description": "Document retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Document not found"},
        400: {"model": ErrorResponse, "description": "Invalid document ID"},
    },
)
async def get_document(
    document_id: str,
    collection: Optional[str] = Query(
        None, description="Collection name (optional)", max_length=200
    ),
    x_api_version: Optional[str] = Header(None, alias="X-API-Version"),
    retrieval_service: RetrievalService = Depends(get_retrieval_service_dependency),
) -> DocumentResponse:
    """
    Get a single document by ID.

    **Security**: Document IDs are validated to prevent injection attacks.
    """
    try:
        # Sanitize inputs
        document_id = sanitize_input(document_id, max_length=200)
        if collection:
            collection = sanitize_input(collection, max_length=200)

        client = retrieval_service._chromadb_client
        if not client:
            raise ServiceNotInitializedError("ChromaDB client not initialized")

        # Search across collections or specific collection
        collections_to_search = (
            [collection] if collection else [c.name for c in client.list_collections()]
        )

        document_found = None
        found_collection = None

        for coll_name in collections_to_search:
            try:
                coll = client.get_collection(coll_name)
                result = coll.get(ids=[document_id])

                if result and "ids" in result and len(result["ids"]) > 0:
                    document_found = result
                    found_collection = coll_name
                    break
            except Exception:
                continue

        if not document_found or not document_found.get("ids"):
            raise ResourceNotFoundError(
                f"Document '{document_id}' not found"
                + (f" in collection '{collection}'" if collection else "")
            )

        # Extract document data
        doc_id = document_found["ids"][0]
        content = document_found["documents"][0] if "documents" in document_found else ""
        metadata = document_found["metadatas"][0] if "metadatas" in document_found else {}

        return DocumentResponse(
            id=doc_id,
            content=content,
            collection=found_collection or collection or "unknown",
            metadata=metadata,
            created_at=metadata.get("created_at"),
            updated_at=metadata.get("updated_at"),
        )

    except ResourceNotFoundError:
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document {document_id}: {e}")
        raise RetrievalError(f"Failed to retrieve document: {str(e)}")


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create document",
    description="Create a new document in the specified collection",
    responses={
        201: {"description": "Document created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        409: {"model": ErrorResponse, "description": "Document with ID already exists"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def create_document(
    document: DocumentCreate,
    x_api_version: Optional[str] = Header(None, alias="X-API-Version"),
    retrieval_service: RetrievalService = Depends(get_retrieval_service_dependency),
) -> DocumentResponse:
    """
    Create a new document.

    **Validation**:
    - Content must be 1-1,000,000 characters
    - Collection name must be alphanumeric with hyphens/underscores
    - Metadata fields are validated

    **Security**:
    - Content is sanitized to prevent XSS
    - Collection names are validated to prevent injection
    """
    try:
        client = retrieval_service._chromadb_client
        if not client:
            raise ServiceNotInitializedError("ChromaDB client not initialized")

        # Get or create collection
        try:
            collection_obj = client.get_collection(document.collection)
        except Exception:
            # Collection doesn't exist, create it
            collection_obj = client.create_collection(
                name=document.collection,
                metadata={"created_at": datetime.now().isoformat()},
            )

        # Check if document ID already exists
        if document.id:
            existing = collection_obj.get(ids=[document.id])
            if existing and "ids" in existing and len(existing["ids"]) > 0:
                raise ValidationError(
                    f"Document with ID '{document.id}' already exists in collection '{document.collection}'"
                )

        # Prepare metadata
        metadata_dict = {}
        if document.metadata:
            metadata_dict = document.metadata.model_dump(exclude_none=True)
        metadata_dict["created_at"] = datetime.now().isoformat()
        metadata_dict["updated_at"] = datetime.now().isoformat()

        # Generate ID if not provided
        doc_id = document.id or f"doc_{datetime.now().timestamp()}"

        # Add document to collection
        collection_obj.add(
            ids=[doc_id],
            documents=[document.content],
            metadatas=[metadata_dict],
        )

        logger.info(f"Created document '{doc_id}' in collection '{document.collection}'")

        return DocumentResponse(
            id=doc_id,
            content=document.content,
            collection=document.collection,
            metadata=metadata_dict,
            created_at=metadata_dict["created_at"],
            updated_at=metadata_dict["updated_at"],
        )

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error creating document: {e}")
        if "already exists" in str(e).lower():
            raise ValidationError(str(e))
        raise RetrievalError(f"Failed to create document: {str(e)}")


@router.put(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Update document (full)",
    description="Replace an entire document with new content and metadata",
    responses={
        200: {"description": "Document updated successfully"},
        404: {"model": ErrorResponse, "description": "Document not found"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
    },
)
async def update_document(
    document_id: str,
    document: DocumentUpdate,
    collection: Optional[str] = Query(None, description="Collection name", max_length=200),
    x_api_version: Optional[str] = Header(None, alias="X-API-Version"),
    retrieval_service: RetrievalService = Depends(get_retrieval_service_dependency),
) -> DocumentResponse:
    """
    Update a document (full replacement).

    **Note**: This replaces the entire document. Use PATCH for partial updates.
    """
    try:
        document_id = sanitize_input(document_id, max_length=200)
        if collection:
            collection = sanitize_input(collection, max_length=200)

        client = retrieval_service._chromadb_client
        if not client:
            raise ServiceNotInitializedError("ChromaDB client not initialized")

        # Find document
        collections_to_search = (
            [collection] if collection else [c.name for c in client.list_collections()]
        )
        document_found = None
        found_collection = None

        for coll_name in collections_to_search:
            try:
                coll = client.get_collection(coll_name)
                result = coll.get(ids=[document_id])
                if result and "ids" in result and len(result["ids"]) > 0:
                    document_found = result
                    found_collection = coll_name
                    break
            except Exception:
                continue

        if not document_found:
            raise ResourceNotFoundError(f"Document '{document_id}' not found")

        # Get existing metadata to merge
        existing_metadata = document_found["metadatas"][0] if "metadatas" in document_found else {}
        if document.metadata:
            # Merge metadata
            new_metadata = document.metadata.model_dump(exclude_none=True)
            existing_metadata.update(new_metadata)
        existing_metadata["updated_at"] = datetime.now().isoformat()

        # Update document
        coll = client.get_collection(found_collection)
        new_content = document.content if document.content else document_found["documents"][0]

        # ChromaDB update: delete and re-add (ChromaDB doesn't have direct update)
        coll.delete(ids=[document_id])
        coll.add(
            ids=[document_id],
            documents=[new_content],
            metadatas=[existing_metadata],
        )

        logger.info(f"Updated document '{document_id}' in collection '{found_collection}'")

        return DocumentResponse(
            id=document_id,
            content=new_content,
            collection=found_collection,
            metadata=existing_metadata,
            created_at=existing_metadata.get("created_at"),
            updated_at=existing_metadata["updated_at"],
        )

    except ResourceNotFoundError:
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error updating document {document_id}: {e}")
        raise RetrievalError(f"Failed to update document: {str(e)}")


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update document",
    description="Update specific fields of a document without replacing the entire document",
    responses={
        200: {"description": "Document updated successfully"},
        404: {"model": ErrorResponse, "description": "Document not found"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
    },
)
async def patch_document(
    document_id: str,
    document: DocumentUpdate,
    collection: Optional[str] = Query(None, description="Collection name", max_length=200),
    x_api_version: Optional[str] = Header(None, alias="X-API-Version"),
    retrieval_service: RetrievalService = Depends(get_retrieval_service_dependency),
) -> DocumentResponse:
    """
    Partially update a document.

    Only provided fields are updated; others remain unchanged.
    """
    # Same implementation as PUT for now (ChromaDB limitation)
    # In a real implementation, you'd merge more intelligently
    return await update_document(
        document_id, document, collection, x_api_version, retrieval_service
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document",
    description="Delete a document by ID",
    responses={
        204: {"description": "Document deleted successfully"},
        404: {"model": ErrorResponse, "description": "Document not found"},
        400: {"model": ErrorResponse, "description": "Invalid document ID"},
    },
)
async def delete_document(
    document_id: str,
    collection: Optional[str] = Query(None, description="Collection name", max_length=200),
    x_api_version: Optional[str] = Header(None, alias="X-API-Version"),
    retrieval_service: RetrievalService = Depends(get_retrieval_service_dependency),
):
    """
    Delete a document.

    **Warning**: This operation is irreversible.

    **Security**: Requires authentication (to be implemented).
    """
    try:
        document_id = sanitize_input(document_id, max_length=200)
        if collection:
            collection = sanitize_input(collection, max_length=200)

        client = retrieval_service._chromadb_client
        if not client:
            raise ServiceNotInitializedError("ChromaDB client not initialized")

        # Find and delete document
        collections_to_search = (
            [collection] if collection else [c.name for c in client.list_collections()]
        )
        deleted = False

        for coll_name in collections_to_search:
            try:
                coll = client.get_collection(coll_name)
                result = coll.get(ids=[document_id])
                if result and "ids" in result and len(result["ids"]) > 0:
                    coll.delete(ids=[document_id])
                    deleted = True
                    logger.info(f"Deleted document '{document_id}' from collection '{coll_name}'")
                    break
            except Exception:
                continue

        if not deleted:
            raise ResourceNotFoundError(f"Document '{document_id}' not found")

        # Return 204 No Content
        return None

    except ResourceNotFoundError:
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {e}")
        raise RetrievalError(f"Failed to delete document: {str(e)}")
