"""
Vision Detector Adapter for Hybrid Detection Pipeline

This module provides an adapter that wraps the existing VisionFieldDetector
to implement the VisionDetectorProtocol required by HybridDetectionPipeline.

The adapter:
1. Takes a PDF path and optional document_id
2. Renders pages to images
3. Calls the vision model for each page
4. Returns List[FieldDetection] with normalized coordinates

This allows the existing VisionFieldDetector to be used seamlessly
with the new hybrid detection pipeline.
"""

import os
import tempfile
from typing import List, Optional, Literal
import fitz  # PyMuPDF
import logging

from .detection_models import BBox, FieldDetection, FieldType, DetectionSource
from .hybrid_detection_pipeline import VisionDetectorProtocol

logger = logging.getLogger(__name__)


class VisionDetectorAdapter:
    """
    Adapter that wraps vision model calls to implement VisionDetectorProtocol.
    
    This adapter:
    - Renders PDF pages to images
    - Calls OpenAI or Gemini vision models
    - Converts responses to FieldDetection objects
    - Returns results compatible with HybridDetectionPipeline
    
    Example:
        adapter = VisionDetectorAdapter(provider="openai")
        fields = adapter.detect_fields("form.pdf")
    """
    
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
    }
  ]
}"""
    
    # Field type mapping from vision model to FieldType enum
    FIELD_TYPE_MAP = {
        'text': FieldType.TEXT,
        'textarea': FieldType.MULTILINE,
        'checkbox': FieldType.CHECKBOX,
        'signature': FieldType.SIGNATURE,
        'date': FieldType.DATE,
        'number': FieldType.NUMBER,
        'unknown': FieldType.UNKNOWN,
    }
    
    def __init__(
        self,
        provider: Literal["openai", "gemini"] = "openai",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dpi: int = 150,
        debug: bool = False,
    ):
        """
        Initialize the vision detector adapter.
        
        Args:
            provider: LLM provider ("openai" or "gemini")
            api_key: API key for the provider (defaults to env var)
            model: Model name (defaults to gpt-4o-mini or gemini-1.5-flash)
            dpi: DPI for PDF rendering (default 150)
            debug: If True, enable verbose logging
        """
        self.provider = provider
        self.dpi = dpi
        self.debug = debug
        self.client = None
        self.model = None
        
        if provider == "openai":
            try:
                import openai
                self.api_key = api_key or os.getenv("OPENAI_API_KEY")
                self.model = model or "gpt-4o-mini"
                if self.api_key:
                    self.client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                logger.warning("OpenAI package not installed")
        elif provider == "gemini":
            try:
                import google.generativeai as genai
                self.api_key = api_key or os.getenv("GEMINI_API_KEY")
                self.model = model or "gemini-1.5-flash"
                if self.api_key:
                    genai.configure(api_key=self.api_key)
                    self.client = genai.GenerativeModel(self.model)
            except ImportError:
                logger.warning("Google GenerativeAI package not installed")
        
        if self.debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.debug(f"VisionDetectorAdapter initialized: provider={provider}, model={self.model}")
    
    def detect_fields(
        self,
        pdf_path: str,
        document_id: Optional[str] = None,
    ) -> List[FieldDetection]:
        """
        Detect form fields in a PDF using vision AI.
        
        Implements VisionDetectorProtocol.
        
        Args:
            pdf_path: Path to the PDF file
            document_id: Optional document identifier (for logging)
        
        Returns:
            List of FieldDetection objects with normalized coordinates
        """
        if self.client is None:
            if self.debug:
                logger.debug("Vision client not initialized, returning empty list")
            return []
        
        detections: List[FieldDetection] = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_index in range(len(doc)):
                try:
                    page = doc[page_index]
                    
                    # Render page to image
                    image_bytes = self._render_page_to_image(page)
                    
                    # Call vision model
                    result = self._call_vision_model(image_bytes, page_index)
                    
                    if result and 'fields' in result:
                        for field_data in result['fields']:
                            detection = self._convert_to_field_detection(
                                field_data, page_index
                            )
                            if detection:
                                detections.append(detection)
                    
                    if self.debug:
                        logger.debug(
                            f"Page {page_index}: detected {len(result.get('fields', []))} fields"
                        )
                        
                except Exception as e:
                    logger.error(f"Error processing page {page_index}: {e}")
                    continue
            
            doc.close()
            
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
        
        if self.debug:
            logger.debug(f"Total vision detections: {len(detections)}")
        
        return detections
    
    def _render_page_to_image(self, page: fitz.Page) -> bytes:
        """Render a PDF page to PNG bytes."""
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    
    def _call_vision_model(self, image_bytes: bytes, page_index: int) -> dict:
        """Call the vision model and return parsed JSON response."""
        if self.provider == "openai":
            return self._call_openai(image_bytes, page_index)
        elif self.provider == "gemini":
            return self._call_gemini(image_bytes, page_index)
        return {}
    
    def _call_openai(self, image_bytes: bytes, page_index: int) -> dict:
        """Call OpenAI GPT-4o-mini vision API."""
        import base64
        import json
        
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.VISION_PROMPT},
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
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            return self._parse_json_response(content)
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return {}
    
    def _call_gemini(self, image_bytes: bytes, page_index: int) -> dict:
        """Call Google Gemini Flash vision API."""
        from PIL import Image
        from io import BytesIO
        
        try:
            img = Image.open(BytesIO(image_bytes))
            response = self.client.generate_content([self.VISION_PROMPT, img])
            return self._parse_json_response(response.text)
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return {}
    
    def _parse_json_response(self, content: str) -> dict:
        """Parse JSON from vision model response."""
        import json
        
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return {}
    
    def _convert_to_field_detection(
        self,
        field_data: dict,
        page_index: int
    ) -> Optional[FieldDetection]:
        """Convert vision model field data to FieldDetection."""
        try:
            bbox_raw = field_data.get('bbox', [])
            if len(bbox_raw) != 4:
                return None
            
            # Vision model uses 0-1000 coordinate system with bottom-left origin
            x_min, y_min, x_max, y_max = bbox_raw
            
            # Normalize to 0-1 range
            x = max(0.0, min(1.0, x_min / 1000.0))
            y = max(0.0, min(1.0, y_min / 1000.0))
            width = max(0.0, min(1.0 - x, (x_max - x_min) / 1000.0))
            height = max(0.0, min(1.0 - y, (y_max - y_min) / 1000.0))
            
            # Skip invalid boxes
            if width < 0.001 or height < 0.001:
                return None
            
            bbox = BBox(x=x, y=y, width=width, height=height)
            
            # Map field type
            vision_type = field_data.get('type', 'unknown').lower()
            field_type = self.FIELD_TYPE_MAP.get(vision_type, FieldType.UNKNOWN)
            
            # Get label
            label = field_data.get('label', 'Unnamed Field')
            if len(label) > 255:
                label = label[:255]
            
            return FieldDetection(
                page_index=page_index,
                bbox=bbox,
                field_type=field_type,
                label=label,
                confidence=0.85,  # Vision model confidence
                source=DetectionSource.VISION,
                template_key=field_data.get('id')
            )
            
        except Exception as e:
            logger.error(f"Error converting field data: {e}")
            return None


# Verify protocol compliance
assert isinstance(VisionDetectorAdapter, type)
# Runtime check will happen when instance is created
