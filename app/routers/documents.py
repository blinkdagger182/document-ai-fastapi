from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import tempfile
import os

from app.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.document import (
    DocumentSummary,
    InitUploadResponse,
    ProcessDocumentResponse,
    DownloadResponse
)
from app.schemas.field import (
    DocumentDetailResponse,
    FieldComponent,
    FieldRegionDTO,
    SubmitValuesRequest,
    SubmitValuesResponse
)
from app.models.field import FieldRegion, FieldValue
from app.services.storage import get_storage_service
from app.utils.hashing import compute_file_hash
from app.utils.logging import get_logger
from app.services.cloud_tasks import get_cloud_tasks_service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
logger = get_logger(__name__)


def get_current_user(db: Session = Depends(get_db)) -> User:
    """Stub: Get or create default user for single-user mode"""
    user = db.query(User).filter(User.email == "default@documentai.app").first()
    if not user:
        user = User(email="default@documentai.app")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("/init-upload", response_model=InitUploadResponse, status_code=status.HTTP_201_CREATED)
async def init_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Upload a document (PDF or image) and create a document record.
    """
    logger.info(f"Uploading file: {file.filename}")
    
    # Validate file type
    if not file.content_type or not (
        file.content_type.startswith("image/") or 
        file.content_type == "application/pdf"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and image files are supported"
        )
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = tmp_file.name
    
    try:
        # Compute hash
        file_hash = compute_file_hash(tmp_path)
        
        # Create document record
        document = Document(
            user_id=user.id,
            file_name=file.filename or "document.pdf",
            mime_type=file.content_type,
            storage_key_original=f"originals/{user.id}/{file_hash}",
            status=DocumentStatus.imported,
            hash_fingerprint=file_hash
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Upload to storage
        storage = get_storage_service()
        await storage.upload_file(
            local_path=tmp_path,
            key=document.storage_key_original,
            content_type=file.content_type
        )
        
        logger.info(f"Document created: {document.id}")
        
        # Convert to response
        doc_summary = DocumentSummary.model_validate(document)
        
        return InitUploadResponse(
            documentId=document.id,
            document=doc_summary
        )
    
    finally:
        # Cleanup temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/{document_id}/process", response_model=ProcessDocumentResponse)
async def process_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Start OCR processing for a document.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if document.status != DocumentStatus.imported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document cannot be processed in status: {document.status}"
        )
    
    # Enqueue OCR task via Cloud Tasks
    cloud_tasks = get_cloud_tasks_service()
    task_name = cloud_tasks.enqueue_ocr_task(str(document_id))
    
    document.status = DocumentStatus.processing
    db.commit()
    
    logger.info(f"OCR task enqueued for document {document_id}: {task_name}")
    
    return ProcessDocumentResponse(
        documentId=document_id,
        status=document.status
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get document details including field components and field map.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Get field regions
    field_regions = db.query(FieldRegion).filter(
        FieldRegion.document_id == document_id
    ).all()
    
    # Build components and field map
    components = []
    field_map = {}
    
    for region in field_regions:
        component_id = str(region.id)
        
        component = FieldComponent(
            id=region.id,
            fieldId=region.id,
            type=region.field_type,
            label=region.label,
            placeholder=f"Enter {region.label}",
            pageIndex=region.page_index,
            defaultValue=None
        )
        components.append(component)
        
        field_dto = FieldRegionDTO(
            id=region.id,
            pageIndex=region.page_index,
            x=region.x,
            y=region.y,
            width=region.width,
            height=region.height,
            fieldType=region.field_type,
            label=region.label,
            confidence=region.confidence
        )
        field_map[component_id] = field_dto
    
    doc_summary = DocumentSummary.model_validate(document)
    
    return DocumentDetailResponse(
        document=doc_summary,
        components=components,
        fieldMap=field_map
    )


@router.post("/{document_id}/values", response_model=SubmitValuesResponse)
async def submit_values(
    document_id: UUID,
    request: SubmitValuesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Submit field values for a document.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Upsert field values
    for value_input in request.values:
        # Check if value already exists
        existing = db.query(FieldValue).filter(
            FieldValue.document_id == document_id,
            FieldValue.field_region_id == value_input.fieldRegionId,
            FieldValue.user_id == user.id
        ).first()
        
        if existing:
            existing.value = value_input.value
            existing.source = value_input.source
        else:
            field_value = FieldValue(
                document_id=document_id,
                field_region_id=value_input.fieldRegionId,
                user_id=user.id,
                value=value_input.value,
                source=value_input.source
            )
            db.add(field_value)
    
    document.status = DocumentStatus.filling
    db.commit()
    
    logger.info(f"Submitted {len(request.values)} values for document {document_id}")
    
    return SubmitValuesResponse(
        documentId=document_id,
        status=document.status.value
    )


@router.post("/{document_id}/compose", response_model=ProcessDocumentResponse)
async def compose_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Start PDF composition to generate filled PDF.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Enqueue compose task via Cloud Tasks
    cloud_tasks = get_cloud_tasks_service()
    task_name = cloud_tasks.enqueue_compose_task(str(document_id))
    
    document.status = DocumentStatus.filling
    db.commit()
    
    logger.info(f"PDF composition task enqueued for document {document_id}: {task_name}")
    
    return ProcessDocumentResponse(
        documentId=document_id,
        status=document.status
    )


@router.get("/{document_id}/download", response_model=DownloadResponse)
async def download_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get download URL for filled PDF.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if not document.storage_key_filled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filled PDF not yet available"
        )
    
    # Generate presigned URL
    storage = get_storage_service()
    url = storage.generate_presigned_url(
        key=document.storage_key_filled,
        expires_in=3600
    )
    
    return DownloadResponse(
        documentId=document_id,
        filledPdfUrl=url
    )
