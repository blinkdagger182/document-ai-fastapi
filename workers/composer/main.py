"""
PDF Composer Worker - Separate Cloud Run Service
Composes filled PDFs with user values
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
from app.models.field import FieldRegion, FieldValue
from app.models.usage import UsageEvent, EventType
from app.services.storage import get_storage_service
from app.services.pdf_compose import PDFComposer
from app.utils.logging import get_logger

app = FastAPI(title="DocumentAI PDF Composer")
logger = get_logger(__name__)


class ComposeRequest(BaseModel):
    document_id: str


class ComposeResponse(BaseModel):
    document_id: str
    status: str
    filled_pdf_key: str


@app.post("/compose", response_model=ComposeResponse)
async def compose_pdf(request: ComposeRequest):
    """
    Compose filled PDF with user values.
    Called by Cloud Tasks.
    """
    document_id = request.document_id
    logger.info(f"Starting PDF composition for document {document_id}")
    
    db = SessionLocal()
    try:
        # Fetch document
        doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Update status
        doc.status = DocumentStatus.filling
        db.commit()
        
        # Fetch field regions and values
        field_regions = db.query(FieldRegion).filter(
            FieldRegion.document_id == doc.id
        ).all()
        
        field_values_list = db.query(FieldValue).filter(
            FieldValue.document_id == doc.id
        ).all()
        
        # Create value map
        value_map = {fv.field_region_id: fv.value for fv in field_values_list}
        
        # Download original PDF
        storage = get_storage_service()
        with tempfile.NamedTemporaryFile(delete=False, suffix="_original.pdf") as tmp_orig:
            original_path = tmp_orig.name
        
        with tempfile.NamedTemporaryFile(delete=False, suffix="_filled.pdf") as tmp_filled:
            filled_path = tmp_filled.name
        
        try:
            import asyncio
            asyncio.run(storage.download_to_path(key=doc.storage_key_original, local_path=original_path))
            
            # Compose PDF
            composer = PDFComposer()
            composer.compose_pdf(
                original_pdf_path=original_path,
                output_pdf_path=filled_path,
                field_regions=field_regions,
                field_values=value_map
            )
            
            # Upload filled PDF
            filled_key = f"filled/{document_id}.pdf"
            asyncio.run(storage.upload_file(
                local_path=filled_path,
                key=filled_key,
                content_type="application/pdf"
            ))
            
            # Update document
            doc.storage_key_filled = filled_key
            doc.status = DocumentStatus.filled
            db.commit()
            
            # Log usage
            usage_event = UsageEvent(
                user_id=doc.user_id,
                event_type=EventType.pdf_compose,
                value=1
            )
            db.add(usage_event)
            db.commit()
            
            logger.info(f"PDF composition completed for document {document_id}")
            
            return ComposeResponse(
                document_id=document_id,
                status="filled",
                filled_pdf_key=filled_key
            )
            
        finally:
            # Cleanup temp files
            if os.path.exists(original_path):
                os.unlink(original_path)
            if os.path.exists(filled_path):
                os.unlink(filled_path)
    
    except Exception as e:
        logger.error(f"PDF composition failed for document {document_id}: {str(e)}")
        doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        db.close()


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "service": "pdf-composer"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
