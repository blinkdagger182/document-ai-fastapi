"""
Text Overlap Filter for Form Field Detection

This module implements a post-processing filter that removes detected form fields
that overlap with existing text regions on the PDF page. This ensures annotations
only appear on genuinely empty input areas (like iOS Files App interactive mode).

How it works:
1. Extracts all text regions from each PDF page using PyMuPDF
2. For each detected field, calculates what fraction of its area overlaps with text
3. Rejects fields where text overlap exceeds the threshold (default 30%)

Coordinate System:
- All coordinates are normalized to [0.0, 1.0] range
- Origin is at bottom-left (PDF standard)
- PyMuPDF uses top-left origin, so y-coordinates are converted

Usage:
    filter = TextOverlapFilter(overlap_threshold=0.30)
    filtered_fields = filter.filter_fields(detected_fields, "form.pdf")
"""

import logging
from typing import List, Dict, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .detection_models import BBox, FieldDetection


# Configure logging
logger = logging.getLogger(__name__)


class TextOverlapFilter:
    """
    Filters out detected fields that overlap with existing text on the page.
    
    This filter ensures that form field annotations only appear on genuinely
    empty areas (empty boxes, blank lines, checkboxes, signature areas) and
    never on printed text, paragraphs, or table cells containing text.
    
    The overlap calculation uses intersection-over-field-area (not IoU):
        overlap_ratio = total_intersection_area / field_area
    
    This means a field is rejected if X% of its area contains text, regardless
    of how much of the text region is covered.
    
    Example:
        filter = TextOverlapFilter(overlap_threshold=0.30)
        
        # Filter fields - removes any field with >30% text overlap
        filtered = filter.filter_fields(detected_fields, "form.pdf")
    """
    
    DEFAULT_OVERLAP_THRESHOLD = 0.30
    
    def __init__(
        self,
        overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
        debug: bool = False
    ):
        """
        Initialize the text overlap filter.
        
        Args:
            overlap_threshold: Maximum allowed text overlap ratio (0.0-1.0).
                              Fields with overlap > threshold are rejected.
                              Default 0.30 (30%).
                              Values outside [0.0, 1.0] are clamped.
            debug: If True, enable verbose logging
        """
        # Clamp threshold to valid range [0.0, 1.0]
        if overlap_threshold < 0.0:
            logger.warning(f"overlap_threshold {overlap_threshold} < 0.0, clamping to 0.0")
            overlap_threshold = 0.0
        elif overlap_threshold > 1.0:
            logger.warning(f"overlap_threshold {overlap_threshold} > 1.0, clamping to 1.0")
            overlap_threshold = 1.0
        
        self.overlap_threshold = overlap_threshold
        self.debug = debug
        
        if self.debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.debug(f"TextOverlapFilter initialized with threshold={overlap_threshold}")
    
    def filter_fields(
        self,
        fields: List[FieldDetection],
        pdf_path: str
    ) -> List[FieldDetection]:
        """
        Filter fields by removing those that overlap with text regions.
        
        Args:
            fields: List of detected fields to filter
            pdf_path: Path to PDF for text extraction
            
        Returns:
            Filtered list with text-overlapping fields removed
        """
        if not fields:
            return []
        
        if fitz is None:
            logger.error("PyMuPDF (fitz) not available, returning fields unfiltered")
            return fields
        
        # Extract text regions from PDF
        try:
            text_regions_by_page = self._extract_all_text_regions(pdf_path)
        except Exception as e:
            logger.error(f"Failed to extract text regions: {e}, returning fields unfiltered")
            return fields
        
        # Filter fields
        filtered_fields: List[FieldDetection] = []
        
        for field in fields:
            page_index = field.page_index
            
            # Get text regions for this page
            text_regions = text_regions_by_page.get(page_index, [])
            
            # Calculate overlap
            overlap_ratio = self.calculate_text_overlap(field.bbox, text_regions)
            
            if self.debug:
                logger.debug(
                    f"Field '{field.label}' on page {page_index}: "
                    f"overlap={overlap_ratio:.2%}, threshold={self.overlap_threshold:.2%}"
                )
            
            # Include field if overlap is below threshold
            if overlap_ratio < self.overlap_threshold:
                filtered_fields.append(field)
            elif self.debug:
                logger.debug(f"Rejected field '{field.label}' due to text overlap")
        
        if self.debug:
            logger.debug(
                f"Filtered {len(fields)} -> {len(filtered_fields)} fields "
                f"(removed {len(fields) - len(filtered_fields)})"
            )
        
        return filtered_fields
    
    def _extract_all_text_regions(self, pdf_path: str) -> Dict[int, List[BBox]]:
        """
        Extract text regions from all pages of a PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict mapping page_index to list of text region BBoxes
        """
        text_regions_by_page: Dict[int, List[BBox]] = {}
        
        doc = fitz.open(pdf_path)
        try:
            for page_index in range(len(doc)):
                page = doc[page_index]
                text_regions = self.extract_text_regions(page)
                text_regions_by_page[page_index] = text_regions
                
                if self.debug:
                    logger.debug(
                        f"Page {page_index}: extracted {len(text_regions)} text regions"
                    )
        finally:
            doc.close()
        
        return text_regions_by_page
    
    def extract_text_regions(self, page) -> List[BBox]:
        """
        Extract all text regions from a PDF page as normalized bboxes.
        
        Uses PyMuPDF's get_text("dict") to get text blocks with bounding boxes,
        then converts to normalized coordinates with bottom-left origin.
        
        Args:
            page: PyMuPDF page object
            
        Returns:
            List of BBox objects representing text regions
        """
        text_regions: List[BBox] = []
        
        page_width = page.rect.width
        page_height = page.rect.height
        
        if page_width <= 0 or page_height <= 0:
            return []
        
        # Get text blocks with bounding boxes
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        blocks = text_dict.get("blocks", [])
        
        for block in blocks:
            # Only process text blocks (type 0), skip image blocks (type 1)
            if block.get("type") != 0:
                continue
            
            bbox_coords = block.get("bbox")
            if not bbox_coords or len(bbox_coords) != 4:
                continue
            
            x0, y0, x1, y1 = bbox_coords
            
            # Skip empty or invalid bboxes
            if x1 <= x0 or y1 <= y0:
                continue
            
            # Convert from PyMuPDF coordinates (top-left origin) to 
            # normalized coordinates (bottom-left origin)
            # PyMuPDF: y=0 is top, y=page_height is bottom
            # PDF standard: y=0 is bottom, y=1.0 is top
            
            x_norm = x0 / page_width
            width_norm = (x1 - x0) / page_width
            
            # Convert y: flip the coordinate system
            y_norm = 1.0 - (y1 / page_height)  # y1 is bottom in PyMuPDF
            height_norm = (y1 - y0) / page_height
            
            # Clamp to valid range
            x_norm = max(0.0, min(1.0, x_norm))
            y_norm = max(0.0, min(1.0, y_norm))
            width_norm = max(0.0, min(1.0 - x_norm, width_norm))
            height_norm = max(0.0, min(1.0 - y_norm, height_norm))
            
            # Skip very small regions (likely noise)
            if width_norm < 0.001 or height_norm < 0.001:
                continue
            
            try:
                bbox = BBox(
                    x=x_norm,
                    y=y_norm,
                    width=width_norm,
                    height=height_norm
                )
                text_regions.append(bbox)
            except ValueError as e:
                if self.debug:
                    logger.debug(f"Skipping invalid bbox: {e}")
                continue
        
        return text_regions
    
    def calculate_text_overlap(
        self,
        field_bbox: BBox,
        text_regions: List[BBox]
    ) -> float:
        """
        Calculate what fraction of the field area overlaps with text.
        
        Uses intersection-over-field-area (not IoU):
            overlap_ratio = sum(intersection_areas) / field_area
        
        This means a field is rejected if X% of its area contains text,
        regardless of how much of the text region is covered.
        
        Args:
            field_bbox: The field's bounding box
            text_regions: List of text region bboxes on the same page
            
        Returns:
            Overlap ratio between 0.0 and 1.0
        """
        field_area = field_bbox.area()
        
        if field_area <= 0:
            return 0.0
        
        if not text_regions:
            return 0.0
        
        # Sum intersection areas with all text regions
        total_intersection = 0.0
        
        for text_bbox in text_regions:
            intersection = field_bbox.intersection_area(text_bbox)
            total_intersection += intersection
        
        # Calculate ratio (clamped to 1.0 in case of overlapping text regions)
        overlap_ratio = total_intersection / field_area
        return min(1.0, overlap_ratio)
