"""
CommonForms Worker - Separate Cloud Run Service
Processes PDFs using CommonForms library to detect fields and generate fillable PDFs.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import sys
import tempfile
import json
from uuid import UUID, uuid4

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.field import FieldRegion, FieldType
from app.services.storage import get_storage_service
from app.utils.logging import get_logger

app = FastAPI(title="DocumentAI CommonForms Worker")
logger = get_logger(__name__)


class CommonFormsRequest(BaseModel):
    document_id: str
    job_id: str


class FieldData(BaseModel):
    id: str
    type: str
    page: int
    bbox: List[float]  # [x1, y1, x2, y2]
    label: Optional[str] = None


class CommonFormsResponse(BaseModel):
    job_id: str
    document_id: str
    status: str
    output_pdf_url: Optional[str] = None
    fields: List[FieldData] = []
    error: Optional[str] = None


@app.post("/process-commonforms", response_model=CommonFormsResponse)
async def process_commonforms(request: CommonFormsRequest):
    """
    Process PDF with CommonForms:
    1. Download original PDF from Supabase
    2. Run CommonForms prepare_form()
    3. Upload fillable PDF to Supabase
    4. Save field metadata to DB
    5. Update document status
    
    Called by Cloud Tasks.
    """
    document_id = request.document_id
    job_id = request.job_id
    logger.info(f"Starting CommonForms processing for document {document_id}, job {job_id}")
    
    db = SessionLocal()
    try:
        # Fetch document
        doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Update status to processing
        doc.status = DocumentStatus.processing
        db.commit()
        
        # Download file from storage
        storage = get_storage_service()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.pdf")
            output_path = os.path.join(tmp_dir, "output.pdf")
            
            # Download original PDF
            await storage.download_to_path(
                key=doc.storage_key_original,
                local_path=input_path
            )
            logger.info(f"Downloaded PDF from {doc.storage_key_original}")
            
            # Run CommonForms
            try:
                from commonforms import prepare_form
                
                # prepare_form creates fillable PDF (doesn't return metadata)
                prepare_form(
                    input_path,
                    output_path,
                    model_or_path="FFDetr",
                    confidence=0.4,
                    device="cpu"
                )
                logger.info("CommonForms prepare_form completed")
                
                # Extract field metadata from the generated PDF
                field_metadata = extract_fields_from_pdf(output_path)
                logger.info(f"Extracted {len(field_metadata)} fields from output PDF")
                
            except ImportError as e:
                logger.error(f"CommonForms not installed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="CommonForms library not installed. Install: pip install git+https://github.com/jbarrow/commonforms.git"
                )
            except Exception as e:
                logger.error(f"CommonForms processing failed: {e}")
                raise HTTPException(status_code=500, detail=f"CommonForms error: {str(e)}")
            
            # Upload output PDF to Supabase
            output_key = f"commonforms/{doc.user_id}/{document_id}/fillable.pdf"
            output_url = await storage.upload_file(
                local_path=output_path,
                key=output_key,
                content_type="application/pdf"
            )
            logger.info(f"Uploaded fillable PDF to {output_key}")
            
            # Save field regions to DB
            fields_response = []
            
            for field_data in field_metadata:
                # Save to database
                field_region = FieldRegion(
                    document_id=doc.id,
                    page_index=field_data['page'],
                    x=field_data['bbox'][0],
                    y=field_data['bbox'][1],
                    width=field_data['bbox'][2] - field_data['bbox'][0],
                    height=field_data['bbox'][3] - field_data['bbox'][1],
                    field_type=map_commonforms_type(field_data['type']),
                    label=field_data.get('label', 'Unnamed Field'),
                    confidence=1.0,  # CommonForms fields are definitive
                    template_key=field_data.get('name')
                )
                db.add(field_region)
                
                # Build response field
                fields_response.append(FieldData(
                    id=str(field_region.id),
                    type=field_data['type'],
                    page=field_data['page'],
                    bbox=field_data['bbox'],
                    label=field_data.get('label')
                ))
            
            # Update document
            doc.status = DocumentStatus.ready
            doc.storage_key_filled = output_key
            db.commit()
            
            logger.info(f"CommonForms processing completed for document {document_id}")
            
            # Generate presigned URL for response
            presigned_url = storage.generate_presigned_url(key=output_key, expires_in=3600)
            
            return CommonFormsResponse(
                job_id=job_id,
                document_id=document_id,
                status="completed",
                output_pdf_url=presigned_url,
                fields=fields_response
            )
    
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"CommonForms processing failed for document {document_id}: {error_msg}")
        
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        
        try:
            doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
            if doc:
                doc.status = DocumentStatus.failed
                doc.error_message = error_msg
                db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update document status: {db_error}")
        
        raise HTTPException(status_code=500, detail=error_msg)
    
    finally:
        db.close()


def extract_fields_from_pdf(pdf_path: str) -> List[Dict]:
    """
    Extract AcroForm fields from the CommonForms-generated PDF.
    CommonForms creates fillable PDFs with form fields that we can read.
    """
    import fitz  # PyMuPDF
    
    fields = []
    pdf_doc = fitz.open(pdf_path)
    
    try:
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            page_rect = page.rect
            
            # Get all widgets (form fields) on this page
            for widget in page.widgets():
                if widget is None:
                    continue
                
                field_name = widget.field_name or f"field_{page_num}_{len(fields)}"
                field_type_code = widget.field_type
                rect = widget.rect
                
                # Map PDF widget type to our field type
                if field_type_code == fitz.PDF_WIDGET_TYPE_TEXT:
                    field_type = "text"
                elif field_type_code == fitz.PDF_WIDGET_TYPE_BUTTON:
                    field_type = "checkbox"
                elif field_type_code == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    field_type = "signature"
                else:
                    field_type = "text"
                
                # Infer type from field name (CommonForms naming convention)
                name_lower = field_name.lower()
                if "checkbox" in name_lower or "choicebutton" in name_lower:
                    field_type = "checkbox"
                elif "signature" in name_lower:
                    field_type = "signature"
                elif "textbox" in name_lower:
                    field_type = "text"
                
                # Normalize bbox to [0,1] coordinates
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


def parse_commonforms_fields(field_metadata) -> List[Dict]:
    """
    Parse CommonForms field metadata into our format.
    CommonForms returns field info from prepare_form().
    """
    if not field_metadata:
        return []
    
    fields = []
    
    # Handle different CommonForms output formats
    if isinstance(field_metadata, list):
        for idx, field in enumerate(field_metadata):
            if isinstance(field, dict):
                fields.append({
                    'page': field.get('page', 0),
                    'type': field.get('type', 'text'),
                    'bbox': field.get('bbox', [0, 0, 100, 20]),
                    'label': field.get('label', field.get('name', f'Field_{idx}')),
                    'name': field.get('name', f'field_{idx}')
                })
    elif isinstance(field_metadata, dict):
        # If it's a dict with fields key
        if 'fields' in field_metadata:
            return parse_commonforms_fields(field_metadata['fields'])
        # Single field
        fields.append({
            'page': field_metadata.get('page', 0),
            'type': field_metadata.get('type', 'text'),
            'bbox': field_metadata.get('bbox', [0, 0, 100, 20]),
            'label': field_metadata.get('label', 'Field'),
            'name': field_metadata.get('name', 'field_0')
        })
    
    return fields


def map_commonforms_type(cf_type: str) -> FieldType:
    """Map CommonForms field type to our FieldType enum."""
    type_map = {
        'text': FieldType.text,
        'textarea': FieldType.multiline,
        'checkbox': FieldType.checkbox,
        'date': FieldType.date,
        'number': FieldType.number,
        'signature': FieldType.signature,
        'radio': FieldType.checkbox,
        'select': FieldType.text,
    }
    return type_map.get(cf_type.lower(), FieldType.text)


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "service": "commonforms-worker"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8081)))
