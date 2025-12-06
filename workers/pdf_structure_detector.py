"""
PDF Structure Detector using PyMuPDF (fitz)

This module implements Phase 3 of the Hybrid Detection Pipeline: PDF structural
field detection using PyMuPDF to extract form fields directly from PDF structure.

How it works:
1. Opens PDF using PyMuPDF (fitz)
2. Extracts structural elements:
   - AcroForm text fields
   - Widget annotations
   - Checkbox fields
   - Radio button fields
   - Signature fields
   - Rectangles that represent input areas
   - XObject-based form fields
3. Infers field labels using heuristics
4. Returns FieldDetection objects with normalized coordinates

Coordinate System:
- PDF uses bottom-left origin: (0, 0) is bottom-left corner
- All coordinates are normalized to [0.0, 1.0] range
- y is inverted from PyMuPDF's top-left origin to PDF standard bottom-left

Detection Sources:
- AcroForm fields: Native PDF form fields (highest accuracy)
- Widget annotations: Interactive form elements
- Drawing rectangles: Visual form field indicators
- XObjects: Embedded form templates

This detector is deterministic and does not depend on pixel rendering.
"""

import fitz  # PyMuPDF
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import logging

from .detection_models import BBox, FieldDetection, FieldType, DetectionSource


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class RawFieldData:
    """
    Internal representation of a raw field before conversion to FieldDetection.
    
    Attributes:
        rect: PyMuPDF Rect object
        field_type: Detected field type
        label: Field label/name
        value: Current field value (if any)
        page_index: Zero-based page number
        confidence: Detection confidence (0-1)
    """
    rect: fitz.Rect
    field_type: FieldType
    label: Optional[str]
    value: Optional[str]
    page_index: int
    confidence: float = 0.95


class PDFStructureDetector:
    """
    PDF structural form-field detector using PyMuPDF.
    
    Responsibilities:
    - Open PDF files and extract structural form field data
    - Detect AcroForm fields, widget annotations, and visual form elements
    - Return a list of FieldDetection objects with normalized coordinates
      using the same normalized system as BBox (0–1, bottom-left origin)
    
    Detection Strategy:
    1. Extract AcroForm fields from document catalog
    2. Extract widget annotations from each page
    3. Detect rectangles from drawing commands
    4. Extract XObject-based form fields
    5. Infer labels using text proximity heuristics
    6. Convert all coordinates to normalized format
    
    Advantages over Vision/Geometric detection:
    - 100% accurate for native PDF forms
    - No rendering required
    - Extracts field names and values
    - Deterministic results
    
    Limitations:
    - Cannot detect fields in scanned/image PDFs
    - May miss visually-drawn fields without annotations
    - Best used in ensemble with Vision AI for comprehensive coverage
    """
    
    # Widget annotation type constant
    WIDGET_TYPE = 20  # fitz.PDF_ANNOT_WIDGET
    
    # Field type mappings from PDF /FT values
    FIELD_TYPE_MAP = {
        'Tx': FieldType.TEXT,      # Text field
        'Btn': FieldType.CHECKBOX,  # Button (checkbox/radio)
        'Sig': FieldType.SIGNATURE, # Signature
        'Ch': FieldType.TEXT,       # Choice (dropdown/listbox)
    }
    
    def __init__(self, debug: bool = False):
        """
        Initialize the PDF structure detector.
        
        Args:
            debug: If True, enable verbose logging for debugging
        """
        self.debug = debug
        
        # Thresholds for field classification
        self.min_field_width_ratio = 0.02   # 2% of page width
        self.min_field_height_ratio = 0.005  # 0.5% of page height
        self.max_field_height_ratio = 0.15   # 15% of page height
        
        # Checkbox detection thresholds
        self.checkbox_max_size_ratio = 0.03  # 3% of page dimension
        self.checkbox_aspect_ratio_range = (0.5, 2.0)  # Nearly square
        
        # Signature detection thresholds
        self.signature_min_aspect_ratio = 4.0  # Wide rectangle
        self.signature_max_height_ratio = 0.05  # Short height
        
        # Label inference settings
        self.label_search_distance = 0.15  # 15% of page width to search for labels
        
        if self.debug:
            logging.basicConfig(level=logging.DEBUG)
    
    def detect_fields(self, pdf_path: str) -> List[FieldDetection]:
        """
        Detect all form fields in a PDF document.
        
        Args:
            pdf_path: Path to the PDF file
        
        Returns:
            List of FieldDetection objects with normalized coordinates
        """
        detections: List[FieldDetection] = []
        
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"Failed to open PDF: {e}")
            return []
        
        try:
            # Step 1: Extract AcroForm fields (document-level)
            acroform_fields = self._extract_acroform_fields(doc)
            detections.extend(acroform_fields)
            
            if self.debug:
                logger.debug(f"Found {len(acroform_fields)} AcroForm fields")
            
            # Step 2: Process each page
            for page_index in range(len(doc)):
                page = doc[page_index]
                
                # Extract widget annotations
                widget_fields = self._extract_widget_annotations(page, page_index)
                detections.extend(widget_fields)
                
                if self.debug:
                    logger.debug(f"Page {page_index}: {len(widget_fields)} widget annotations")
                
                # Extract rectangle-based form glyphs
                rect_fields = self._extract_rect_form_glyphs(page, page_index)
                detections.extend(rect_fields)
                
                if self.debug:
                    logger.debug(f"Page {page_index}: {len(rect_fields)} rectangle fields")
                
                # Extract XObject-based fields
                xobject_fields = self._extract_xobjects(page, page_index)
                detections.extend(xobject_fields)
                
                if self.debug:
                    logger.debug(f"Page {page_index}: {len(xobject_fields)} XObject fields")
            
            # Deduplicate overlapping detections from same source
            detections = self._deduplicate_detections(detections)
            
            if self.debug:
                logger.debug(f"Total detections after dedup: {len(detections)}")
            
        finally:
            doc.close()
        
        return detections
    
    def _extract_acroform_fields(self, doc: fitz.Document) -> List[FieldDetection]:
        """
        Extract AcroForm fields from the document catalog.
        
        AcroForm fields are the native PDF form fields defined in the
        document's interactive form dictionary.
        
        Args:
            doc: PyMuPDF Document object
        
        Returns:
            List of FieldDetection objects
        """
        detections: List[FieldDetection] = []
        
        # Check if document has AcroForm
        try:
            # Get the trailer/catalog
            xref_len = doc.xref_length()
            
            # Look for AcroForm in catalog
            for xref in range(1, xref_len):
                try:
                    obj_type = doc.xref_get_key(xref, "Type")
                    if obj_type and obj_type[1] == "/Catalog":
                        acroform_ref = doc.xref_get_key(xref, "AcroForm")
                        if acroform_ref and acroform_ref[0] != "null":
                            if self.debug:
                                logger.debug(f"Found AcroForm reference: {acroform_ref}")
                            break
                except Exception:
                    continue
            
        except Exception as e:
            if self.debug:
                logger.debug(f"No AcroForm found: {e}")
            return []
        
        # Use PyMuPDF's built-in widget iteration for AcroForm fields
        # This is more reliable than manual parsing
        for page_index in range(len(doc)):
            page = doc[page_index]
            
            for widget in page.widgets():
                try:
                    field_detection = self._widget_to_detection(widget, page, page_index)
                    if field_detection:
                        detections.append(field_detection)
                except Exception as e:
                    if self.debug:
                        logger.debug(f"Error processing widget: {e}")
                    continue
        
        return detections
    
    def _extract_widget_annotations(
        self,
        page: fitz.Page,
        page_index: int
    ) -> List[FieldDetection]:
        """
        Extract widget annotations from a page.
        
        Widget annotations are interactive form elements that may not
        be part of the AcroForm structure.
        
        Args:
            page: PyMuPDF Page object
            page_index: Zero-based page number
        
        Returns:
            List of FieldDetection objects
        """
        detections: List[FieldDetection] = []
        
        # Iterate through all annotations
        for annot in page.annots():
            if annot is None:
                continue
            
            try:
                # Check if this is a widget annotation
                annot_type = annot.type[0]
                
                if annot_type == self.WIDGET_TYPE:
                    # Get annotation info
                    info = annot.info
                    rect = annot.rect
                    
                    # Skip invalid rectangles
                    if rect.is_empty or rect.is_infinite:
                        continue
                    
                    # Classify the annotation
                    field_type = self._classify_annotation(annot, page)
                    
                    # Get label from annotation or infer it
                    label = info.get('title') or info.get('name')
                    if not label:
                        label = self._infer_label(page, rect)
                    
                    # Convert to normalized bbox
                    bbox = self._convert_pdf_rect_to_bbox(rect, page)
                    
                    if bbox is None:
                        continue
                    
                    detection = FieldDetection(
                        page_index=page_index,
                        bbox=bbox,
                        field_type=field_type,
                        label=label or f"Widget {len(detections) + 1}",
                        confidence=0.95,
                        source=DetectionSource.STRUCTURE,
                        template_key=None
                    )
                    
                    detections.append(detection)
                    
            except Exception as e:
                if self.debug:
                    logger.debug(f"Error processing annotation: {e}")
                continue
        
        return detections
    
    def _extract_rect_form_glyphs(
        self,
        page: fitz.Page,
        page_index: int
    ) -> List[FieldDetection]:
        """
        Extract rectangle-based form fields from drawing commands.
        
        Many official forms draw rectangles but do not embed AcroForms.
        This method detects such visual form field indicators.
        
        Args:
            page: PyMuPDF Page object
            page_index: Zero-based page number
        
        Returns:
            List of FieldDetection objects
        """
        detections: List[FieldDetection] = []
        
        try:
            drawings = page.get_drawings()
        except Exception as e:
            if self.debug:
                logger.debug(f"Error getting drawings: {e}")
            return []
        
        page_width = page.rect.width
        page_height = page.rect.height
        
        for drawing in drawings:
            try:
                # Check if this is a rectangle
                items = drawing.get('items', [])
                rect_item = None
                
                for item in items:
                    if item[0] == 're':  # Rectangle command
                        rect_item = item
                        break
                
                if rect_item is None:
                    continue
                
                # Get rectangle coordinates
                rect = drawing.get('rect')
                if rect is None:
                    continue
                
                rect = fitz.Rect(rect)
                
                # Skip invalid rectangles
                if rect.is_empty or rect.is_infinite:
                    continue
                
                # Filter by size
                width_ratio = rect.width / page_width
                height_ratio = rect.height / page_height
                
                if width_ratio < self.min_field_width_ratio:
                    continue
                if height_ratio < self.min_field_height_ratio:
                    continue
                if height_ratio > self.max_field_height_ratio:
                    continue
                
                # Classify field type based on dimensions
                field_type = self._classify_rect_field(rect, page)
                
                # Infer label
                label = self._infer_label(page, rect)
                
                # Convert to normalized bbox
                bbox = self._convert_pdf_rect_to_bbox(rect, page)
                
                if bbox is None:
                    continue
                
                detection = FieldDetection(
                    page_index=page_index,
                    bbox=bbox,
                    field_type=field_type,
                    label=label or f"Field {len(detections) + 1}",
                    confidence=0.75,  # Lower confidence for drawn rectangles
                    source=DetectionSource.STRUCTURE,
                    template_key=None
                )
                
                detections.append(detection)
                
            except Exception as e:
                if self.debug:
                    logger.debug(f"Error processing drawing: {e}")
                continue
        
        return detections
    
    def _extract_xobjects(
        self,
        page: fitz.Page,
        page_index: int
    ) -> List[FieldDetection]:
        """
        Extract XObject-based form fields.
        
        Form XObjects are reusable content streams that may contain
        form field templates.
        
        Args:
            page: PyMuPDF Page object
            page_index: Zero-based page number
        
        Returns:
            List of FieldDetection objects
        """
        detections: List[FieldDetection] = []
        
        try:
            # Get XObjects from page resources
            xobjects = page.get_images(full=True)
            
            # Also check for Form XObjects in the page's resources
            # These are different from image XObjects
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            
            # Look for blocks that might be form XObjects
            blocks = page_dict.get('blocks', [])
            
            for block in blocks:
                if block.get('type') == 1:  # Image block
                    bbox_coords = block.get('bbox')
                    if bbox_coords:
                        rect = fitz.Rect(bbox_coords)
                        
                        # Check if this looks like a form field
                        if self._is_form_field_candidate(rect, page):
                            bbox = self._convert_pdf_rect_to_bbox(rect, page)
                            
                            if bbox is None:
                                continue
                            
                            field_type = self._classify_rect_field(rect, page)
                            label = self._infer_label(page, rect)
                            
                            detection = FieldDetection(
                                page_index=page_index,
                                bbox=bbox,
                                field_type=field_type,
                                label=label or f"XObject Field {len(detections) + 1}",
                                confidence=0.70,  # Lower confidence for XObjects
                                source=DetectionSource.STRUCTURE,
                                template_key=None
                            )
                            
                            detections.append(detection)
            
        except Exception as e:
            if self.debug:
                logger.debug(f"Error extracting XObjects: {e}")
        
        return detections
    
    def _widget_to_detection(
        self,
        widget: fitz.Widget,
        page: fitz.Page,
        page_index: int
    ) -> Optional[FieldDetection]:
        """
        Convert a PyMuPDF Widget to a FieldDetection.
        
        Args:
            widget: PyMuPDF Widget object
            page: PyMuPDF Page object
            page_index: Zero-based page number
        
        Returns:
            FieldDetection object or None if invalid
        """
        try:
            rect = widget.rect
            
            # Skip invalid rectangles
            if rect.is_empty or rect.is_infinite:
                return None
            
            # Get field type from widget
            field_type_code = widget.field_type
            
            # Map widget field type to our FieldType
            if field_type_code == fitz.PDF_WIDGET_TYPE_TEXT:
                field_type = FieldType.TEXT
            elif field_type_code == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                field_type = FieldType.CHECKBOX
            elif field_type_code == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                field_type = FieldType.CHECKBOX  # Treat radio as checkbox
            elif field_type_code == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                field_type = FieldType.SIGNATURE
            elif field_type_code == fitz.PDF_WIDGET_TYPE_COMBOBOX:
                field_type = FieldType.TEXT
            elif field_type_code == fitz.PDF_WIDGET_TYPE_LISTBOX:
                field_type = FieldType.TEXT
            else:
                field_type = FieldType.UNKNOWN
            
            # Get label from widget name or infer it
            label = widget.field_name
            if not label:
                label = self._infer_label(page, rect)
            
            # Convert to normalized bbox
            bbox = self._convert_pdf_rect_to_bbox(rect, page)
            
            if bbox is None:
                return None
            
            return FieldDetection(
                page_index=page_index,
                bbox=bbox,
                field_type=field_type,
                label=label or f"Field {page_index + 1}",
                confidence=0.98,  # High confidence for native widgets
                source=DetectionSource.STRUCTURE,
                template_key=None
            )
            
        except Exception as e:
            if self.debug:
                logger.debug(f"Error converting widget: {e}")
            return None
    
    def _classify_annotation(
        self,
        annot: fitz.Annot,
        page: fitz.Page
    ) -> FieldType:
        """
        Classify a widget annotation by its type.
        
        Args:
            annot: PyMuPDF Annotation object
            page: PyMuPDF Page object
        
        Returns:
            FieldType enum value
        """
        try:
            # Try to get field type from annotation info
            info = annot.info
            
            # Check for specific field type indicators
            rect = annot.rect
            page_width = page.rect.width
            page_height = page.rect.height
            
            width_ratio = rect.width / page_width
            height_ratio = rect.height / page_height
            aspect_ratio = rect.width / rect.height if rect.height > 0 else 0
            
            # Checkbox: Small and nearly square
            if (width_ratio < self.checkbox_max_size_ratio and
                height_ratio < self.checkbox_max_size_ratio and
                self.checkbox_aspect_ratio_range[0] <= aspect_ratio <= self.checkbox_aspect_ratio_range[1]):
                return FieldType.CHECKBOX
            
            # Signature: Wide and short
            if (aspect_ratio >= self.signature_min_aspect_ratio and
                height_ratio <= self.signature_max_height_ratio):
                return FieldType.SIGNATURE
            
            # Default to text
            return FieldType.TEXT
            
        except Exception:
            return FieldType.UNKNOWN
    
    def _classify_rect_field(
        self,
        rect: fitz.Rect,
        page: fitz.Page
    ) -> FieldType:
        """
        Classify a rectangle as a specific field type.
        
        Args:
            rect: PyMuPDF Rect object
            page: PyMuPDF Page object
        
        Returns:
            FieldType enum value
        """
        page_width = page.rect.width
        page_height = page.rect.height
        
        width_ratio = rect.width / page_width
        height_ratio = rect.height / page_height
        aspect_ratio = rect.width / rect.height if rect.height > 0 else 0
        
        # Checkbox: Small and nearly square
        if (width_ratio < self.checkbox_max_size_ratio and
            height_ratio < self.checkbox_max_size_ratio and
            self.checkbox_aspect_ratio_range[0] <= aspect_ratio <= self.checkbox_aspect_ratio_range[1]):
            return FieldType.CHECKBOX
        
        # Signature: Wide and short
        if (aspect_ratio >= self.signature_min_aspect_ratio and
            height_ratio <= self.signature_max_height_ratio):
            return FieldType.SIGNATURE
        
        # Default to text
        return FieldType.TEXT
    
    def _convert_pdf_rect_to_bbox(
        self,
        rect: fitz.Rect,
        page: fitz.Page
    ) -> Optional[BBox]:
        """
        Convert a PDF rectangle to a normalized BBox.
        
        PyMuPDF uses top-left origin internally, but we need bottom-left origin
        for consistency with PDF standard coordinates.
        
        Args:
            rect: PyMuPDF Rect object
            page: PyMuPDF Page object
        
        Returns:
            BBox with normalized coordinates (0-1, bottom-left origin)
        """
        try:
            page_width = page.rect.width
            page_height = page.rect.height
            
            if page_width <= 0 or page_height <= 0:
                return None
            
            # Normalize x and width
            x = rect.x0 / page_width
            width = rect.width / page_width
            
            # Convert y from top-left to bottom-left origin
            # In PyMuPDF: y=0 is top, y=page_height is bottom
            # In PDF standard: y=0 is bottom, y=1.0 is top
            # rect.y1 is the bottom edge in PyMuPDF coords
            y = 1.0 - (rect.y1 / page_height)
            height = rect.height / page_height
            
            # Clamp to valid range [0, 1]
            x = max(0.0, min(1.0, x))
            y = max(0.0, min(1.0, y))
            width = max(0.0, min(1.0 - x, width))
            height = max(0.0, min(1.0 - y, height))
            
            # Skip if dimensions are too small
            if width < 0.001 or height < 0.001:
                return None
            
            return BBox(x=x, y=y, width=width, height=height)
            
        except Exception as e:
            if self.debug:
                logger.debug(f"Error converting rect to bbox: {e}")
            return None
    
    def _infer_label(
        self,
        page: fitz.Page,
        bbox: fitz.Rect
    ) -> Optional[str]:
        """
        Infer a field label by searching for nearby text.
        
        Heuristics:
        1. Search to the left of the field
        2. Search above the field
        3. Use the closest text block
        
        Args:
            page: PyMuPDF Page object
            bbox: Field bounding box
        
        Returns:
            Inferred label string or None
        """
        try:
            page_width = page.rect.width
            search_distance = page_width * self.label_search_distance
            
            # Define search regions
            # Region to the left of the field
            left_region = fitz.Rect(
                max(0, bbox.x0 - search_distance),
                bbox.y0,
                bbox.x0,
                bbox.y1
            )
            
            # Region above the field
            above_region = fitz.Rect(
                bbox.x0,
                max(0, bbox.y0 - search_distance),
                bbox.x1,
                bbox.y0
            )
            
            # Get text from regions
            left_text = page.get_text("text", clip=left_region).strip()
            above_text = page.get_text("text", clip=above_region).strip()
            
            # Prefer left text (common form layout)
            if left_text:
                # Clean up the label
                label = self._clean_label(left_text)
                if label:
                    return label
            
            # Fall back to above text
            if above_text:
                label = self._clean_label(above_text)
                if label:
                    return label
            
            return None
            
        except Exception as e:
            if self.debug:
                logger.debug(f"Error inferring label: {e}")
            return None
    
    def _clean_label(self, text: str) -> Optional[str]:
        """
        Clean up a label string.
        
        Args:
            text: Raw text string
        
        Returns:
            Cleaned label or None if invalid
        """
        if not text:
            return None
        
        # Remove extra whitespace
        label = ' '.join(text.split())
        
        # Remove trailing colons
        label = label.rstrip(':')
        
        # Limit length
        if len(label) > 100:
            label = label[:100]
        
        # Skip if too short or just punctuation
        if len(label) < 2:
            return None
        
        if all(c in '.:;,!?-_' for c in label):
            return None
        
        return label
    
    def _is_form_field_candidate(
        self,
        rect: fitz.Rect,
        page: fitz.Page
    ) -> bool:
        """
        Check if a rectangle is a likely form field candidate.
        
        Args:
            rect: PyMuPDF Rect object
            page: PyMuPDF Page object
        
        Returns:
            True if likely a form field
        """
        page_width = page.rect.width
        page_height = page.rect.height
        
        width_ratio = rect.width / page_width
        height_ratio = rect.height / page_height
        
        # Check size constraints
        if width_ratio < self.min_field_width_ratio:
            return False
        if height_ratio < self.min_field_height_ratio:
            return False
        if height_ratio > self.max_field_height_ratio:
            return False
        
        # Check aspect ratio (not too extreme)
        aspect_ratio = rect.width / rect.height if rect.height > 0 else 0
        if aspect_ratio < 0.1 or aspect_ratio > 50:
            return False
        
        return True
    
    def _deduplicate_detections(
        self,
        detections: List[FieldDetection]
    ) -> List[FieldDetection]:
        """
        Remove duplicate detections that overlap significantly.
        
        Args:
            detections: List of FieldDetection objects
        
        Returns:
            Deduplicated list
        """
        if len(detections) <= 1:
            return detections
        
        # Sort by confidence (highest first)
        sorted_detections = sorted(
            detections,
            key=lambda d: d.confidence,
            reverse=True
        )
        
        result: List[FieldDetection] = []
        
        for detection in sorted_detections:
            # Check if this detection overlaps with any existing result
            is_duplicate = False
            
            for existing in result:
                # Only compare detections on the same page
                if detection.page_index != existing.page_index:
                    continue
                
                # Calculate IoU
                intersection = detection.bbox.intersection_area(existing.bbox)
                union = detection.bbox.area() + existing.bbox.area() - intersection
                iou = intersection / union if union > 0 else 0.0
                
                # If IoU > 0.5, consider it a duplicate
                if iou > 0.5:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                result.append(detection)
        
        return result
