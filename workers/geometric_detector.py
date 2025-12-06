"""
Geometric Form Field Detection using OpenCV

This module implements Step 3 of the DocumentAI system: Pure geometric field detection
using computer vision techniques to find form fields that AI might miss.

How it works:
1. Takes a page image (numpy array)
2. Applies OpenCV image processing to detect:
   - Horizontal lines (signature fields, underlines)
   - Rectangular boxes (text fields, checkboxes)
   - Whitespace regions (optional)
3. Filters candidates by size and aspect ratio
4. Returns FieldDetection objects with normalized coordinates

Coordinate System:
- Input: OpenCV image with origin at top-left (standard image coordinates)
- Output: Normalized coordinates (0-1) with origin at bottom-left (PDF standard)
- Conversion: y_normalized = 1.0 - (y_opencv + height) / image_height

Detection Heuristics:
- Checkbox: Small square (aspect ratio ~1.0, area < 0.5% of page)
- Signature: Very wide line (aspect ratio > 8.0, height < 2% of page)
- Text field: Moderate rectangle (aspect ratio 2.0-8.0)
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .detection_models import BBox, FieldDetection, FieldType, DetectionSource


@dataclass
class ContourCandidate:
    """
    Internal representation of a detected contour before classification.
    
    Attributes:
        x, y, w, h: Bounding box in pixel coordinates (OpenCV top-left origin)
        area: Area in pixels
        aspect_ratio: width / height
        confidence: Detection confidence (0-1)
    """
    x: int
    y: int
    w: int
    h: int
    area: float
    aspect_ratio: float
    confidence: float = 0.8


class GeometricDetector:
    """
    Pure geometric form-field detector using OpenCV.
    
    Responsibilities:
    - Take a single page image (numpy array, RGB or BGR)
    - Detect line-based fields (underlines, rectangular boxes, grid cells)
    - Return a list of FieldDetection objects with normalized coordinates
      using the same normalized system as BBox (0–1, bottom-left origin)
    
    Detection Strategy:
    1. Convert to grayscale
    2. Apply adaptive thresholding
    3. Use morphological operations to emphasize lines/boxes
    4. Find contours
    5. Filter by size and aspect ratio
    6. Classify as checkbox/signature/text
    7. Convert to normalized coordinates
    
    Limitations:
    - Cannot read labels (returns generic labels like "Field 1")
    - May produce false positives on decorative elements
    - Requires tuning for different document styles
    - Best used in ensemble with Vision AI for label extraction
    """
    
    def __init__(
        self,
        min_field_width_ratio: float = 0.05,
        min_field_height_ratio: float = 0.005,
        max_field_height_ratio: float = 0.08,
        debug: bool = False,
    ):
        """
        Initialize the geometric detector.
        
        Args:
            min_field_width_ratio: Minimum field width as ratio of page width (default 0.05 = 5%)
            min_field_height_ratio: Minimum field height as ratio of page height (default 0.005 = 0.5%)
            max_field_height_ratio: Maximum field height as ratio of page height (default 0.08 = 8%)
            debug: If True, save intermediate images for debugging
        """
        self.min_field_width_ratio = min_field_width_ratio
        self.min_field_height_ratio = min_field_height_ratio
        self.max_field_height_ratio = max_field_height_ratio
        self.debug = debug
        
        # Thresholds for field classification
        self.checkbox_max_area_ratio = 0.005  # 0.5% of page
        self.checkbox_aspect_ratio_range = (0.5, 2.0)  # Nearly square
        self.signature_min_aspect_ratio = 8.0  # Very wide
        self.signature_max_height_ratio = 0.02  # Very short (2% of page)
        self.text_aspect_ratio_range = (2.0, 8.0)  # Moderate rectangle
    
    def detect_page_fields(
        self,
        page_image: np.ndarray,
        page_index: int,
    ) -> List[FieldDetection]:
        """
        Detect candidate fields on a single page image.
        
        Args:
            page_image: H x W x 3 numpy array (RGB or BGR)
            page_index: Zero-based page index in the document
        
        Returns:
            A list of FieldDetection with:
              - bbox: normalized BBox (0-1, bottom-left origin)
              - field_type: text / checkbox / signature / unknown
              - source: DetectionSource.GEOMETRIC
              - confidence: heuristically assigned [0.0–1.0]
              - label: Generic label (e.g., "Field 1", "Checkbox 2")
        """
        if page_image is None or page_image.size == 0:
            return []
        
        # Get image dimensions
        img_height, img_width = page_image.shape[:2]
        
        if img_height == 0 or img_width == 0:
            return []
        
        # Step 1: Preprocess image
        gray = self._convert_to_grayscale(page_image)
        binary = self._apply_thresholding(gray)
        
        # Step 2: Detect rectangles using contours
        rectangles = self._detect_rectangles(binary, img_width, img_height)
        
        # Step 3: Detect horizontal lines (signature fields)
        lines = self._detect_horizontal_lines(binary, img_width, img_height)
        
        # Combine all candidates
        all_candidates = rectangles + lines
        
        # Step 4: Convert to FieldDetection objects
        detections = []
        field_counter = {'text': 0, 'checkbox': 0, 'signature': 0}
        
        for candidate in all_candidates:
            # Classify field type
            field_type = self._classify_field_type(
                candidate, img_width, img_height
            )
            
            # Generate label
            field_counter[field_type.value] += 1
            label = self._generate_label(field_type, field_counter[field_type.value])
            
            # Convert to normalized coordinates (bottom-left origin)
            bbox = self._convert_to_normalized_bbox(
                candidate, img_width, img_height
            )
            
            # Create FieldDetection
            detection = FieldDetection(
                page_index=page_index,
                bbox=bbox,
                field_type=field_type,
                label=label,
                confidence=candidate.confidence,
                source=DetectionSource.GEOMETRIC,
                template_key=None
            )
            
            detections.append(detection)
        
        return detections
    
    def _convert_to_grayscale(self, image: np.ndarray) -> np.ndarray:
        """
        Convert image to grayscale.
        
        Args:
            image: RGB or BGR image
        
        Returns:
            Grayscale image
        """
        if len(image.shape) == 2:
            # Already grayscale
            return image
        elif image.shape[2] == 3:
            # Convert BGR/RGB to grayscale
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            # RGBA or other format - take first channel
            return image[:, :, 0]
    
    def _apply_thresholding(self, gray: np.ndarray) -> np.ndarray:
        """
        Apply adaptive thresholding to create binary image.
        
        Args:
            gray: Grayscale image
        
        Returns:
            Binary image (0 or 255)
        """
        # Use adaptive thresholding for better results with varying lighting
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,  # Invert so lines are white
            blockSize=11,
            C=2
        )
        
        return binary
    
    def _detect_rectangles(
        self,
        binary: np.ndarray,
        img_width: int,
        img_height: int
    ) -> List[ContourCandidate]:
        """
        Detect rectangular regions using contour detection.
        
        Args:
            binary: Binary image
            img_width: Image width in pixels
            img_height: Image height in pixels
        
        Returns:
            List of ContourCandidate objects
        """
        # Apply morphological operations to connect nearby components
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        # Find contours
        contours, _ = cv2.findContours(
            morph,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        candidates = []
        
        # Calculate size thresholds
        min_width = int(img_width * self.min_field_width_ratio)
        min_height = int(img_height * self.min_field_height_ratio)
        max_height = int(img_height * self.max_field_height_ratio)
        
        for contour in contours:
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter by size
            if w < min_width or h < min_height:
                continue
            
            if h > max_height:
                continue
            
            # Calculate properties
            area = w * h
            aspect_ratio = w / h if h > 0 else 0
            
            # Filter out very thin lines (likely noise)
            if h < 3 or w < 3:
                continue
            
            # Calculate confidence based on rectangularity
            contour_area = cv2.contourArea(contour)
            rectangularity = contour_area / area if area > 0 else 0
            confidence = min(0.9, 0.6 + rectangularity * 0.3)
            
            candidates.append(ContourCandidate(
                x=x,
                y=y,
                w=w,
                h=h,
                area=area,
                aspect_ratio=aspect_ratio,
                confidence=confidence
            ))
        
        return candidates
    
    def _detect_horizontal_lines(
        self,
        binary: np.ndarray,
        img_width: int,
        img_height: int
    ) -> List[ContourCandidate]:
        """
        Detect horizontal lines (signature fields, underlines).
        
        Args:
            binary: Binary image
            img_width: Image width in pixels
            img_height: Image height in pixels
        
        Returns:
            List of ContourCandidate objects representing lines
        """
        # Create horizontal kernel to emphasize horizontal lines
        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (int(img_width * 0.05), 1)  # Wide horizontal kernel
        )
        
        # Apply morphological operations
        horizontal_lines = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            horizontal_kernel,
            iterations=1
        )
        
        # Find contours of horizontal lines
        contours, _ = cv2.findContours(
            horizontal_lines,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        candidates = []
        
        # Calculate size thresholds
        min_width = int(img_width * 0.1)  # Lines should be at least 10% of page width
        min_height = 1
        max_height = int(img_height * 0.01)  # Lines should be thin (< 1% of page height)
        
        for contour in contours:
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter by size
            if w < min_width or h < min_height or h > max_height:
                continue
            
            # Calculate properties
            area = w * h
            aspect_ratio = w / h if h > 0 else 0
            
            # Only keep very wide lines (signature fields)
            if aspect_ratio < 8.0:
                continue
            
            # Higher confidence for cleaner lines
            confidence = 0.85
            
            candidates.append(ContourCandidate(
                x=x,
                y=y,
                w=w,
                h=h,
                area=area,
                aspect_ratio=aspect_ratio,
                confidence=confidence
            ))
        
        return candidates
    
    def _classify_field_type(
        self,
        candidate: ContourCandidate,
        img_width: int,
        img_height: int
    ) -> FieldType:
        """
        Classify a candidate as checkbox, signature, or text field.
        
        Args:
            candidate: ContourCandidate to classify
            img_width: Image width in pixels
            img_height: Image height in pixels
        
        Returns:
            FieldType enum value
        """
        page_area = img_width * img_height
        area_ratio = candidate.area / page_area
        height_ratio = candidate.h / img_height
        
        # Checkbox: Small and nearly square
        if (area_ratio < self.checkbox_max_area_ratio and
            self.checkbox_aspect_ratio_range[0] <= candidate.aspect_ratio <= self.checkbox_aspect_ratio_range[1]):
            return FieldType.CHECKBOX
        
        # Signature: Very wide and short
        if (candidate.aspect_ratio >= self.signature_min_aspect_ratio and
            height_ratio <= self.signature_max_height_ratio):
            return FieldType.SIGNATURE
        
        # Text field: Moderate rectangle
        if self.text_aspect_ratio_range[0] <= candidate.aspect_ratio <= self.text_aspect_ratio_range[1]:
            return FieldType.TEXT
        
        # Default to text for anything else
        return FieldType.TEXT
    
    def _generate_label(self, field_type: FieldType, counter: int) -> str:
        """
        Generate a generic label for a detected field.
        
        Args:
            field_type: Type of field
            counter: Counter for this field type
        
        Returns:
            Generic label string
        """
        if field_type == FieldType.CHECKBOX:
            return f"Checkbox {counter}"
        elif field_type == FieldType.SIGNATURE:
            return f"Signature {counter}"
        elif field_type == FieldType.TEXT:
            return f"Text Field {counter}"
        else:
            return f"Field {counter}"
    
    def _convert_to_normalized_bbox(
        self,
        candidate: ContourCandidate,
        img_width: int,
        img_height: int
    ) -> BBox:
        """
        Convert pixel coordinates to normalized BBox with bottom-left origin.
        
        OpenCV uses top-left origin: (0, 0) is top-left corner
        PDF uses bottom-left origin: (0, 0) is bottom-left corner
        
        Conversion:
        - x_normalized = x_opencv / img_width
        - y_normalized = 1.0 - (y_opencv + height) / img_height
        - width_normalized = width_opencv / img_width
        - height_normalized = height_opencv / img_height
        
        Args:
            candidate: ContourCandidate with pixel coordinates
            img_width: Image width in pixels
            img_height: Image height in pixels
        
        Returns:
            BBox with normalized coordinates (0-1, bottom-left origin)
        """
        # Normalize dimensions
        x_norm = candidate.x / img_width
        width_norm = candidate.w / img_width
        height_norm = candidate.h / img_height
        
        # Convert y from top-left to bottom-left origin
        # In OpenCV: y=0 is top, y=img_height is bottom
        # In PDF: y=0 is bottom, y=1.0 is top
        y_opencv_bottom = candidate.y + candidate.h  # Bottom edge in OpenCV coords
        y_norm = 1.0 - (y_opencv_bottom / img_height)  # Convert to PDF coords
        
        # Clamp to valid range [0, 1]
        x_norm = max(0.0, min(1.0, x_norm))
        y_norm = max(0.0, min(1.0, y_norm))
        width_norm = max(0.0, min(1.0 - x_norm, width_norm))
        height_norm = max(0.0, min(1.0 - y_norm, height_norm))
        
        return BBox(
            x=x_norm,
            y=y_norm,
            width=width_norm,
            height=height_norm
        )
    
    def _is_checkbox(self, candidate: ContourCandidate, page_area: float) -> bool:
        """
        Check if candidate is likely a checkbox.
        
        Args:
            candidate: ContourCandidate to check
            page_area: Total page area in pixels
        
        Returns:
            True if likely a checkbox
        """
        area_ratio = candidate.area / page_area
        return (area_ratio < self.checkbox_max_area_ratio and
                self.checkbox_aspect_ratio_range[0] <= candidate.aspect_ratio <= self.checkbox_aspect_ratio_range[1])
    
    def _is_signature_line(self, candidate: ContourCandidate, img_height: int) -> bool:
        """
        Check if candidate is likely a signature line.
        
        Args:
            candidate: ContourCandidate to check
            img_height: Image height in pixels
        
        Returns:
            True if likely a signature line
        """
        height_ratio = candidate.h / img_height
        return (candidate.aspect_ratio >= self.signature_min_aspect_ratio and
                height_ratio <= self.signature_max_height_ratio)
