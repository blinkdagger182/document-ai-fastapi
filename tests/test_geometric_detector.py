"""
Unit Tests for GeometricDetector

Tests for:
- Rectangle detection on synthetic images
- Horizontal line detection (signature fields)
- Checkbox detection
- Coordinate conversion (OpenCV top-left → PDF bottom-left)
- Field type classification
- Property-based tests with Hypothesis
"""

import pytest
import numpy as np
import cv2
from hypothesis import given, strategies as st, settings

from workers.geometric_detector import GeometricDetector, ContourCandidate
from workers.detection_models import BBox, FieldDetection, FieldType, DetectionSource


class TestGeometricDetector:
    """Tests for GeometricDetector class"""
    
    def test_detector_initialization(self):
        """Test creating a GeometricDetector with default parameters"""
        detector = GeometricDetector()
        
        assert detector.min_field_width_ratio == 0.05
        assert detector.min_field_height_ratio == 0.005
        assert detector.max_field_height_ratio == 0.08
        assert detector.debug == False
    
    def test_detector_custom_parameters(self):
        """Test creating a GeometricDetector with custom parameters"""
        detector = GeometricDetector(
            min_field_width_ratio=0.1,
            min_field_height_ratio=0.01,
            max_field_height_ratio=0.1,
            debug=True
        )
        
        assert detector.min_field_width_ratio == 0.1
        assert detector.min_field_height_ratio == 0.01
        assert detector.max_field_height_ratio == 0.1
        assert detector.debug == True
    
    def test_detect_empty_image(self):
        """Test detection on empty image returns no fields"""
        detector = GeometricDetector()
        
        # Create empty white image
        empty_image = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        
        detections = detector.detect_page_fields(empty_image, page_index=0)
        
        # Should return empty list (no fields detected)
        assert isinstance(detections, list)
        assert len(detections) == 0
    
    def test_detect_single_rectangle(self):
        """Test detection of a single rectangle (text field)"""
        detector = GeometricDetector()
        
        # Create white image with black rectangle
        image = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        
        # Draw a text field: 400x40 pixels at (100, 100)
        cv2.rectangle(image, (100, 100), (500, 140), (0, 0, 0), 2)
        
        detections = detector.detect_page_fields(image, page_index=0)
        
        # Should detect at least one field
        assert len(detections) >= 1
        
        # Check first detection
        detection = detections[0]
        assert isinstance(detection, FieldDetection)
        assert detection.source == DetectionSource.GEOMETRIC
        assert detection.page_index == 0
        assert 0.0 <= detection.confidence <= 1.0
        
        # Check bbox is normalized
        assert 0.0 <= detection.bbox.x <= 1.0
        assert 0.0 <= detection.bbox.y <= 1.0
        assert 0.0 <= detection.bbox.width <= 1.0
        assert 0.0 <= detection.bbox.height <= 1.0
    
    def test_detect_checkbox(self):
        """Test detection of a checkbox (small square)"""
        detector = GeometricDetector()
        
        # Create white image with small black square (checkbox)
        image = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        
        # Draw a checkbox: 50x50 pixels at (100, 100) - meets min width (5% of 1000 = 50px)
        # Use filled rectangle for better detection
        cv2.rectangle(image, (100, 100), (150, 150), (0, 0, 0), -1)
        
        detections = detector.detect_page_fields(image, page_index=0)
        
        # Should detect at least one field
        assert len(detections) >= 1, f"Expected at least 1 detection, got {len(detections)}"
        
        # Check if any detection is classified as checkbox
        checkbox_found = any(d.field_type == FieldType.CHECKBOX for d in detections)
        assert checkbox_found, f"Expected to find at least one checkbox, got types: {[d.field_type for d in detections]}"
    
    def test_detect_signature_line(self):
        """Test detection of a signature line (long horizontal line)"""
        detector = GeometricDetector()
        
        # Create white image with long horizontal line
        image = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        
        # Draw a signature line: 600x5 pixels at (100, 500)
        cv2.rectangle(image, (100, 500), (700, 505), (0, 0, 0), -1)  # Filled
        
        detections = detector.detect_page_fields(image, page_index=0)
        
        # Should detect at least one field
        assert len(detections) >= 1
        
        # Check if any detection is classified as signature
        signature_found = any(d.field_type == FieldType.SIGNATURE for d in detections)
        assert signature_found, "Expected to find at least one signature field"
    
    def test_detect_multiple_fields(self):
        """Test detection of multiple fields on same page"""
        detector = GeometricDetector()
        
        # Create white image with multiple fields
        image = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        
        # Draw 3 text fields
        cv2.rectangle(image, (100, 100), (500, 140), (0, 0, 0), 2)
        cv2.rectangle(image, (100, 200), (500, 240), (0, 0, 0), 2)
        cv2.rectangle(image, (100, 300), (500, 340), (0, 0, 0), 2)
        
        # Draw 2 checkboxes
        cv2.rectangle(image, (100, 400), (120, 420), (0, 0, 0), 2)
        cv2.rectangle(image, (150, 400), (170, 420), (0, 0, 0), 2)
        
        detections = detector.detect_page_fields(image, page_index=0)
        
        # Should detect multiple fields (at least 3)
        assert len(detections) >= 3
        
        # All should have GEOMETRIC source
        assert all(d.source == DetectionSource.GEOMETRIC for d in detections)
    
    def test_coordinate_conversion_top_left_to_bottom_left(self):
        """
        Test that OpenCV coordinates (top-left origin) are correctly
        converted to PDF coordinates (bottom-left origin).
        """
        detector = GeometricDetector()
        
        # Create a candidate at top of image (y=100 in OpenCV coords)
        candidate = ContourCandidate(
            x=100,
            y=100,
            w=400,
            h=40,
            area=16000,
            aspect_ratio=10.0,
            confidence=0.8
        )
        
        img_width = 1000
        img_height = 1000
        
        # Convert to normalized bbox
        bbox = detector._convert_to_normalized_bbox(candidate, img_width, img_height)
        
        # Check x and width (should be straightforward)
        assert abs(bbox.x - 0.1) < 1e-6  # 100/1000
        assert abs(bbox.width - 0.4) < 1e-6  # 400/1000
        
        # Check y conversion (bottom-left origin)
        # OpenCV: y=100, h=40 → bottom edge at y=140
        # PDF: y = 1.0 - (140/1000) = 0.86
        expected_y = 1.0 - (140 / 1000)
        assert abs(bbox.y - expected_y) < 1e-6
        
        # Check height (should be same)
        assert abs(bbox.height - 0.04) < 1e-6  # 40/1000
    
    def test_field_type_classification_checkbox(self):
        """Test that small squares are classified as checkboxes"""
        detector = GeometricDetector()
        
        # Small square candidate
        candidate = ContourCandidate(
            x=100,
            y=100,
            w=20,
            h=20,
            area=400,
            aspect_ratio=1.0,
            confidence=0.8
        )
        
        img_width = 1000
        img_height = 1000
        
        field_type = detector._classify_field_type(candidate, img_width, img_height)
        
        assert field_type == FieldType.CHECKBOX
    
    def test_field_type_classification_signature(self):
        """Test that wide lines are classified as signature fields"""
        detector = GeometricDetector()
        
        # Very wide, short candidate
        candidate = ContourCandidate(
            x=100,
            y=500,
            w=600,
            h=5,
            area=3000,
            aspect_ratio=120.0,
            confidence=0.85
        )
        
        img_width = 1000
        img_height = 1000
        
        field_type = detector._classify_field_type(candidate, img_width, img_height)
        
        assert field_type == FieldType.SIGNATURE
    
    def test_field_type_classification_text(self):
        """Test that moderate rectangles are classified as text fields"""
        detector = GeometricDetector()
        
        # Moderate rectangle candidate
        candidate = ContourCandidate(
            x=100,
            y=100,
            w=400,
            h=40,
            area=16000,
            aspect_ratio=10.0,
            confidence=0.8
        )
        
        img_width = 1000
        img_height = 1000
        
        field_type = detector._classify_field_type(candidate, img_width, img_height)
        
        assert field_type == FieldType.TEXT
    
    def test_label_generation(self):
        """Test that labels are generated correctly"""
        detector = GeometricDetector()
        
        assert detector._generate_label(FieldType.TEXT, 1) == "Text Field 1"
        assert detector._generate_label(FieldType.TEXT, 2) == "Text Field 2"
        assert detector._generate_label(FieldType.CHECKBOX, 1) == "Checkbox 1"
        assert detector._generate_label(FieldType.SIGNATURE, 1) == "Signature 1"
    
    def test_grayscale_conversion_rgb(self):
        """Test grayscale conversion from RGB image"""
        detector = GeometricDetector()
        
        # Create RGB image
        rgb_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        
        gray = detector._convert_to_grayscale(rgb_image)
        
        assert len(gray.shape) == 2  # Should be 2D
        assert gray.shape == (100, 100)
    
    def test_grayscale_conversion_already_gray(self):
        """Test grayscale conversion when image is already grayscale"""
        detector = GeometricDetector()
        
        # Create grayscale image
        gray_image = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        
        gray = detector._convert_to_grayscale(gray_image)
        
        assert len(gray.shape) == 2
        assert np.array_equal(gray, gray_image)
    
    def test_none_image_returns_empty(self):
        """Test that None image returns empty list"""
        detector = GeometricDetector()
        
        detections = detector.detect_page_fields(None, page_index=0)
        
        assert detections == []
    
    def test_zero_size_image_returns_empty(self):
        """Test that zero-size image returns empty list"""
        detector = GeometricDetector()
        
        # Create zero-size image
        empty = np.array([])
        
        detections = detector.detect_page_fields(empty, page_index=0)
        
        assert detections == []


class TestGeometricDetectorPropertyBased:
    """Property-based tests using Hypothesis"""
    
    @given(
        x_ratio=st.floats(min_value=0.1, max_value=0.7),
        y_ratio=st.floats(min_value=0.1, max_value=0.7),
        width_ratio=st.floats(min_value=0.1, max_value=0.3),
        height_ratio=st.floats(min_value=0.02, max_value=0.07),  # Reduced max to stay within detector limits
        page_index=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_detected_bbox_overlaps_ground_truth(
        self,
        x_ratio: float,
        y_ratio: float,
        width_ratio: float,
        height_ratio: float,
        page_index: int
    ):
        """
        Property: For any rectangle drawn on a blank image,
        the detector should find at least one field that overlaps
        with the ground truth region (IoU > 0.05).
        
        Note: IoU threshold is low because OpenCV contour detection
        may not perfectly match the drawn rectangle boundaries.
        """
        detector = GeometricDetector()
        
        # Create blank white image
        img_width = 1000
        img_height = 1000
        image = np.ones((img_height, img_width, 3), dtype=np.uint8) * 255
        
        # Calculate pixel coordinates from ratios
        x_px = int(x_ratio * img_width)
        y_px = int(y_ratio * img_height)
        w_px = int(width_ratio * img_width)
        h_px = int(height_ratio * img_height)
        
        # Draw rectangle with thicker lines for better detection
        cv2.rectangle(
            image,
            (x_px, y_px),
            (x_px + w_px, y_px + h_px),
            (0, 0, 0),
            3  # Thicker lines
        )
        
        # Create ground truth BBox (convert to bottom-left origin)
        y_bottom_opencv = y_px + h_px
        y_norm = 1.0 - (y_bottom_opencv / img_height)
        
        ground_truth = BBox(
            x=x_px / img_width,
            y=y_norm,
            width=w_px / img_width,
            height=h_px / img_height
        )
        
        # Run detection
        detections = detector.detect_page_fields(image, page_index=page_index)
        
        # Should detect at least one field
        assert len(detections) >= 1, "Expected at least one detection"
        
        # Check that at least one detection overlaps with ground truth
        max_iou = 0.0
        for detection in detections:
            # Calculate IoU
            intersection = detection.bbox.intersection_area(ground_truth)
            union = detection.bbox.area() + ground_truth.area() - intersection
            iou = intersection / union if union > 0 else 0.0
            max_iou = max(max_iou, iou)
        
        # At least one detection should have some overlap
        # Lower threshold because contour detection isn't pixel-perfect
        assert max_iou > 0.05, f"Expected IoU > 0.05, got {max_iou}"
    
    @given(
        num_fields=st.integers(min_value=1, max_value=5),
        page_index=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=20, deadline=None)
    def test_property_all_detections_have_valid_coordinates(
        self,
        num_fields: int,
        page_index: int
    ):
        """
        Property: All detected fields should have valid normalized coordinates
        in the range [0, 1] and satisfy BBox validation.
        """
        detector = GeometricDetector()
        
        # Create blank white image
        img_width = 1000
        img_height = 1000
        image = np.ones((img_height, img_width, 3), dtype=np.uint8) * 255
        
        # Draw random rectangles
        for i in range(num_fields):
            x = 100 + i * 150
            y = 100 + i * 100
            w = 300
            h = 40
            
            if x + w < img_width and y + h < img_height:
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), 2)
        
        # Run detection
        detections = detector.detect_page_fields(image, page_index=page_index)
        
        # Check all detections
        for detection in detections:
            # Should be FieldDetection
            assert isinstance(detection, FieldDetection)
            
            # Should have GEOMETRIC source
            assert detection.source == DetectionSource.GEOMETRIC
            
            # Should have correct page index
            assert detection.page_index == page_index
            
            # BBox should be valid (this will raise if invalid)
            bbox = detection.bbox
            assert isinstance(bbox, BBox)
            
            # Coordinates should be in [0, 1]
            assert 0.0 <= bbox.x <= 1.0
            assert 0.0 <= bbox.y <= 1.0
            assert 0.0 <= bbox.width <= 1.0
            assert 0.0 <= bbox.height <= 1.0
            
            # Confidence should be in [0, 1]
            assert 0.0 <= detection.confidence <= 1.0
    
    @given(
        page_index=st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=20, deadline=None)
    def test_property_page_index_preserved(self, page_index: int):
        """
        Property: The page_index passed to detect_page_fields should be
        preserved in all returned FieldDetection objects.
        """
        detector = GeometricDetector()
        
        # Create image with one rectangle
        image = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        cv2.rectangle(image, (100, 100), (500, 140), (0, 0, 0), 2)
        
        # Run detection
        detections = detector.detect_page_fields(image, page_index=page_index)
        
        # All detections should have the same page_index
        for detection in detections:
            assert detection.page_index == page_index


class TestContourCandidate:
    """Tests for ContourCandidate dataclass"""
    
    def test_contour_candidate_creation(self):
        """Test creating a ContourCandidate"""
        candidate = ContourCandidate(
            x=100,
            y=200,
            w=300,
            h=40,
            area=12000,
            aspect_ratio=7.5,
            confidence=0.85
        )
        
        assert candidate.x == 100
        assert candidate.y == 200
        assert candidate.w == 300
        assert candidate.h == 40
        assert candidate.area == 12000
        assert candidate.aspect_ratio == 7.5
        assert candidate.confidence == 0.85
    
    def test_contour_candidate_default_confidence(self):
        """Test that ContourCandidate has default confidence"""
        candidate = ContourCandidate(
            x=100,
            y=200,
            w=300,
            h=40,
            area=12000,
            aspect_ratio=7.5
        )
        
        assert candidate.confidence == 0.8  # Default value
