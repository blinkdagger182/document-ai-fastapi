"""
CommonForms Worker - Cloud Run Service
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
    bbox: List[float]
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
    """
    document_id = request.document_id
    job_id = request.job_id
    logger.info(f"[CF-WORKER] Starting CommonForms processing for document {document_id}, job {job_id}")
    
    db = SessionLocal()
    try:
        # Step 1: Fetch document metadata from Supabase
        logger.info(f"[CF-WORKER] Step 1: Fetching document metadata")
        doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
        if not doc:
            logger.error(f"[CF-WORKER] Document not found: {document_id}")
            raise HTTPException(status_code=404, detail="Document not found")
        
        logger.info(f"[CF-WORKER] Found document: {doc.file_name}, storage_key: {doc.storage_key_original}")
        
        # Update status to processing
        doc.status = DocumentStatus.processing
        db.commit()
        logger.info(f"[CF-WORKER] Updated document status to processing")
        
        # Step 2: Download PDF from storage
        storage = get_storage_service()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.pdf")
            output_path = os.path.join(tmp_dir, "output.pdf")
            
            logger.info(f"[CF-WORKER] Step 2: Downloading PDF from {doc.storage_key_original}")
            await storage.download_to_path(
                key=doc.storage_key_original,
                local_path=input_path
            )
            logger.info(f"[CF-WORKER] Downloaded PDF to {input_path}")
            
            # Verify file exists and has content
            file_size = os.path.getsize(input_path)
            logger.info(f"[CF-WORKER] Input PDF size: {file_size} bytes")
            
            # Step 3: Run CommonForms prepare_form()
            logger.info(f"[CF-WORKER] Step 3: Running CommonForms prepare_form()")
            try:
                from commonforms import prepare_form
                
                prepare_form(
                    input_path,
                    output_path,
                    model_or_path="FFDetr",
                    confidence=0.4,
                    device="cpu"
                )
                logger.info(f"[CF-WORKER] CommonForms prepare_form() completed successfully")
                
                # Verify output exists
                if not os.path.exists(output_path):
                    raise Exception("CommonForms did not generate output PDF")
                
                output_size = os.path.getsize(output_path)
                logger.info(f"[CF-WORKER] Output PDF size: {output_size} bytes")
                
            except ImportError as e:
                logger.error(f"[CF-WORKER] CommonForms not installed: {e}")
                doc.status = DocumentStatus.failed
                doc.error_message = "CommonForms library not installed"
                db.commit()
                raise HTTPException(
                    status_code=500,
                    detail="CommonForms library not installed"
                )
            except Exception as e:
                logger.error(f"[CF-WORKER] CommonForms processing failed: {e}")
                doc.status = DocumentStatus.failed
                doc.error_message = f"CommonForms error: {str(e)}"
                db.commit()
                raise HTTPException(status_code=500, detail=f"CommonForms error: {str(e)}")
            
            # Step 4: Extract field metadata from generated PDF
            logger.info(f"[CF-WORKER] Step 4: Extracting fields from output PDF")
            field_metadata = extract_fields_from_pdf(output_path)
            logger.info(f"[CF-WORKER] Extracted {len(field_metadata)} fields")
            
            # Step 5: Upload output PDF to Supabase Storage
            logger.info(f"[CF-WORKER] Step 5: Uploading fillable PDF to Supabase")
            output_key = f"commonforms/{doc.user_id}/{document_id}/fillable.pdf"
            output_url = await storage.upload_file(
                local_path=output_path,
                key=output_key,
                content_type="application/pdf"
            )
            logger.info(f"[CF-WORKER] Uploaded fillable PDF to {output_key}")
            
            # Step 6: Save field regions to DB
            logger.info(f"[CF-WORKER] Step 6: Saving field regions to database")
            fields_response = []
            
            for idx, field_data in enumerate(field_metadata):
                field_region = FieldRegion(
                    document_id=doc.id,
                    page_index=field_data['page'],
                    x=field_data['bbox'][0],
                    y=field_data['bbox'][1],
                    width=field_data['bbox'][2] - field_data['bbox'][0],
                    height=field_data['bbox'][3] - field_data['bbox'][1],
                    field_type=map_commonforms_type(field_data['type']),
                    label=field_data.get('label', f'Field_{idx}'),
                    confidence=1.0,
                    template_key=field_data.get('name')
                )
                db.add(field_region)
                db.flush()  # Get the ID
                
                fields_response.append(FieldData(
                    id=str(field_region.id),
                    type=field_data['type'],
                    page=field_data['page'],
                    bbox=field_data['bbox'],
                    label=field_data.get('label')
                ))
                logger.info(f"[CF-WORKER] Saved field: {field_data.get('label', f'Field_{idx}')} ({field_data['type']})")
            
            # Step 7: Update document status
            logger.info(f"[CF-WORKER] Step 7: Updating document status to ready")
            doc.status = DocumentStatus.ready
            doc.storage_key_filled = output_key
            db.commit()
            
            # Generate presigned URL for response
            presigned_url = storage.generate_presigned_url(key=output_key, expires_in=3600)
            
            logger.info(f"[CF-WORKER] ✅ CommonForms processing completed successfully")
            logger.info(f"[CF-WORKER] Output URL: {presigned_url}")
            logger.info(f"[CF-WORKER] Fields detected: {len(fields_response)}")
            
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
        logger.error(f"[CF-WORKER] ❌ Processing failed: {error_msg}")
        
        import traceback
        logger.error(f"[CF-WORKER] Traceback:\n{traceback.format_exc()}")
        
        try:
            doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
            if doc:
                doc.status = DocumentStatus.failed
                doc.error_message = error_msg
                db.commit()
        except Exception as db_error:
            logger.error(f"[CF-WORKER] Failed to update document status: {db_error}")
        
        raise HTTPException(status_code=500, detail=error_msg)
    
    finally:
        db.close()


def extract_fields_from_pdf(pdf_path: str) -> List[Dict]:
    """
    Extract AcroForm fields from the CommonForms-generated PDF.
    """
    import fitz  # PyMuPDF
    
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
                
                # Map PDF widget type
                if field_type_code == fitz.PDF_WIDGET_TYPE_TEXT:
                    field_type = "text"
                elif field_type_code == fitz.PDF_WIDGET_TYPE_BUTTON:
                    field_type = "checkbox"
                elif field_type_code == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    field_type = "signature"
                else:
                    field_type = "text"
                
                # Infer from CommonForms naming convention
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


def map_commonforms_type(cf_type: str) -> FieldType:
    """Map CommonForms field type to FieldType enum."""
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
    """Health check endpoint"""
    return {"status": "ok", "service": "commonforms-worker"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8081)))
