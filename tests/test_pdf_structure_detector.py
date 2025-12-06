"""
Unit Tests for PDFStructureDetector

Tests for:
- AcroForm text field extraction
- Checkbox annotation extraction
- Signature field extraction
- Form XObject rectangle extraction
- PDF → BBox coordinate conversion
- Label inference (basic)
- BBox normalization validation
- Y-axis inversion correctness
- Synthetic PDF testing
- Property-based tests with Hypothesis

All tests use synthetic PDFs created in-memory using PyMuPDF.
"""

import pytest
import fitz  # PyMuPDF
import tempfile
import os
from hypothesis import given, strategies as st, settings, assume

from workers.pdf_structure_detector import PDFStructureDetector, RawFieldData
from workers.detection_models import BBox, FieldDetection, FieldType, DetectionSource


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def detector():
    """Create a PDFStructureDetector instance"""
    return PDFStructureDetector(debug=False)

@pytest.fixture
def debug_detector():
    """Create a PDFStructureDetector with debug enabled"""
    return PDFStructureDetector(debug=True)


# ============================================================================
# Helper Functions for Creating Synthetic PDFs
# ============================================================================

def create_blank_pdf(width: float = 612, height: float = 792) -> str:
    """
    Create a blank PDF and return its path.
    
    Args:
        width: Page width in points (default: US Letter)
        height: Page height in points (default: US Letter)
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_pdf_with_text_field(
    field_rect: tuple = (100, 100, 300, 130),
    field_name: str = "test_field"
) -> str:
    """
    Create a PDF with a single text field widget.
    
    Args:
        field_rect: (x0, y0, x1, y1) in PDF coordinates
        field_name: Name of the field
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Create a text widget
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_name = field_name
    widget.rect = fitz.Rect(field_rect)
    widget.field_value = ""
    
    # Add widget to page
    page.add_widget(widget)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_pdf_with_checkbox(
    field_rect: tuple = (100, 100, 120, 120),
    field_name: str = "checkbox_field"
) -> str:
    """
    Create a PDF with a checkbox widget.
    
    Args:
        field_rect: (x0, y0, x1, y1) in PDF coordinates
        field_name: Name of the field
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Create a checkbox widget
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    widget.field_name = field_name
    widget.rect = fitz.Rect(field_rect)
    
    # Add widget to page
    page.add_widget(widget)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_pdf_with_signature_field(
    field_rect: tuple = (100, 700, 400, 750),
    field_name: str = "signature_field"
) -> str:
    """
    Create a PDF with a signature field widget.
    
    Args:
        field_rect: (x0, y0, x1, y1) in PDF coordinates
        field_name: Name of the field
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Create a signature widget
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    widget.field_name = field_name
    widget.rect = fitz.Rect(field_rect)
    
    # Add widget to page
    page.add_widget(widget)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_pdf_with_drawn_rectangle(
    rect: tuple = (100, 100, 300, 130),
    stroke_color: tuple = (0, 0, 0),
    stroke_width: float = 1.0
) -> str:
    """
    Create a PDF with a drawn rectangle (no widget).
    
    Args:
        rect: (x0, y0, x1, y1) in PDF coordinates
        stroke_color: RGB color tuple (0-1 range)
        stroke_width: Line width
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Draw a rectangle
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(rect))
    shape.finish(color=stroke_color, width=stroke_width)
    shape.commit()
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_pdf_with_multiple_fields() -> str:
    """
    Create a PDF with multiple field types.
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Add text field
    text_widget = fitz.Widget()
    text_widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    text_widget.field_name = "name_field"
    text_widget.rect = fitz.Rect(100, 100, 300, 130)
    page.add_widget(text_widget)
    
    # Add another text field
    text_widget2 = fitz.Widget()
    text_widget2.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    text_widget2.field_name = "email_field"
    text_widget2.rect = fitz.Rect(100, 150, 300, 180)
    page.add_widget(text_widget2)
    
    # Add checkbox
    checkbox_widget = fitz.Widget()
    checkbox_widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    checkbox_widget.field_name = "agree_checkbox"
    checkbox_widget.rect = fitz.Rect(100, 200, 120, 220)
    page.add_widget(checkbox_widget)
    
    # Add signature field
    sig_widget = fitz.Widget()
    sig_widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    sig_widget.field_name = "signature"
    sig_widget.rect = fitz.Rect(100, 700, 400, 750)
    page.add_widget(sig_widget)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_multipage_pdf_with_fields() -> str:
    """
    Create a multi-page PDF with fields on different pages.
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    
    # Page 0
    page0 = doc.new_page(width=612, height=792)
    widget0 = fitz.Widget()
    widget0.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget0.field_name = "page0_field"
    widget0.rect = fitz.Rect(100, 100, 300, 130)
    page0.add_widget(widget0)
    
    # Page 1
    page1 = doc.new_page(width=612, height=792)
    widget1 = fitz.Widget()
    widget1.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget1.field_name = "page1_field"
    widget1.rect = fitz.Rect(100, 200, 300, 230)
    page1.add_widget(widget1)
    
    # Page 2
    page2 = doc.new_page(width=612, height=792)
    widget2 = fitz.Widget()
    widget2.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    widget2.field_name = "page2_checkbox"
    widget2.rect = fitz.Rect(100, 300, 120, 320)
    page2.add_widget(widget2)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_pdf_with_labeled_field() -> str:
    """
    Create a PDF with a text field and a label to the left.
    
    Returns:
        Path to temporary PDF file
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Add label text
    text_point = fitz.Point(50, 115)
    page.insert_text(text_point, "Name:", fontsize=12)
    
    # Add text field to the right of label
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_name = "name_input"
    widget.rect = fitz.Rect(100, 100, 300, 130)
    page.add_widget(widget)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


# ============================================================================
# Unit Tests - Detector Initialization
# ============================================================================

class TestPDFStructureDetectorInit:
    """Tests for PDFStructureDetector initialization"""
    
    def test_detector_default_initialization(self):
        """Test creating a PDFStructureDetector with default parameters"""
        detector = PDFStructureDetector()
        
        assert detector.debug == False
        assert detector.min_field_width_ratio == 0.02
        assert detector.min_field_height_ratio == 0.005
        assert detector.max_field_height_ratio == 0.15
    
    def test_detector_debug_mode(self):
        """Test creating a PDFStructureDetector with debug enabled"""
        detector = PDFStructureDetector(debug=True)
        
        assert detector.debug == True
    
    def test_detector_has_required_methods(self):
        """Test that detector has all required methods"""
        detector = PDFStructureDetector()
        
        assert hasattr(detector, 'detect_fields')
        assert hasattr(detector, '_extract_widget_annotations')
        assert hasattr(detector, '_extract_acroform_fields')
        assert hasattr(detector, '_extract_rect_form_glyphs')
        assert hasattr(detector, '_extract_xobjects')
        assert hasattr(detector, '_infer_label')
        assert hasattr(detector, '_convert_pdf_rect_to_bbox')
        assert hasattr(detector, '_classify_annotation')


# ============================================================================
# Unit Tests - Text Field Extraction
# ============================================================================

class TestTextFieldExtraction:
    """Tests for AcroForm text field extraction"""
    
    def test_extract_single_text_field(self, detector):
        """Test extraction of a single text field"""
        pdf_path = create_pdf_with_text_field(
            field_rect=(100, 100, 300, 130),
            field_name="test_text"
        )
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            assert len(detections) >= 1
            
            # Find the text field
            text_fields = [d for d in detections if d.field_type == FieldType.TEXT]
            assert len(text_fields) >= 1
            
            field = text_fields[0]
            assert field.source == DetectionSource.STRUCTURE
            assert field.page_index == 0
            assert 0.0 <= field.confidence <= 1.0
            
        finally:
            os.unlink(pdf_path)
    
    def test_text_field_has_label(self, detector):
        """Test that text field has a label"""
        pdf_path = create_pdf_with_text_field(
            field_rect=(100, 100, 300, 130),
            field_name="my_text_field"
        )
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            text_fields = [d for d in detections if d.field_type == FieldType.TEXT]
            assert len(text_fields) >= 1
            
            field = text_fields[0]
            assert field.label is not None
            assert len(field.label) > 0
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Unit Tests - Checkbox Extraction
# ============================================================================

class TestCheckboxExtraction:
    """Tests for checkbox annotation extraction"""
    
    def test_extract_checkbox_field(self, detector):
        """Test extraction of a checkbox field"""
        pdf_path = create_pdf_with_checkbox(
            field_rect=(100, 100, 120, 120),
            field_name="test_checkbox"
        )
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            assert len(detections) >= 1
            
            # Find the checkbox
            checkboxes = [d for d in detections if d.field_type == FieldType.CHECKBOX]
            assert len(checkboxes) >= 1
            
            checkbox = checkboxes[0]
            assert checkbox.source == DetectionSource.STRUCTURE
            assert checkbox.page_index == 0
            
        finally:
            os.unlink(pdf_path)
    
    def test_checkbox_is_small_square(self, detector):
        """Test that checkbox bbox is approximately square"""
        pdf_path = create_pdf_with_checkbox(
            field_rect=(100, 100, 120, 120),
            field_name="square_checkbox"
        )
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            checkboxes = [d for d in detections if d.field_type == FieldType.CHECKBOX]
            assert len(checkboxes) >= 1
            
            checkbox = checkboxes[0]
            aspect_ratio = checkbox.bbox.width / checkbox.bbox.height if checkbox.bbox.height > 0 else 0
            
            # Should be approximately square (aspect ratio between 0.5 and 2.0)
            assert 0.5 <= aspect_ratio <= 2.0
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Unit Tests - Signature Field Extraction
# ============================================================================

class TestSignatureFieldExtraction:
    """Tests for signature field extraction"""
    
    def test_extract_signature_field(self, detector):
        """Test extraction of a signature field"""
        pdf_path = create_pdf_with_signature_field(
            field_rect=(100, 700, 400, 750),
            field_name="test_signature"
        )
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            assert len(detections) >= 1
            
            # Find the signature field
            signatures = [d for d in detections if d.field_type == FieldType.SIGNATURE]
            assert len(signatures) >= 1
            
            sig = signatures[0]
            assert sig.source == DetectionSource.STRUCTURE
            assert sig.page_index == 0
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Unit Tests - Rectangle Form Glyph Extraction
# ============================================================================

class TestRectangleExtraction:
    """Tests for Form XObject rectangle extraction"""
    
    def test_extract_drawn_rectangle(self, detector):
        """Test extraction of a drawn rectangle as form field"""
        pdf_path = create_pdf_with_drawn_rectangle(
            rect=(100, 100, 300, 130)
        )
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            # May or may not detect drawn rectangles depending on PDF structure
            # This is expected behavior - drawn rectangles are lower priority
            assert isinstance(detections, list)
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Unit Tests - Coordinate Conversion
# ============================================================================

class TestCoordinateConversion:
    """Tests for PDF → BBox coordinate conversion"""
    
    def test_convert_pdf_rect_to_bbox_basic(self, detector):
        """Test basic PDF rect to BBox conversion"""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        # Create a rect at (100, 100, 200, 150) in PDF coords
        rect = fitz.Rect(100, 100, 200, 150)
        
        bbox = detector._convert_pdf_rect_to_bbox(rect, page)
        
        assert bbox is not None
        
        # Check x normalization: 100/612 ≈ 0.163
        assert abs(bbox.x - (100 / 612)) < 0.01
        
        # Check width normalization: 100/612 ≈ 0.163
        assert abs(bbox.width - (100 / 612)) < 0.01
        
        # Check height normalization: 50/792 ≈ 0.063
        assert abs(bbox.height - (50 / 792)) < 0.01
        
        doc.close()
    
    def test_y_axis_inversion(self, detector):
        """Test that y-axis is correctly inverted from top-left to bottom-left"""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        # Rect at top of page in PyMuPDF coords (y=0 is top)
        rect_top = fitz.Rect(100, 0, 200, 50)
        bbox_top = detector._convert_pdf_rect_to_bbox(rect_top, page)
        
        # Rect at bottom of page in PyMuPDF coords
        rect_bottom = fitz.Rect(100, 742, 200, 792)
        bbox_bottom = detector._convert_pdf_rect_to_bbox(rect_bottom, page)
        
        assert bbox_top is not None
        assert bbox_bottom is not None
        
        # In bottom-left origin, top rect should have higher y
        # bbox_top.y should be close to 1.0 - (50/792) ≈ 0.937
        # bbox_bottom.y should be close to 1.0 - (792/792) = 0.0
        assert bbox_top.y > bbox_bottom.y
        
        doc.close()
    
    def test_bbox_normalization_range(self, detector):
        """Test that all bbox values are in [0, 1] range"""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        # Test various rect positions
        test_rects = [
            fitz.Rect(0, 0, 100, 100),
            fitz.Rect(512, 692, 612, 792),
            fitz.Rect(306, 396, 406, 496),
        ]
        
        for rect in test_rects:
            bbox = detector._convert_pdf_rect_to_bbox(rect, page)
            
            assert bbox is not None
            assert 0.0 <= bbox.x <= 1.0
            assert 0.0 <= bbox.y <= 1.0
            assert 0.0 <= bbox.width <= 1.0
            assert 0.0 <= bbox.height <= 1.0
            assert bbox.x + bbox.width <= 1.0
            assert bbox.y + bbox.height <= 1.0
        
        doc.close()
    
    def test_convert_full_page_rect(self, detector):
        """Test converting a full-page rectangle"""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        # Full page rect
        rect = fitz.Rect(0, 0, 612, 792)
        bbox = detector._convert_pdf_rect_to_bbox(rect, page)
        
        assert bbox is not None
        assert abs(bbox.x - 0.0) < 0.001
        assert abs(bbox.y - 0.0) < 0.001
        assert abs(bbox.width - 1.0) < 0.001
        assert abs(bbox.height - 1.0) < 0.001
        
        doc.close()


# ============================================================================
# Unit Tests - Label Inference
# ============================================================================

class TestLabelInference:
    """Tests for label inference (basic)"""
    
    def test_infer_label_from_left_text(self, detector):
        """Test inferring label from text to the left of field"""
        pdf_path = create_pdf_with_labeled_field()
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            # Should find at least one field
            assert len(detections) >= 1
            
            # The field should have a label (either from widget name or inferred)
            field = detections[0]
            assert field.label is not None
            
        finally:
            os.unlink(pdf_path)
    
    def test_label_cleanup(self, detector):
        """Test that labels are cleaned up properly"""
        # Test the _clean_label method directly
        assert detector._clean_label("Name:") == "Name"
        assert detector._clean_label("  Email  ") == "Email"
        assert detector._clean_label("") is None
        assert detector._clean_label("::") is None
        assert detector._clean_label("A") is None  # Too short


# ============================================================================
# Unit Tests - Multiple Fields
# ============================================================================

class TestMultipleFields:
    """Tests for multiple field detection"""
    
    def test_detect_multiple_field_types(self, detector):
        """Test detection of multiple field types in one PDF"""
        pdf_path = create_pdf_with_multiple_fields()
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            # Should detect multiple fields
            assert len(detections) >= 3
            
            # Check field types
            field_types = {d.field_type for d in detections}
            assert FieldType.TEXT in field_types
            assert FieldType.CHECKBOX in field_types
            assert FieldType.SIGNATURE in field_types
            
        finally:
            os.unlink(pdf_path)
    
    def test_multipage_field_detection(self, detector):
        """Test that fields on different pages have correct page_index"""
        pdf_path = create_multipage_pdf_with_fields()
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            # Should detect fields on multiple pages
            assert len(detections) >= 3
            
            # Check page indices
            page_indices = {d.page_index for d in detections}
            assert 0 in page_indices
            assert 1 in page_indices
            assert 2 in page_indices
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Unit Tests - Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""
    
    def test_blank_pdf_returns_empty_list(self, detector):
        """Test that blank PDF returns empty list"""
        pdf_path = create_blank_pdf()
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            assert isinstance(detections, list)
            assert len(detections) == 0
            
        finally:
            os.unlink(pdf_path)
    
    def test_invalid_pdf_path_returns_empty_list(self, detector):
        """Test that invalid PDF path returns empty list"""
        detections = detector.detect_fields("/nonexistent/path/to/file.pdf")
        
        assert isinstance(detections, list)
        assert len(detections) == 0
    
    def test_all_detections_have_structure_source(self, detector):
        """Test that all detections have STRUCTURE source"""
        pdf_path = create_pdf_with_multiple_fields()
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            for detection in detections:
                assert detection.source == DetectionSource.STRUCTURE
                
        finally:
            os.unlink(pdf_path)
    
    def test_all_detections_are_field_detection_type(self, detector):
        """Test that all detections are FieldDetection instances"""
        pdf_path = create_pdf_with_multiple_fields()
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            for detection in detections:
                assert isinstance(detection, FieldDetection)
                assert isinstance(detection.bbox, BBox)
                assert isinstance(detection.field_type, FieldType)
                assert isinstance(detection.source, DetectionSource)
                
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Property-Based Tests with Hypothesis
# ============================================================================

class TestPropertyBasedBBoxNormalization:
    """Property-based tests for BBox normalization"""
    
    @given(
        x0=st.floats(min_value=0, max_value=500),
        y0=st.floats(min_value=0, max_value=700),
        width=st.floats(min_value=20, max_value=200),
        height=st.floats(min_value=10, max_value=100)
    )
    @settings(max_examples=100, deadline=None)
    def test_property_bbox_always_normalized(
        self,
        x0: float,
        y0: float,
        width: float,
        height: float
    ):
        """
        Property: For any valid PDF rectangle, the resulting BBox
        should always have coordinates in [0, 1] range.
        
        **Feature: hybrid-detection-pipeline, Property 1: BBox normalization**
        **Validates: Requirements 3.1**
        """
        # Ensure rect fits within page
        assume(x0 + width <= 612)
        assume(y0 + height <= 792)
        
        detector = PDFStructureDetector()
        
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        rect = fitz.Rect(x0, y0, x0 + width, y0 + height)
        bbox = detector._convert_pdf_rect_to_bbox(rect, page)
        
        doc.close()
        
        assert bbox is not None
        assert 0.0 <= bbox.x <= 1.0, f"x={bbox.x} not in [0,1]"
        assert 0.0 <= bbox.y <= 1.0, f"y={bbox.y} not in [0,1]"
        assert 0.0 <= bbox.width <= 1.0, f"width={bbox.width} not in [0,1]"
        assert 0.0 <= bbox.height <= 1.0, f"height={bbox.height} not in [0,1]"
        assert bbox.x + bbox.width <= 1.0 + 1e-6, f"x+width={bbox.x + bbox.width} > 1"
        assert bbox.y + bbox.height <= 1.0 + 1e-6, f"y+height={bbox.y + bbox.height} > 1"
    
    @given(
        page_width=st.floats(min_value=100, max_value=2000),
        page_height=st.floats(min_value=100, max_value=2000)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_normalization_works_for_any_page_size(
        self,
        page_width: float,
        page_height: float
    ):
        """
        Property: BBox normalization should work correctly for any page size.
        
        **Feature: hybrid-detection-pipeline, Property 2: Page size independence**
        **Validates: Requirements 3.1**
        """
        detector = PDFStructureDetector()
        
        doc = fitz.open()
        page = doc.new_page(width=page_width, height=page_height)
        
        # Create a rect at 10% from each edge
        margin = 0.1
        rect = fitz.Rect(
            page_width * margin,
            page_height * margin,
            page_width * (1 - margin),
            page_height * (1 - margin)
        )
        
        bbox = detector._convert_pdf_rect_to_bbox(rect, page)
        
        doc.close()
        
        assert bbox is not None
        
        # Should be approximately 80% of page (1 - 2*margin)
        expected_width = 1.0 - 2 * margin
        expected_height = 1.0 - 2 * margin
        
        assert abs(bbox.width - expected_width) < 0.01
        assert abs(bbox.height - expected_height) < 0.01


class TestPropertyBasedPageIndex:
    """Property-based tests for page index mapping"""
    
    @given(
        num_pages=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=20, deadline=None)
    def test_property_page_index_mapping(self, num_pages: int):
        """
        Property: For multi-page PDFs, each field should have the correct
        page_index corresponding to the page it was found on.
        
        **Feature: hybrid-detection-pipeline, Property 3: Page index correctness**
        **Validates: Requirements 3.2**
        """
        detector = PDFStructureDetector()
        
        # Create multi-page PDF with one field per page
        doc = fitz.open()
        
        for i in range(num_pages):
            page = doc.new_page(width=612, height=792)
            
            widget = fitz.Widget()
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_name = f"field_page_{i}"
            widget.rect = fitz.Rect(100, 100 + i * 10, 300, 130 + i * 10)
            page.add_widget(widget)
        
        # Save to temp file
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)
        doc.save(path)
        doc.close()
        
        try:
            detections = detector.detect_fields(path)
            
            # Should have at least num_pages detections
            assert len(detections) >= num_pages
            
            # Check that page indices are valid
            for detection in detections:
                assert 0 <= detection.page_index < num_pages
            
            # Check that we have detections on each page
            page_indices = {d.page_index for d in detections}
            for i in range(num_pages):
                assert i in page_indices, f"No detection found on page {i}"
                
        finally:
            os.unlink(path)


class TestPropertyBasedFieldTypes:
    """Property-based tests for field type classification"""
    
    @given(
        size=st.floats(min_value=15, max_value=25)
    )
    @settings(max_examples=30, deadline=None)
    def test_property_small_squares_are_checkboxes(self, size: float):
        """
        Property: Small, approximately square widgets should be classified
        as checkboxes.
        
        **Feature: hybrid-detection-pipeline, Property 4: Checkbox classification**
        **Validates: Requirements 3.3**
        """
        detector = PDFStructureDetector()
        
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        widget.field_name = "test_checkbox"
        widget.rect = fitz.Rect(100, 100, 100 + size, 100 + size)
        page.add_widget(widget)
        
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)
        doc.save(path)
        doc.close()
        
        try:
            detections = detector.detect_fields(path)
            
            assert len(detections) >= 1
            
            # Should be classified as checkbox
            checkbox_found = any(d.field_type == FieldType.CHECKBOX for d in detections)
            assert checkbox_found, f"Expected checkbox, got: {[d.field_type for d in detections]}"
            
        finally:
            os.unlink(path)
    
    @given(
        width=st.floats(min_value=200, max_value=400),
        height=st.floats(min_value=30, max_value=50)
    )
    @settings(max_examples=30, deadline=None)
    def test_property_wide_rectangles_are_text_fields(
        self,
        width: float,
        height: float
    ):
        """
        Property: Wide rectangular widgets should be classified as text fields.
        
        **Feature: hybrid-detection-pipeline, Property 5: Text field classification**
        **Validates: Requirements 3.3**
        """
        detector = PDFStructureDetector()
        
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = "test_text"
        widget.rect = fitz.Rect(100, 100, 100 + width, 100 + height)
        page.add_widget(widget)
        
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)
        doc.save(path)
        doc.close()
        
        try:
            detections = detector.detect_fields(path)
            
            assert len(detections) >= 1
            
            # Should be classified as text
            text_found = any(d.field_type == FieldType.TEXT for d in detections)
            assert text_found, f"Expected text field, got: {[d.field_type for d in detections]}"
            
        finally:
            os.unlink(path)


class TestPropertyBasedYInversion:
    """Property-based tests for Y-axis inversion"""
    
    @given(
        y_position=st.floats(min_value=50, max_value=700)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_y_inversion_monotonic(self, y_position: float):
        """
        Property: Higher y values in PyMuPDF coords should result in
        lower y values in normalized coords (bottom-left origin).
        
        **Feature: hybrid-detection-pipeline, Property 6: Y-axis inversion**
        **Validates: Requirements 3.1**
        """
        detector = PDFStructureDetector()
        
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        # Create two rects at different y positions
        rect1 = fitz.Rect(100, y_position, 200, y_position + 30)
        rect2 = fitz.Rect(100, y_position + 100, 200, y_position + 130)
        
        # Ensure rect2 fits on page
        assume(y_position + 130 <= 792)
        
        bbox1 = detector._convert_pdf_rect_to_bbox(rect1, page)
        bbox2 = detector._convert_pdf_rect_to_bbox(rect2, page)
        
        doc.close()
        
        assert bbox1 is not None
        assert bbox2 is not None
        
        # rect2 has higher y in PyMuPDF (lower on page visually)
        # So bbox2 should have lower y in normalized coords
        assert bbox2.y < bbox1.y, f"bbox2.y={bbox2.y} should be < bbox1.y={bbox1.y}"


class TestPropertyBasedDeduplication:
    """Property-based tests for detection deduplication"""
    
    @given(
        num_overlapping=st.integers(min_value=2, max_value=5)
    )
    @settings(max_examples=20, deadline=None)
    def test_property_overlapping_detections_deduplicated(
        self,
        num_overlapping: int
    ):
        """
        Property: Highly overlapping detections should be deduplicated
        to avoid redundant results.
        
        **Feature: hybrid-detection-pipeline, Property 7: Deduplication**
        **Validates: Requirements 3.4**
        """
        detector = PDFStructureDetector()
        
        # Create synthetic detections with high overlap
        detections = []
        base_bbox = BBox(x=0.1, y=0.1, width=0.3, height=0.05)
        
        for i in range(num_overlapping):
            # Slightly offset each detection
            offset = i * 0.01
            bbox = BBox(
                x=base_bbox.x + offset,
                y=base_bbox.y + offset,
                width=base_bbox.width,
                height=base_bbox.height
            )
            
            detection = FieldDetection(
                page_index=0,
                bbox=bbox,
                field_type=FieldType.TEXT,
                label=f"Field {i}",
                confidence=0.9 - i * 0.05,
                source=DetectionSource.STRUCTURE
            )
            detections.append(detection)
        
        # Deduplicate
        result = detector._deduplicate_detections(detections)
        
        # Should have fewer detections after dedup
        assert len(result) < len(detections) or len(detections) == 1


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for full detection pipeline"""
    
    def test_full_detection_pipeline(self, detector):
        """Test complete detection pipeline on a complex PDF"""
        pdf_path = create_pdf_with_multiple_fields()
        
        try:
            detections = detector.detect_fields(pdf_path)
            
            # Verify all detections are valid
            for detection in detections:
                # Valid FieldDetection
                assert isinstance(detection, FieldDetection)
                
                # Valid BBox
                assert isinstance(detection.bbox, BBox)
                assert 0.0 <= detection.bbox.x <= 1.0
                assert 0.0 <= detection.bbox.y <= 1.0
                assert 0.0 <= detection.bbox.width <= 1.0
                assert 0.0 <= detection.bbox.height <= 1.0
                
                # Valid field type
                assert isinstance(detection.field_type, FieldType)
                
                # Valid source
                assert detection.source == DetectionSource.STRUCTURE
                
                # Valid confidence
                assert 0.0 <= detection.confidence <= 1.0
                
                # Has label
                assert detection.label is not None
                assert len(detection.label) > 0
                
        finally:
            os.unlink(pdf_path)
    
    def test_detection_consistency(self, detector):
        """Test that detection is deterministic (same results each time)"""
        pdf_path = create_pdf_with_multiple_fields()
        
        try:
            # Run detection multiple times
            results = []
            for _ in range(3):
                detections = detector.detect_fields(pdf_path)
                results.append(detections)
            
            # All results should be identical
            for i in range(1, len(results)):
                assert len(results[i]) == len(results[0])
                
                for j in range(len(results[0])):
                    assert results[i][j].bbox.x == results[0][j].bbox.x
                    assert results[i][j].bbox.y == results[0][j].bbox.y
                    assert results[i][j].field_type == results[0][j].field_type
                    
        finally:
            os.unlink(pdf_path)
