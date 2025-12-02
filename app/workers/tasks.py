from celery import Task
from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.field import FieldRegion, FieldValue, FieldType
from app.models.usage import EventType
from app.services.storage import get_storage_service
from app.services.ocr_dispatcher import get_ocr_backend
from app.services.pdf_compose import PDFComposer
from app.services.usage_tracker import UsageTracker
from app.utils.logging import get_logger
import tempfile
import os
from uuid import UUID

logger = get_logger(__name__)


class DatabaseTask(Task):
    """Base task with database session"""
    _db = None
    
    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db
    
    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=DatabaseTask, bind=True, queue="ocr")
def run_ocr(self, document_id: str):
    """
    Run OCR on a document and extract field regions.
    
    Args:
        document_id: UUID of the document to process
    """
    logger.info(f"Starting OCR for document {document_id}")
    
    try:
        # Fetch document
        doc = self.db.query(Document).filter(Document.id == UUID(document_id)).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return
        
        # Update status
        doc.status = DocumentStatus.processing
        self.db.commit()
        
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
                    label=box.text[:100],  # Use detected text as label
                    confidence=box.confidence
                )
                self.db.add(field_region)
            
            # Update document
            doc.status = DocumentStatus.ready
            doc.page_count = result.page_count
            self.db.commit()
            
            # Log usage
            UsageTracker.log_event(
                self.db,
                doc.user_id,
                EventType.ocr_run,
                value=1
            )
            UsageTracker.log_event(
                self.db,
                doc.user_id,
                EventType.pages_processed,
                value=result.page_count
            )
            
            logger.info(f"OCR completed for document {document_id}: {len(result.boxes)} fields found")
            
        finally:
            # Cleanup temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        logger.error(f"OCR failed for document {document_id}: {str(e)}")
        doc = self.db.query(Document).filter(Document.id == UUID(document_id)).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_message = str(e)
            self.db.commit()
        raise


@celery_app.task(base=DatabaseTask, bind=True, queue="compose")
def compose_pdf(self, document_id: str):
    """
    Compose a filled PDF with user-entered values.
    
    Args:
        document_id: UUID of the document to compose
    """
    logger.info(f"Starting PDF composition for document {document_id}")
    
    try:
        # Fetch document
        doc = self.db.query(Document).filter(Document.id == UUID(document_id)).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return
        
        # Update status
        doc.status = DocumentStatus.filling
        self.db.commit()
        
        # Fetch field regions and values
        field_regions = self.db.query(FieldRegion).filter(
            FieldRegion.document_id == doc.id
        ).all()
        
        field_values_list = self.db.query(FieldValue).filter(
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
            
            # Upload filled PDF (sync version for Celery)
            filled_key = f"filled/{document_id}.pdf"
            import asyncio
            asyncio.run(storage.upload_file(
                local_path=filled_path,
                key=filled_key,
                content_type="application/pdf"
            ))
            
            # Update document
            doc.storage_key_filled = filled_key
            doc.status = DocumentStatus.filled
            self.db.commit()
            
            # Log usage
            UsageTracker.log_event(
                self.db,
                doc.user_id,
                EventType.pdf_compose,
                value=1
            )
            
            logger.info(f"PDF composition completed for document {document_id}")
            
        finally:
            # Cleanup temp files
            if os.path.exists(original_path):
                os.unlink(original_path)
            if os.path.exists(filled_path):
                os.unlink(filled_path)
    
    except Exception as e:
        logger.error(f"PDF composition failed for document {document_id}: {str(e)}")
        doc = self.db.query(Document).filter(Document.id == UUID(document_id)).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_message = str(e)
            self.db.commit()
        raise


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
