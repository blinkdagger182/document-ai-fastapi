"""
Vision-based Form Field Detection Worker

This module implements Step 2 of the DocumentAI system: Vision-based field detection
for PDFs that do NOT have native AcroForm fields.

How it works:
1. Renders each PDF page to a high-resolution image (150-200 DPI)
2. Sends the image to a Vision LLM (GPT-4o-mini or Gemini Flash)
3. Receives JSON with detected fields and bounding boxes in 0-1000 coordinate system
4. Converts bboxes to normalized coordinates (0-1) for storage
5. Saves field_regions to Postgres

Coordinate System:
- Vision model uses: (0,0) = bottom-left, (1000,1000) = top-right
- Database stores: normalized coordinates where x, y, width, height are in [0, 1]
- Conversion: x_norm = x_min / 1000.0, width_norm = (x_max - x_min) / 1000.0
"""

import os
import sys
import json
import base64
import tempfile
from typing import List, Dict, Optional, Literal
from uuid import UUID
import fitz  # PyMuPDF
from io import BytesIO

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.field import FieldRegion, FieldType
from app.services.storage import get_storage_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


# Vision prompt for the LLM
VISION_PROMPT = """You are a document form field detection engine. Your job is to find every place a human is supposed to type, tick, or sign on this form page.

You MUST:
- Look for empty boxes, underlines, table cells, or whitespace aligned with labels.
- Treat "fill-in-the-blank" lines, rectangular boxes, and empty cells as input fields.
- Include checkboxes and signature areas.

For each field you detect, return JSON with:
- id: a short unique string (like "field_001").
- type: one of "text" | "textarea" | "checkbox" | "signature" | "date" | "number" | "unknown".
- label: the human-readable label, e.g. "Full Name", "NRIC No.", "Marital Status".
- bbox: bounding box as [x_min, y_min, x_max, y_max] in a 0–1000 relative grid, where (0,0) is bottom-left of the page and (1000,1000) is top-right.

Important details:
- Ignore decorative text and headings that are not directly associated with an input field.
- If multiple small boxes form one logical field (e.g., individual NRIC digits), treat them as one field that covers the whole group.
- For checkboxes with labels, return the bbox of the checkbox itself and include the label text.

Output format (JSON only, no explanations):
{
  "page_index": <zero_based_page_index>,
  "fields": [
    {
      "id": "field_001",
      "type": "text",
      "label": "Name (as per NRIC)",
      "bbox": [100, 120, 600, 160]
    },
    {
      "id": "field_002",
      "type": "checkbox",
      "label": "Single",
      "bbox": [120, 300, 150, 330]
    }
  ]
}"""


class VisionFieldDetector:
    """
    Vision-based field detector using multimodal LLMs.
    Supports OpenAI GPT-4o-mini and Google Gemini Flash.
    """
    
    def __init__(
        self,
        provider: Literal["openai", "gemini"] = "openai",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dpi: int = 150
    ):
        """
        Initialize the vision field detector.
        
        Args:
            provider: LLM provider ("openai" or "gemini")
            api_key: API key for the provider (defaults to env var)
            model: Model name (defaults to gpt-4o-mini or gemini-1.5-flash)
            dpi: DPI for PDF rendering (default 150)
        """
        self.provider = provider
        self.dpi = dpi
        
        if provider == "openai":
            import openai
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self.model = model or "gpt-4o-mini"
            self.client = openai.OpenAI(api_key=self.api_key)
        elif provider == "gemini":
            import google.generativeai as genai
            self.api_key = api_key or os.getenv("GEMINI_API_KEY")
            self.model = model or "gemini-1.5-flash"
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        logger.info(f"Initialized VisionFieldDetector with provider={provider}, model={self.model}")
    
    def render_page_to_image(self, page: fitz.Page) -> bytes:
        """
        Render a PDF page to a high-resolution PNG image.
        
        Args:
            page: PyMuPDF page object
            
        Returns:
            PNG image as bytes
        """
        # Calculate zoom factor for desired DPI
        # PyMuPDF default is 72 DPI, so zoom = target_dpi / 72
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        
        # Render to pixmap
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Convert to PNG bytes
        img_bytes = pix.tobytes("png")
        
        logger.debug(f"Rendered page to {pix.width}x{pix.height} image ({len(img_bytes)} bytes)")
        return img_bytes
    
    def call_vision_model(self, image_bytes: bytes, page_index: int) -> Dict:
        """
        Call the vision model to detect form fields in an image.
        
        Args:
            image_bytes: PNG image bytes
            page_index: Zero-based page index
            
        Returns:
            Parsed JSON response with detected fields
        """
        if self.provider == "openai":
            return self._call_openai(image_bytes, page_index)
        elif self.provider == "gemini":
            return self._call_gemini(image_bytes, page_index)
    
    def _call_openai(self, image_bytes: bytes, page_index: int) -> Dict:
        """Call OpenAI GPT-4o-mini vision API"""
        # Encode image to base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.1  # Low temperature for consistent detection
            )
            
            # Extract JSON from response
            content = response.choices[0].message.content
            
            # Try to parse JSON (handle markdown code blocks)
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            result = json.loads(content)
            logger.info(f"OpenAI detected {len(result.get('fields', []))} fields on page {page_index}")
            return result
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}")
            raise
    
    def _call_gemini(self, image_bytes: bytes, page_index: int) -> Dict:
        """Call Google Gemini Flash vision API"""
        from PIL import Image
        
        try:
            # Load image from bytes
            img = Image.open(BytesIO(image_bytes))
            
            # Generate content
            response = self.client.generate_content([
                VISION_PROMPT,
                img
            ])
            
            # Extract JSON from response
            content = response.text.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            result = json.loads(content)
            logger.info(f"Gemini detected {len(result.get('fields', []))} fields on page {page_index}")
            return result
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {str(e)}")
            raise
    
    def normalize_bbox(self, bbox: List[int]) -> Dict[str, float]:
        """
        Convert vision model bbox (0-1000 coordinate system) to normalized coordinates (0-1).
        
        Vision model coordinate system:
        - (0, 0) = bottom-left
        - (1000, 1000) = top-right
        - bbox = [x_min, y_min, x_max, y_max]
        
        Database coordinate system:
        - x, y = bottom-left corner (normalized 0-1)
        - width, height = dimensions (normalized 0-1)
        
        Args:
            bbox: [x_min, y_min, x_max, y_max] in 0-1000 range
            
        Returns:
            Dict with x, y, width, height in 0-1 range
        """
        x_min, y_min, x_max, y_max = bbox
        
        # Normalize to 0-1 range
        x = x_min / 1000.0
        y = y_min / 1000.0
        width = (x_max - x_min) / 1000.0
        height = (y_max - y_min) / 1000.0
        
        # Validate ranges
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        width = max(0.0, min(1.0 - x, width))
        height = max(0.0, min(1.0 - y, height))
        
        return {
            'x': x,
            'y': y,
            'width': width,
            'height': height
        }
    
    def map_field_type(self, vision_type: str) -> str:
        """
        Map vision model field type to our FieldType enum.
        
        Args:
            vision_type: Field type from vision model
            
        Returns:
            FieldType enum value as string
        """
        type_mapping = {
            'text': 'text',
            'textarea': 'multiline',
            'checkbox': 'checkbox',
            'signature': 'signature',
            'date': 'date',
            'number': 'number',
            'unknown': 'unknown'
        }
        return type_mapping.get(vision_type.lower(), 'unknown')
    
    def detect_form_fields(self, document_id: str, force: bool = False) -> Dict:
        """
        Main entry point: Detect form fields in a PDF document using vision AI.
        
        This function:
        1. Loads the document from storage
        2. Renders each page to an image
        3. Calls the vision model to detect fields
        4. Normalizes coordinates and saves to database
        
        Args:
            document_id: UUID of the document to process
            force: If True, re-process even if fields already exist
            
        Returns:
            Dict with processing results
        """
        logger.info(f"Starting vision field detection for document {document_id}")
        
        db = SessionLocal()
        try:
            # Fetch document
            doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
            if not doc:
                raise ValueError(f"Document {document_id} not found")
            
            # Check if already processed (unless force=True)
            if not force:
                existing_fields = db.query(FieldRegion).filter(
                    FieldRegion.document_id == doc.id
                ).count()
                
                if existing_fields > 0:
                    logger.info(f"Document {document_id} already has {existing_fields} fields, skipping (use force=True to re-process)")
                    return {
                        'document_id': document_id,
                        'status': 'skipped',
                        'reason': 'already_processed',
                        'existing_fields': existing_fields
                    }
            else:
                # Delete existing fields if force=True
                db.query(FieldRegion).filter(FieldRegion.document_id == doc.id).delete()
                db.commit()
                logger.info(f"Deleted existing fields for document {document_id}")
            
            # Update status
            doc.status = DocumentStatus.processing
            db.commit()
            
            # Download file from storage
            storage = get_storage_service()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_path = tmp_file.name
            
            try:
                # Download PDF
                storage.download_to_path(key=doc.storage_key_original, local_path=tmp_path)
                
                # Open PDF with PyMuPDF
                pdf_doc = fitz.open(tmp_path)
                page_count = len(pdf_doc)
                
                logger.info(f"Processing {page_count} pages for document {document_id}")
                
                # Process each page
                all_fields = []
                for page_num in range(page_count):
                    logger.info(f"Processing page {page_num + 1}/{page_count}")
                    
                    page = pdf_doc[page_num]
                    
                    # Render page to image
                    image_bytes = self.render_page_to_image(page)
                    
                    # Call vision model
                    try:
                        result = self.call_vision_model(image_bytes, page_num)
                        
                        # Validate response structure
                        if 'fields' not in result:
                            logger.warning(f"No 'fields' key in response for page {page_num}")
                            continue
                        
                        # Process each detected field
                        for field_data in result['fields']:
                            try:
                                # Normalize bbox
                                bbox = field_data.get('bbox', [])
                                if len(bbox) != 4:
                                    logger.warning(f"Invalid bbox format: {bbox}")
                                    continue
                                
                                coords = self.normalize_bbox(bbox)
                                
                                # Map field type
                                field_type = self.map_field_type(field_data.get('type', 'unknown'))
                                
                                # Create field region
                                field_region = {
                                    'page_index': page_num,
                                    'x': coords['x'],
                                    'y': coords['y'],
                                    'width': coords['width'],
                                    'height': coords['height'],
                                    'field_type': field_type,
                                    'label': field_data.get('label', 'Unnamed Field')[:255],  # Truncate if too long
                                    'confidence': 0.85,  # Vision model confidence (can be adjusted)
                                    'template_key': field_data.get('id')  # Use field ID as template key
                                }
                                
                                all_fields.append(field_region)
                                
                            except Exception as e:
                                logger.error(f"Error processing field on page {page_num}: {str(e)}")
                                continue
                    
                    except Exception as e:
                        logger.error(f"Error processing page {page_num}: {str(e)}")
                        continue
                
                pdf_doc.close()
                
                # Save all fields to database
                logger.info(f"Saving {len(all_fields)} fields to database")
                for field_data in all_fields:
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
                
                # Update document status
                doc.status = DocumentStatus.ready
                doc.page_count = page_count
                doc.acroform = False  # Vision detection means no AcroForm
                db.commit()
                
                logger.info(f"Vision field detection completed for document {document_id}: {len(all_fields)} fields found")
                
                return {
                    'document_id': document_id,
                    'status': 'success',
                    'page_count': page_count,
                    'fields_found': len(all_fields),
                    'fields_by_page': {
                        page_num: len([f for f in all_fields if f['page_index'] == page_num])
                        for page_num in range(page_count)
                    }
                }
                
            finally:
                # Cleanup temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Vision field detection failed for document {document_id}: {error_msg}")
            
            try:
                doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
                if doc:
                    doc.status = DocumentStatus.failed
                    doc.error_message = error_msg
                    db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update document status: {db_error}")
            
            raise
        
        finally:
            db.close()


# Convenience functions for direct usage

def detect_fields_openai(document_id: str, api_key: Optional[str] = None, force: bool = False) -> Dict:
    """
    Detect form fields using OpenAI GPT-4o-mini.
    
    Args:
        document_id: UUID of the document
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        force: Re-process even if fields exist
        
    Returns:
        Processing results dict
    """
    detector = VisionFieldDetector(provider="openai", api_key=api_key)
    return detector.detect_form_fields(document_id, force=force)


def detect_fields_gemini(document_id: str, api_key: Optional[str] = None, force: bool = False) -> Dict:
    """
    Detect form fields using Google Gemini Flash.
    
    Args:
        document_id: UUID of the document
        api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        force: Re-process even if fields exist
        
    Returns:
        Processing results dict
    """
    detector = VisionFieldDetector(provider="gemini", api_key=api_key)
    return detector.detect_form_fields(document_id, force=force)


if __name__ == "__main__":
    """
    CLI usage:
    python vision_field_detector.py <document_id> [--provider openai|gemini] [--force]
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Vision-based form field detection")
    parser.add_argument("document_id", help="Document UUID")
    parser.add_argument("--provider", choices=["openai", "gemini"], default="openai", help="Vision model provider")
    parser.add_argument("--force", action="store_true", help="Re-process even if fields exist")
    parser.add_argument("--api-key", help="API key (defaults to env var)")
    
    args = parser.parse_args()
    
    detector = VisionFieldDetector(provider=args.provider, api_key=args.api_key)
    result = detector.detect_form_fields(args.document_id, force=args.force)
    
    print(json.dumps(result, indent=2))
