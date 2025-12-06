"""
Hybrid Detection API Router

This router provides endpoints for the new hybrid detection pipeline
that combines PDF structure detection, geometric detection, and vision AI.

Endpoints:
- POST /api/v1/hybrid/{document_id}/process - Process document with hybrid detection
- GET /api/v1/hybrid/{document_id}/fields - Get detected fields with source info
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from enum import Enum

from app.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.models.field import FieldRegion
from app.utils.logging import get_logger

router = APIRouter(prefix="/api/v1/hybrid", tags=["hybrid-detection"])
logger = get_logger(__name__)


# Request/Response Models

class VisionProvider(str, Enum):
    openai = "openai"
    gemini = "gemini"


class HybridProcessRequest(BaseModel):
    """Request body for hybrid processing"""
    force: bool = False
    enable_vision: bool = True
    vision_provider: VisionProvider = VisionProvider.openai


class FieldsBySource(BaseModel):
    """Field count by detection source"""
    structure: int = 0
    geometric: int = 0
    vision: int = 0
    merged: int = 0


class HybridProcessResponse(BaseModel):
    """Response from hybrid processing"""
    document_id: UUID
    status: str
    page_count: Optional[int] = None
    fields_found: int = 0
    fields_by_source: Optional[FieldsBySource] = None
    acroform: bool = False
    message: Optional[str] = None


class FieldRegionWithSource(BaseModel):
    """Field region with detection source information"""
    id: UUID
    page_index: int
    x: float
    y: float
    width: float
    height: float
    field_type: str
    label: str
    confidence: float
    template_key: Optional[str] = None


class HybridFieldsResponse(BaseModel):
    """Response with detected fields"""
    document_id: UUID
    fields: List[FieldRegionWithSource]
    total_count: int


# Helper function to get current user
def get_current_user(db: Session = Depends(get_db)) -> User:
    """Stub: Get or create default user for single-user mode"""
    from app.models.user import User
    user = db.query(User).filter(User.email == "default@documentai.app").first()
    if not user:
        user = User(email="default@documentai.app")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/{document_id}/process", response_model=HybridProcessResponse)
async def process_document_hybrid(
    document_id: UUID,
    request: HybridProcessRequest = HybridProcessRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Process a document using the hybrid detection pipeline.
    
    The hybrid pipeline combines:
    1. PDF Structure Detection - Native PDF form fields (highest accuracy)
    2. Geometric Detection - OpenCV-based visual detection
    3. Vision AI Detection - LLM-based semantic understanding (optional)
    
    All detections are merged and deduplicated using IoU-based matching.
    
    Args:
        document_id: UUID of the document to process
        request: Processing options (force, enable_vision, vision_provider)
    
    Returns:
        Processing results including field counts by source
    """
    # Fetch document
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check if document can be processed
    if document.status not in [DocumentStatus.imported, DocumentStatus.ready, DocumentStatus.failed]:
        if not request.force:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document cannot be processed in status: {document.status}. Use force=true to override."
            )
    
    try:
        # Import here to avoid circular imports
        from workers.hybrid_processor import HybridProcessor
        
        # Create processor
        processor = HybridProcessor(
            enable_vision=request.enable_vision,
            vision_provider=request.vision_provider.value,
            debug=False,
        )
        
        # Process document
        result = processor.process_document(
            document_id=str(document_id),
            force=request.force,
        )
        
        # Build response
        fields_by_source = None
        if 'fields_by_source' in result:
            fbs = result['fields_by_source']
            fields_by_source = FieldsBySource(
                structure=fbs.get('structure', 0),
                geometric=fbs.get('geometric', 0),
                vision=fbs.get('vision', 0),
                merged=fbs.get('merged', 0),
            )
        
        return HybridProcessResponse(
            document_id=document_id,
            status=result.get('status', 'unknown'),
            page_count=result.get('page_count'),
            fields_found=result.get('fields_found', 0),
            fields_by_source=fields_by_source,
            acroform=result.get('acroform', False),
            message=result.get('reason'),
        )
        
    except Exception as e:
        logger.error(f"Hybrid processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}"
        )


@router.get("/{document_id}/fields", response_model=HybridFieldsResponse)
async def get_hybrid_fields(
    document_id: UUID,
    page_index: Optional[int] = Query(None, description="Filter by page index"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get detected fields for a document.
    
    Returns all field regions detected by the hybrid pipeline,
    optionally filtered by page index.
    
    Args:
        document_id: UUID of the document
        page_index: Optional page filter
    
    Returns:
        List of field regions with detection metadata
    """
    # Fetch document
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Query field regions
    query = db.query(FieldRegion).filter(FieldRegion.document_id == document_id)
    
    if page_index is not None:
        query = query.filter(FieldRegion.page_index == page_index)
    
    # Order by page and position
    query = query.order_by(FieldRegion.page_index, FieldRegion.y.desc(), FieldRegion.x)
    
    field_regions = query.all()
    
    # Convert to response format
    fields = [
        FieldRegionWithSource(
            id=fr.id,
            page_index=fr.page_index,
            x=fr.x,
            y=fr.y,
            width=fr.width,
            height=fr.height,
            field_type=fr.field_type.value,
            label=fr.label,
            confidence=fr.confidence,
            template_key=fr.template_key,
        )
        for fr in field_regions
    ]
    
    return HybridFieldsResponse(
        document_id=document_id,
        fields=fields,
        total_count=len(fields),
    )


@router.delete("/{document_id}/fields", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hybrid_fields(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete all detected fields for a document.
    
    This allows re-processing the document with different settings.
    
    Args:
        document_id: UUID of the document
    """
    # Fetch document
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Delete field regions
    deleted_count = db.query(FieldRegion).filter(
        FieldRegion.document_id == document_id
    ).delete()
    
    # Reset document status
    document.status = DocumentStatus.imported
    db.commit()
    
    logger.info(f"Deleted {deleted_count} fields for document {document_id}")
