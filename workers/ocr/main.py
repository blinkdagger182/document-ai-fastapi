"""
Hybrid OCR Worker - Separate Cloud Run Service
1. Detects AcroForm fields first (precise PDF coordinates)
2. Falls back to PaddleOCR if no AcroForm found
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import sys
import tempfile
from uuid import UUID
import fitz  # PyMuPDF

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.field import FieldRegion, FieldType
from app.models.usage import UsageEvent, EventType
from app.services.storage import get_storage_service
from app.utils.logging import get_logger

app = FastAPI(title="DocumentAI Hybrid OCR Worker")
logger = get_logger(__name__)


class OCRRequest(BaseModel):
    document_id: str


class FieldRegionData(BaseModel):
    page_index: int
    x: float
    y: float
    width: float
    height: float
    field_type: str
    label: str
    confidence: float
    template_key: Optional[str] = None


class OCRResponse(BaseModel):
    document_id: str
    status: str
    acroform: bool
    fields_found: int
    page_count: int
    field_regions: List[FieldRegionData]


@app.post("/ocr", response_model=OCRResponse)
async def process_ocr(request: OCRRequest):
    """
    Hybrid OCR processing:
    1. Try AcroForm detection first (precise PDF fields)
    2. Fallback to PaddleOCR if no AcroForm found
    
    Called by Cloud Tasks.
    """
    document_id = request.document_id
    logger.info(f"Starting hybrid OCR for document {document_id}")
    
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
            await storage.download_to_path(key=doc.storage_key_original, local_path=tmp_path)
            
            # Open PDF with PyMuPDF
            pdf_doc = fitz.open(tmp_path)
            page_count = len(pdf_doc)
            
            # Step 1: Try AcroForm detection
            field_regions_data = []
            acroform_detected = False
            
            acroform_fields = detect_acroform_fields(pdf_doc)
            
            if acroform_fields:
                logger.info(f"AcroForm detected: {len(acroform_fields)} fields found")
                acroform_detected = True
                field_regions_data = acroform_fields
            else:
                # Step 2: Fallback to OCR
                logger.info("No AcroForm found, falling back to OCR")
                ocr_fields = detect_ocr_fields(pdf_doc, tmp_path)
                field_regions_data = ocr_fields
            
            pdf_doc.close()
            
            # Save field regions to database
            for field_data in field_regions_data:
                field_region = FieldRegion(
                    document_id=doc.id,
                    page_index=field_data['page_index'],
                    x=field_data['x'],
                    y=field_data['y'],
                    width=field_data['width'],
                    height=field_data['height'],
                    field_type=FieldType[field_data['field_type']],
                    label=field_data['label'],
                    confidence=field_data['confidence'],
                    template_key=field_data.get('template_key')
                )
                db.add(field_region)
            
            # Update document
            doc.status = DocumentStatus.ready
            doc.page_count = page_count
            doc.acroform = acroform_detected
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
                value=page_count
            )
            db.add(usage_event_pages)
            db.commit()
            
            logger.info(f"Processing completed for document {document_id}: {len(field_regions_data)} fields found (AcroForm: {acroform_detected})")
            
            # Build response
            response_fields = [
                FieldRegionData(
                    page_index=f['page_index'],
                    x=f['x'],
                    y=f['y'],
                    width=f['width'],
                    height=f['height'],
                    field_type=f['field_type'],
                    label=f['label'],
                    confidence=f['confidence'],
                    template_key=f.get('template_key')
                )
                for f in field_regions_data
            ]
            
            return OCRResponse(
                document_id=document_id,
                status="ready",
                acroform=acroform_detected,
                fields_found=len(field_regions_data),
                page_count=page_count,
                field_regions=response_fields
            )
            
        finally:
            # Cleanup temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Processing failed for document {document_id}: {error_msg}")
        import traceback
        traceback_str = traceback.format_exc()
        logger.error(f"Full traceback:\n{traceback_str}")
        print(f"ERROR: {error_msg}")  # Force print to stdout
        print(f"TRACEBACK:\n{traceback_str}")  # Force print to stdout
        
        try:
            doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
            if doc:
                doc.status = DocumentStatus.failed
                doc.error_message = error_msg
                db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update document status: {db_error}")
            print(f"DB ERROR: {db_error}")
        
        raise HTTPException(status_code=500, detail=error_msg)
    
    finally:
        db.close()


def detect_acroform_fields(pdf_doc: fitz.Document) -> List[Dict]:
    """
    Detect AcroForm fields in PDF.
    Returns list of field data dicts with normalized coordinates.
    """
    field_regions = []
    
    try:
        # Check if PDF has AcroForm
        if not pdf_doc.is_form_pdf:
            logger.info("PDF does not contain AcroForm")
            return []
        
        # Iterate through all pages
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            page_rect = page.rect
            
            # Get all widgets (form fields) on this page
            widgets = page.widgets()
            
            if not widgets:
                continue
            
            for widget in widgets:
                try:
                    # Get field properties
                    field_name = widget.field_name or "Unnamed Field"
                    field_type_code = widget.field_type  # 1=Text, 2=Button, 3=Choice, 4=Signature
                    field_value = widget.field_value or ""
                    rect = widget.rect
                    
                    # Map PDF field type to our FieldType
                    if field_type_code == fitz.PDF_WIDGET_TYPE_TEXT:
                        # Check if multiline
                        if widget.field_flags & (1 << 12):  # Multiline flag
                            field_type = "multiline"
                        else:
                            field_type = classify_field_type_from_name(field_name)
                    elif field_type_code == fitz.PDF_WIDGET_TYPE_BUTTON:
                        # Check if checkbox or radio
                        if widget.field_flags & (1 << 15):  # Radio button
                            field_type = "checkbox"
                        else:
                            field_type = "checkbox"
                    elif field_type_code == fitz.PDF_WIDGET_TYPE_COMBOBOX or field_type_code == fitz.PDF_WIDGET_TYPE_LISTBOX:
                        field_type = "text"  # Treat as text for now
                    elif field_type_code == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                        field_type = "signature"
                    else:
                        field_type = "text"
                    
                    # Normalize coordinates [0,1]
                    x = rect.x0 / page_rect.width
                    y = rect.y0 / page_rect.height
                    width = rect.width / page_rect.width
                    height = rect.height / page_rect.height
                    
                    field_regions.append({
                        'page_index': page_num,
                        'x': x,
                        'y': y,
                        'width': width,
                        'height': height,
                        'field_type': field_type,
                        'label': field_name,
                        'confidence': 1.0,  # AcroForm fields are 100% confident
                        'template_key': field_name  # Use field name as template key
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing widget: {str(e)}")
                    continue
        
        logger.info(f"AcroForm detection found {len(field_regions)} fields")
        return field_regions
        
    except Exception as e:
        logger.error(f"AcroForm detection failed: {str(e)}")
        return []


def detect_ocr_fields(pdf_doc: fitz.Document, pdf_path: str) -> List[Dict]:
    """
    Fallback OCR detection using PaddleOCR.
    Returns list of field data dicts with normalized coordinates.
    """
    field_regions = []
    
    try:
        from paddleocr import PaddleOCR
        from PIL import Image
        import io
        
        ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
        
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            page_rect = page.rect
            
            # Render page to image
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            
            # Run PaddleOCR
            result = ocr.ocr(img_bytes, cls=True)
            
            if result and result[0]:
                for line in result[0]:
                    bbox_points = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    text_info = line[1]  # (text, confidence)
                    
                    # Convert to normalized coordinates [0,1]
                    x_coords = [p[0] for p in bbox_points]
                    y_coords = [p[1] for p in bbox_points]
                    x = min(x_coords) / pix.width
                    y = min(y_coords) / pix.height
                    width = (max(x_coords) - min(x_coords)) / pix.width
                    height = (max(y_coords) - min(y_coords)) / pix.height
                    
                    # Classify field type based on text
                    field_type = classify_field_type_from_text(text_info[0])
                    
                    field_regions.append({
                        'page_index': page_num,
                        'x': x,
                        'y': y,
                        'width': width,
                        'height': height,
                        'field_type': field_type,
                        'label': text_info[0][:100],
                        'confidence': text_info[1],
                        'template_key': None
                    })
        
        logger.info(f"OCR detection found {len(field_regions)} fields")
        return field_regions
        
    except Exception as e:
        logger.error(f"OCR detection failed: {str(e)}")
        return []


def classify_field_type_from_name(field_name: str) -> str:
    """Classify field type based on field name (for AcroForm)"""
    name_lower = field_name.lower()
    
    if any(word in name_lower for word in ['date', 'dob', 'birth', 'day', 'month', 'year']):
        return "date"
    elif any(word in name_lower for word in ['email', 'mail']):
        return "text"
    elif any(word in name_lower for word in ['phone', 'tel', 'mobile', 'number']):
        return "number"
    elif any(word in name_lower for word in ['signature', 'sign']):
        return "signature"
    elif any(word in name_lower for word in ['address', 'street', 'city', 'state', 'zip', 'comment', 'note', 'description']):
        return "multiline"
    else:
        return "text"


def classify_field_type_from_text(text: str) -> str:
    """Classify field type based on OCR text content"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['date', 'dob', 'birth']):
        return "date"
    elif any(word in text_lower for word in ['check', 'yes', 'no', 'agree']):
        return "checkbox"
    elif any(word in text_lower for word in ['signature', 'sign']):
        return "signature"
    elif any(word in text_lower for word in ['amount', 'price', 'total', 'number', '#']):
        return "number"
    elif len(text) > 50:
        return "multiline"
    else:
        return "text"


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "service": "ocr-worker"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
