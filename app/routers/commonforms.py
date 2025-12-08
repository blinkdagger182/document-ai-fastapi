"""
CommonForms Router - API endpoints for CommonForms processing
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime

from app.database import get_db, SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.models.field import FieldRegion
from app.services.storage import get_storage_service
from app.services.cloud_tasks import get_cloud_tasks_service
from app.utils.logging import get_logger

router = APIRouter(prefix="/api/v1/process", tags=["commonforms"])
logger = get_logger(__name__)

# In-memory job store (use Redis in production)
_job_store = {}


class ProcessCommonFormsResponse(BaseModel):
    jobId: str


class FieldInfo(BaseModel):
    id: str
    type: str
    page: int
    bbox: List[float]
    label: Optional[str] = None


class JobStatusResponse(BaseModel):
    status: str
    outputPdfUrl: Optional[str] = None
    fields: List[FieldInfo] = []
    documentId: Optional[str] = None
    error: Optional[str] = None


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


@router.post("/commonforms/{document_id}", response_model=ProcessCommonFormsResponse)
async def process_commonforms(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Start CommonForms processing for a document.
    
    This endpoint:
    1. Validates the document exists
    2. Creates a job ID
    3. Queues the CommonForms processing task
    4. Returns the job ID for status polling
    """
    # Validate document exists and belongs to user
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Generate job ID
    job_id = str(uuid4())
    
    # Store job status
    _job_store[job_id] = {
        "status": "queued",
        "document_id": str(document_id),
        "created_at": datetime.utcnow().isoformat(),
        "output_pdf_url": None,
        "fields": [],
        "error": None
    }
    
    # Enqueue CommonForms task via Cloud Tasks
    try:
        cloud_tasks = get_cloud_tasks_service()
        task_name = cloud_tasks.enqueue_commonforms_task(str(document_id), job_id)
        
        _job_store[job_id]["status"] = "processing"
        _job_store[job_id]["task_name"] = task_name
        
        logger.info(f"CommonForms task enqueued for document {document_id}: {task_name}")
        
    except Exception as e:
        # If Cloud Tasks fails, process directly in background (for local dev)
        logger.warning(f"Cloud Tasks unavailable, starting background processing: {e}")
        _job_store[job_id]["status"] = "processing"
        
        # Start background task for direct processing
        import asyncio
        asyncio.create_task(_process_commonforms_background(str(document_id), job_id))
    
    return ProcessCommonFormsResponse(jobId=job_id)


async def _process_commonforms_background(document_id: str, job_id: str):
    """
    Background task to process CommonForms when Cloud Tasks is unavailable.
    Calls the CommonForms worker directly via HTTP.
    """
    import httpx
    from app.config import settings
    
    logger.info(f"Starting background CommonForms processing for {document_id}")
    
    worker_url = settings.commonforms_worker_url
    if not worker_url:
        _job_store[job_id]["status"] = "failed"
        _job_store[job_id]["error"] = "CommonForms worker URL not configured"
        return
    
    try:
        # Call the CommonForms worker directly
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                f"{worker_url}/process-commonforms",
                json={
                    "document_id": document_id,
                    "job_id": job_id
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"CommonForms worker completed: {result}")
                
                # Worker updates the document directly, so we just update job store
                _job_store[job_id]["status"] = "completed"
                if "output_url" in result:
                    _job_store[job_id]["output_pdf_url"] = result["output_url"]
                if "fields" in result:
                    _job_store[job_id]["fields"] = result["fields"]
            else:
                error_msg = f"Worker returned {response.status_code}: {response.text}"
                logger.error(error_msg)
                _job_store[job_id]["status"] = "failed"
                _job_store[job_id]["error"] = error_msg
                
    except httpx.TimeoutException:
        logger.error("CommonForms worker timed out")
        _job_store[job_id]["status"] = "failed"
        _job_store[job_id]["error"] = "Processing timed out"
    except Exception as e:
        logger.error(f"Background CommonForms processing failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        _job_store[job_id]["status"] = "failed"
        _job_store[job_id]["error"] = str(e)


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get the status of a CommonForms processing job.
    
    Returns:
    - status: queued | processing | completed | failed
    - outputPdfUrl: URL to download fillable PDF (if completed)
    - fields: List of detected fields (if completed)
    - error: Error message (if failed)
    """
    # Check in-memory store first
    if job_id in _job_store:
        job = _job_store[job_id]
        
        # If still processing, check if document is now ready
        if job["status"] == "processing":
            document_id = job["document_id"]
            document = db.query(Document).filter(
                Document.id == UUID(document_id)
            ).first()
            
            if document:
                if document.status == DocumentStatus.ready and document.storage_key_filled:
                    # Processing completed - update job store
                    storage = get_storage_service()
                    output_url = storage.generate_presigned_url(
                        key=document.storage_key_filled,
                        expires_in=3600
                    )
                    
                    # Get field regions
                    field_regions = db.query(FieldRegion).filter(
                        FieldRegion.document_id == document.id
                    ).all()
                    
                    fields = [
                        FieldInfo(
                            id=str(fr.id),
                            type=fr.field_type.value,
                            page=fr.page_index,
                            bbox=[fr.x, fr.y, fr.x + fr.width, fr.y + fr.height],
                            label=fr.label
                        )
                        for fr in field_regions
                    ]
                    
                    job["status"] = "completed"
                    job["output_pdf_url"] = output_url
                    job["fields"] = [f.model_dump() for f in fields]
                    
                    return JobStatusResponse(
                        status="completed",
                        outputPdfUrl=output_url,
                        fields=fields,
                        documentId=document_id
                    )
                
                elif document.status == DocumentStatus.failed:
                    job["status"] = "failed"
                    job["error"] = document.error_message
                    
                    return JobStatusResponse(
                        status="failed",
                        error=document.error_message,
                        documentId=document_id
                    )
        
        # Return current job status
        return JobStatusResponse(
            status=job["status"],
            outputPdfUrl=job.get("output_pdf_url"),
            fields=[FieldInfo(**f) for f in job.get("fields", [])],
            documentId=job.get("document_id"),
            error=job.get("error")
        )
    
    # Job not found in memory - check if document exists with completed status
    # This handles cases where the API restarted but processing completed
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Job not found"
    )


@router.post("/commonforms/{document_id}/sync", response_model=JobStatusResponse)
async def process_commonforms_sync(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Synchronous CommonForms processing (for testing/development).
    Processes the document immediately and returns results.
    
    WARNING: This is slow and should only be used for testing.
    Use the async endpoint (/commonforms/{document_id}) in production.
    """
    import tempfile
    import os
    
    # Validate document
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    storage = get_storage_service()
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = os.path.join(tmp_dir, "input.pdf")
        output_path = os.path.join(tmp_dir, "output.pdf")
        
        # Download original PDF
        await storage.download_to_path(
            key=document.storage_key_original,
            local_path=input_path
        )
        
        # Run CommonForms
        try:
            from commonforms import prepare_form
            
            # prepare_form creates fillable PDF
            prepare_form(
                input_path,
                output_path,
                model_or_path="FFDetr",
                confidence=0.4,
                device="cpu"
            )
            
            # Extract fields from generated PDF
            field_metadata = _extract_fields_from_pdf(output_path)
            
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CommonForms library not installed. Install: pip install git+https://github.com/jbarrow/commonforms.git"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"CommonForms error: {str(e)}"
            )
        
        # Upload output PDF
        output_key = f"commonforms/{document.user_id}/{document_id}/fillable.pdf"
        await storage.upload_file(
            local_path=output_path,
            key=output_key,
            content_type="application/pdf"
        )
        
        # Parse fields and save to DB
        fields = []
        for idx, field in enumerate(field_metadata):
            field_region = FieldRegion(
                document_id=document.id,
                page_index=field.get('page', 0),
                x=field.get('bbox', [0, 0, 1, 1])[0],
                y=field.get('bbox', [0, 0, 1, 1])[1],
                width=field.get('bbox', [0, 0, 1, 1])[2] - field.get('bbox', [0, 0, 1, 1])[0],
                height=field.get('bbox', [0, 0, 1, 1])[3] - field.get('bbox', [0, 0, 1, 1])[1],
                field_type=_map_field_type(field.get('type', 'text')),
                label=field.get('label', f'Field_{idx}'),
                confidence=1.0,
                template_key=field.get('name')
            )
            db.add(field_region)
            
            fields.append(FieldInfo(
                id=str(field_region.id),
                type=field.get('type', 'text'),
                page=field.get('page', 0),
                bbox=field.get('bbox', [0, 0, 1, 1]),
                label=field.get('label')
            ))
        
        # Update document
        document.status = DocumentStatus.ready
        document.storage_key_filled = output_key
        db.commit()
        
        # Generate presigned URL
        output_url = storage.generate_presigned_url(key=output_key, expires_in=3600)
        
        return JobStatusResponse(
            status="completed",
            outputPdfUrl=output_url,
            fields=fields
        )


def _extract_fields_from_pdf(pdf_path: str) -> list:
    """Extract AcroForm fields from CommonForms-generated PDF."""
    import fitz
    
    fields = []
    pdf_doc = fitz.open(pdf_path)
    
    try:
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            page_rect = page.rect
            
            for widget in page.widgets():
                if widget is None:
                    continue
                
                field_name = widget.field_name or f"field_{page_num}_{len(fields)}"
                field_type_code = widget.field_type
                rect = widget.rect
                
                # Map widget type
                if field_type_code == fitz.PDF_WIDGET_TYPE_TEXT:
                    field_type = "text"
                elif field_type_code == fitz.PDF_WIDGET_TYPE_BUTTON:
                    field_type = "checkbox"
                elif field_type_code == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    field_type = "signature"
                else:
                    field_type = "text"
                
                # Infer from CommonForms naming
                name_lower = field_name.lower()
                if "checkbox" in name_lower or "choicebutton" in name_lower:
                    field_type = "checkbox"
                elif "signature" in name_lower:
                    field_type = "signature"
                
                bbox = [
                    rect.x0 / page_rect.width,
                    rect.y0 / page_rect.height,
                    rect.x1 / page_rect.width,
                    rect.y1 / page_rect.height
                ]
                
                fields.append({
                    'page': page_num,
                    'type': field_type,
                    'bbox': bbox,
                    'label': field_name,
                    'name': field_name
                })
    finally:
        pdf_doc.close()
    
    return fields


def _map_field_type(cf_type: str):
    """Map CommonForms field type to FieldType enum."""
    from app.models.field import FieldType
    type_map = {
        'text': FieldType.text,
        'textarea': FieldType.multiline,
        'checkbox': FieldType.checkbox,
        'date': FieldType.date,
        'number': FieldType.number,
        'signature': FieldType.signature,
    }
    return type_map.get(cf_type.lower(), FieldType.text)


@router.post("/commonforms/{document_id}/mock", response_model=JobStatusResponse)
async def process_commonforms_mock(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Mock CommonForms processing for testing iOS integration.
    Returns the original PDF with fake detected fields.
    Does NOT require CommonForms library.
    """
    # Validate document
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    storage = get_storage_service()
    
    # Generate presigned URL for original PDF (as mock "fillable" PDF)
    output_url = storage.generate_presigned_url(
        key=document.storage_key_original,
        expires_in=3600
    )
    
    # Return mock fields for testing
    mock_fields = [
        FieldInfo(id="mock-field-1", type="text", page=0, bbox=[0.1, 0.1, 0.4, 0.15], label="Name"),
        FieldInfo(id="mock-field-2", type="text", page=0, bbox=[0.1, 0.2, 0.4, 0.25], label="Email"),
        FieldInfo(id="mock-field-3", type="date", page=0, bbox=[0.1, 0.3, 0.3, 0.35], label="Date"),
        FieldInfo(id="mock-field-4", type="checkbox", page=0, bbox=[0.1, 0.4, 0.15, 0.45], label="Agree to Terms"),
        FieldInfo(id="mock-field-5", type="signature", page=0, bbox=[0.1, 0.5, 0.5, 0.6], label="Signature"),
    ]
    
    logger.info(f"Mock CommonForms response for document {document_id}")
    
    return JobStatusResponse(
        status="completed",
        outputPdfUrl=output_url,
        fields=mock_fields
    )
