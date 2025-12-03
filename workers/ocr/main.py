"""
OCR Worker - Separate Cloud Run Service
Processes documents with PaddleOCR
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import sys
import tempfile
from uuid import UUID

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.field import FieldRegion, FieldType
from app.models.usage import UsageEvent, EventType
from app.services.storage import get_storage_service
from app.services.ocr_dispatcher import get_ocr_backend
from app.utils.logging import get_logger

app = FastAPI(title="DocumentAI OCR Worker")
logger = get_logger(__name__)


class OCRRequest(BaseModel):
    document_id: str


class OCRResponse(BaseModel):
    document_id: str
    status: str
    fields_found: int


@app.post("/ocr", response_model=OCRResponse)
async def process_ocr(request: OCRRequest):
    """
    Process document with PaddleOCR.
    Called by Cloud Tasks.
    """
    document_id = request.document_id
    logger.info(f"Starting OCR for document {document_id}")
    
    db = SessionLocal()
    try:
        # Fetch document
        doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Update status
        doc.status = DocumentStatus.processing
        db.commit()
        
        # Download file from storage
        storage = get_storage_service()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            import asyncio
            asyncio.run(storage.download_to_path(key=doc.storage_key_original, local_path=tmp_path))
            
            # Run OCR
            ocr_backend = get_ocr_backend()
            result = ocr_backend.run_ocr(tmp_path)
            
            # Process results and create field regions
            for box in result.boxes:
                # Simple heuristic: classify fields based on text content
                field_type = classify_field_type(box.text)
                
                field_region = FieldRegion(
                    document_id=doc.id,
                    page_index=box.page_index,
                    x=box.bbox[0],
                    y=box.bbox[1],
                    width=box.bbox[2],
                    height=box.bbox[3],
                    field_type=field_type,
                    label=box.text[:100],
                    confidence=box.confidence
                )
                db.add(field_region)
            
            # Update document
            doc.status = DocumentStatus.ready
            doc.page_count = result.page_count
            db.commit()
            
            # Log usage
            usage_event = UsageEvent(
                user_id=doc.user_id,
                event_type=EventType.ocr_run,
                value=1
            )
            db.add(usage_event)
            
            usage_event_pages = UsageEvent(
                user_id=doc.user_id,
                event_type=EventType.pages_processed,
                value=result.page_count
            )
            db.add(usage_event_pages)
            db.commit()
            
            logger.info(f"OCR completed for document {document_id}: {len(result.boxes)} fields found")
            
            return OCRResponse(
                document_id=document_id,
                status="ready",
                fields_found=len(result.boxes)
            )
            
        finally:
            # Cleanup temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        logger.error(f"OCR failed for document {document_id}: {str(e)}")
        doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        db.close()


def classify_field_type(text: str) -> FieldType:
    """Simple heuristic to classify field type based on text content"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['date', 'dob', 'birth']):
        return FieldType.date
    elif any(word in text_lower for word in ['check', 'yes', 'no', 'agree']):
        return FieldType.checkbox
    elif any(word in text_lower for word in ['signature', 'sign']):
        return FieldType.signature
    elif any(word in text_lower for word in ['amount', 'price', 'total', 'number', '#']):
        return FieldType.number
    elif len(text) > 50:
        return FieldType.multiline
    else:
        return FieldType.text


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "service": "ocr-worker"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
