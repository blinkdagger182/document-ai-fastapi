"""
Unit Tests for HybridDetectionPipeline

Tests for:
- Pipeline initialization
- Individual detector execution
- Error handling when detectors fail
- Integration with real PDF files
- Property-based tests for correctness

All tests use mock/fake detectors to isolate the pipeline logic.
"""

import pytest
import tempfile
import os
import numpy as np
from typing import List, Optional
from unittest.mock import Mock, MagicMock, patch
from hypothesis import given, strategies as st, settings

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from workers.hybrid_detection_pipeline import (
    HybridDetectionPipeline,
    VisionDetectorProtocol,
)
from workers.detection_models import BBox, FieldDetection, FieldType, DetectionSource
from workers.pdf_structure_detector import PDFStructureDetector
from workers.geometric_detector import GeometricDetector
from workers.ensemble_merger import EnsembleMerger


# ============================================================================
# Test Fixtures and Fake Detectors
# ============================================================================

def create_field_detection(
    page_index: int = 0,
    x: float = 0.1,
    y: float = 0.1,
    width: float = 0.3,
    height: float = 0.05,
    field_type: FieldType = FieldType.TEXT,
    label: str = "Test Field",
    confidence: float = 0.9,
    source: DetectionSource = DetectionSource.STRUCTURE,
) -> FieldDetection:
    """Helper to create a FieldDetection for testing"""
    return FieldDetection(
        page_index=page_index,
        bbox=BBox(x=x, y=y, width=width, height=height),
        field_type=field_type,
        label=label,
        confidence=confidence,
        source=source,
    )


class FakePDFStructureDetector:
    """Fake PDF structure detector that returns predefined fields"""
    
    def __init__(self, fields: Optional[List[FieldDetection]] = None):
        self.fields = fields or [
            create_field_detection(
                page_index=0,
                x=0.1, y=0.1, width=0.3, height=0.05,
                label="Structure Field 1",
                source=DetectionSource.STRUCTURE,
            ),
            create_field_detection(
                page_index=0,
                x=0.1, y=0.3, width=0.3, height=0.05,
                label="Structure Field 2",
                source=DetectionSource.STRUCTURE,
            ),
        ]
        self.call_count = 0
        self.last_pdf_path = None
    
    def detect_fields(self, pdf_path: str) -> List[FieldDetection]:
        self.call_count += 1
        self.last_pdf_path = pdf_path
        return self.fields


class FakeGeometricDetector:
    """Fake geometric detector that returns predefined fields"""
    
    def __init__(self, fields_per_page: Optional[dict] = None):
        self.fields_per_page = fields_per_page or {
            0: [],
            1: [
                create_field_detection(
                    page_index=1,
                    x=0.1, y=0.5, width=0.4, height=0.02,
                    field_type=FieldType.SIGNATURE,
                    label="Signature 1",
                    source=DetectionSource.GEOMETRIC,
                ),
                create_field_detection(
                    page_index=1,
                    x=0.1, y=0.6, width=0.3, height=0.05,
                    label="Geometric Field 1",
                    source=DetectionSource.GEOMETRIC,
                ),
                create_field_detection(
                    page_index=1,
                    x=0.5, y=0.6, width=0.03, height=0.03,
                    field_type=FieldType.CHECKBOX,
                    label="Checkbox 1",
                    source=DetectionSource.GEOMETRIC,
                ),
            ],
        }
        self.call_count = 0
        self.pages_processed = []
    
    def detect_page_fields(
        self,
        page_image: np.ndarray,
        page_index: int,
    ) -> List[FieldDetection]:
        self.call_count += 1
        self.pages_processed.append(page_index)
        return self.fields_per_page.get(page_index, [])


class FakeVisionDetector:
    """Fake vision detector that returns predefined fields"""
    
    def __init__(self, fields: Optional[List[FieldDetection]] = None):
        self.fields = fields or [
            create_field_detection(
                page_index=0,
                x=0.1, y=0.1, width=0.3, height=0.05,  # Overlaps with structure field
                label="Vision Field 1",
                source=DetectionSource.VISION,
            ),
        ]
        self.call_count = 0
        self.last_pdf_path = None
        self.last_document_id = None
    
    def detect_fields(
        self,
        pdf_path: str,
        document_id: Optional[str] = None,
    ) -> List[FieldDetection]:
        self.call_count += 1
        self.last_pdf_path = pdf_path
        self.last_document_id = document_id
        return self.fields


class FakeEnsembleMerger:
    """Fake ensemble merger that captures inputs and returns combined list"""
    
    def __init__(self):
        self.call_count = 0
        self.last_pdf_structure_fields = None
        self.last_geometric_fields = None
        self.last_vision_fields = None
    
    def merge(
        self,
        pdf_structure_fields: List[FieldDetection],
        geometric_fields: List[FieldDetection],
        vision_fields: List[FieldDetection],
    ) -> List[FieldDetection]:
        self.call_count += 1
        self.last_pdf_structure_fields = pdf_structure_fields
        self.last_geometric_fields = geometric_fields
        self.last_vision_fields = vision_fields
        
        # Return combined list (simple merge for testing)
        return pdf_structure_fields + geometric_fields + vision_fields


class FailingPDFStructureDetector:
    """PDF structure detector that always raises an exception"""
    
    def detect_fields(self, pdf_path: str) -> List[FieldDetection]:
        raise RuntimeError("PDF Structure Detector intentionally failed")


class FailingGeometricDetector:
    """Geometric detector that always raises an exception"""
    
    def detect_page_fields(
        self,
        page_image: np.ndarray,
        page_index: int,
    ) -> List[FieldDetection]:
        raise RuntimeError("Geometric Detector intentionally failed")


class FailingVisionDetector:
    """Vision detector that always raises an exception"""
    
    def detect_fields(
        self,
        pdf_path: str,
        document_id: Optional[str] = None,
    ) -> List[FieldDetection]:
        raise RuntimeError("Vision Detector intentionally failed")


def create_test_pdf_with_widget() -> str:
    """Create a simple PDF with a text widget for testing"""
    if fitz is None:
        pytest.skip("PyMuPDF not available")
    
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Add a text widget
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_name = "test_field"
    widget.rect = fitz.Rect(100, 100, 300, 130)
    page.add_widget(widget)
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


def create_blank_test_pdf(num_pages: int = 2) -> str:
    """Create a blank PDF with specified number of pages"""
    if fitz is None:
        pytest.skip("PyMuPDF not available")
    
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page(width=612, height=792)
    
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    doc.save(path)
    doc.close()
    
    return path


# ============================================================================
# Unit Tests - Initialization
# ============================================================================

class TestPipelineInitialization:
    """Tests for HybridDetectionPipeline initialization"""
    
    def test_default_initialization(self):
        """Test creating pipeline with default parameters"""
        pipeline = HybridDetectionPipeline()
        
        assert pipeline.pdf_structure_detector is not None
        assert pipeline.geometric_detector is not None
        assert pipeline.vision_detector is None  # Optional
        assert pipeline.ensemble_merger is not None
        assert pipeline.debug == False
    
    def test_custom_detectors(self):
        """Test creating pipeline with custom detectors"""
        fake_structure = FakePDFStructureDetector()
        fake_geometric = FakeGeometricDetector()
        fake_vision = FakeVisionDetector()
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=fake_geometric,
            vision_detector=fake_vision,
            ensemble_merger=fake_merger,
            debug=True,
        )
        
        assert pipeline.pdf_structure_detector is fake_structure
        assert pipeline.geometric_detector is fake_geometric
        assert pipeline.vision_detector is fake_vision
        assert pipeline.ensemble_merger is fake_merger
        assert pipeline.debug == True
    
    def test_custom_render_dpi(self):
        """Test creating pipeline with custom render DPI"""
        pipeline = HybridDetectionPipeline(render_dpi=200)
        
        assert pipeline.render_dpi == 200


# ============================================================================
# Unit Tests - Detector Execution with Mocks
# ============================================================================

class TestDetectorExecution:
    """Tests that each detector is called correctly"""
    
    def test_all_detectors_called(self):
        """Test that all detectors are called exactly once"""
        fake_structure = FakePDFStructureDetector()
        fake_geometric = FakeGeometricDetector()
        fake_vision = FakeVisionDetector()
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=fake_geometric,
            vision_detector=fake_vision,
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=2)
        
        try:
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Each detector should be called
            assert fake_structure.call_count == 1
            assert fake_geometric.call_count == 2  # Once per page
            assert fake_vision.call_count == 1
            assert fake_merger.call_count == 1
            
        finally:
            os.unlink(pdf_path)
    
    def test_merger_receives_all_fields(self):
        """Test that EnsembleMerger receives fields from all detectors"""
        fake_structure = FakePDFStructureDetector()
        fake_geometric = FakeGeometricDetector()
        fake_vision = FakeVisionDetector()
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=fake_geometric,
            vision_detector=fake_vision,
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=2)
        
        try:
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Check merger received correct fields
            assert fake_merger.last_pdf_structure_fields == fake_structure.fields
            assert len(fake_merger.last_geometric_fields) == 3  # From page 1
            assert fake_merger.last_vision_fields == fake_vision.fields
            
        finally:
            os.unlink(pdf_path)
    
    def test_output_equals_merger_output(self):
        """Test that pipeline output equals EnsembleMerger output"""
        fake_structure = FakePDFStructureDetector()
        fake_geometric = FakeGeometricDetector()
        fake_vision = FakeVisionDetector()
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=fake_geometric,
            vision_detector=fake_vision,
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=2)
        
        try:
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Result should be exactly what merger returns
            expected_count = (
                len(fake_structure.fields) +
                len(fake_geometric.fields_per_page.get(0, [])) +
                len(fake_geometric.fields_per_page.get(1, [])) +
                len(fake_vision.fields)
            )
            assert len(result) == expected_count
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Unit Tests - Error Handling
# ============================================================================

class TestErrorHandling:
    """Tests for error handling when detectors fail"""
    
    def test_structure_detector_failure_continues(self):
        """Test that pipeline continues when PDF structure detector fails"""
        fake_geometric = FakeGeometricDetector()
        fake_vision = FakeVisionDetector()
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=FailingPDFStructureDetector(),
            geometric_detector=fake_geometric,
            vision_detector=fake_vision,
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=2)
        
        try:
            # Should not raise exception
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Other detectors should still run
            assert fake_geometric.call_count == 2
            assert fake_vision.call_count == 1
            
            # Merger should receive empty list for structure
            assert fake_merger.last_pdf_structure_fields == []
            
        finally:
            os.unlink(pdf_path)
    
    def test_geometric_detector_failure_continues(self):
        """Test that pipeline continues when geometric detector fails"""
        fake_structure = FakePDFStructureDetector()
        fake_vision = FakeVisionDetector()
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=FailingGeometricDetector(),
            vision_detector=fake_vision,
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=2)
        
        try:
            # Should not raise exception
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Other detectors should still run
            assert fake_structure.call_count == 1
            assert fake_vision.call_count == 1
            
            # Merger should receive empty list for geometric
            assert fake_merger.last_geometric_fields == []
            
        finally:
            os.unlink(pdf_path)
    
    def test_vision_detector_failure_continues(self):
        """Test that pipeline continues when vision detector fails"""
        fake_structure = FakePDFStructureDetector()
        fake_geometric = FakeGeometricDetector()
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=fake_geometric,
            vision_detector=FailingVisionDetector(),
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=2)
        
        try:
            # Should not raise exception
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Other detectors should still run
            assert fake_structure.call_count == 1
            assert fake_geometric.call_count == 2
            
            # Merger should receive empty list for vision
            assert fake_merger.last_vision_fields == []
            
        finally:
            os.unlink(pdf_path)
    
    def test_all_detectors_fail_returns_empty(self):
        """Test that pipeline returns empty list when all detectors fail"""
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=FailingPDFStructureDetector(),
            geometric_detector=FailingGeometricDetector(),
            vision_detector=FailingVisionDetector(),
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=2)
        
        try:
            # Should not raise exception
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Merger should receive empty lists
            assert fake_merger.last_pdf_structure_fields == []
            assert fake_merger.last_geometric_fields == []
            assert fake_merger.last_vision_fields == []
            
            # Result should be empty
            assert result == []
            
        finally:
            os.unlink(pdf_path)
    
    def test_no_exception_escapes(self):
        """Test that no exception escapes detect_fields_for_pdf"""
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=FailingPDFStructureDetector(),
            geometric_detector=FailingGeometricDetector(),
            vision_detector=FailingVisionDetector(),
        )
        
        pdf_path = create_blank_test_pdf()
        
        try:
            # This should NOT raise any exception
            result = pipeline.detect_fields_for_pdf(pdf_path)
            assert isinstance(result, list)
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Integration Tests with Real PDF
# ============================================================================

class TestIntegrationWithRealPDF:
    """Integration tests using real PDF files"""
    
    def test_with_real_structure_detector(self):
        """Test pipeline with real PDFStructureDetector"""
        pdf_path = create_test_pdf_with_widget()
        
        try:
            pipeline = HybridDetectionPipeline(
                pdf_structure_detector=PDFStructureDetector(),
                geometric_detector=FakeGeometricDetector(fields_per_page={}),
                vision_detector=None,
                ensemble_merger=EnsembleMerger(),
            )
            
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Should find at least the widget we created
            assert len(result) >= 1
            
            # Check field properties
            field = result[0]
            assert field.page_index == 0
            assert 0.0 <= field.bbox.x <= 1.0
            assert 0.0 <= field.bbox.y <= 1.0
            assert 0.0 <= field.bbox.width <= 1.0
            assert 0.0 <= field.bbox.height <= 1.0
            
        finally:
            os.unlink(pdf_path)
    
    def test_with_real_geometric_detector(self):
        """Test pipeline with real GeometricDetector"""
        pdf_path = create_blank_test_pdf()
        
        try:
            pipeline = HybridDetectionPipeline(
                pdf_structure_detector=FakePDFStructureDetector(fields=[]),
                geometric_detector=GeometricDetector(),
                vision_detector=None,
                ensemble_merger=EnsembleMerger(),
            )
            
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Blank PDF should have no geometric fields
            assert isinstance(result, list)
            
        finally:
            os.unlink(pdf_path)
    
    def test_full_pipeline_with_real_detectors(self):
        """Test full pipeline with real detectors (no vision)"""
        pdf_path = create_test_pdf_with_widget()
        
        try:
            pipeline = HybridDetectionPipeline(
                vision_detector=None,  # Skip vision
                debug=False,
            )
            
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Should find fields
            assert isinstance(result, list)
            
            # All fields should have valid bboxes
            for field in result:
                assert isinstance(field, FieldDetection)
                assert 0.0 <= field.bbox.x <= 1.0
                assert 0.0 <= field.bbox.y <= 1.0
                assert 0.0 <= field.bbox.width <= 1.0
                assert 0.0 <= field.bbox.height <= 1.0
                
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Property-Based Tests
# ============================================================================

class TestPropertyBased:
    """Property-based tests using Hypothesis"""
    
    @given(
        num_structure_fields=st.integers(min_value=0, max_value=5),
        num_geometric_fields=st.integers(min_value=0, max_value=5),
        num_vision_fields=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=30, deadline=None)
    def test_property_pipeline_never_crashes(
        self,
        num_structure_fields: int,
        num_geometric_fields: int,
        num_vision_fields: int,
    ):
        """
        Property: Pipeline should never crash regardless of detector outputs.
        
        **Feature: hybrid-detection-pipeline, Property 1: No crashes**
        **Validates: Requirements 5.1**
        """
        # Create fake detectors with random field counts
        structure_fields = [
            create_field_detection(
                page_index=0,
                x=0.1 + i * 0.1,
                y=0.1,
                label=f"Structure {i}",
                source=DetectionSource.STRUCTURE,
            )
            for i in range(num_structure_fields)
            if 0.1 + i * 0.1 + 0.3 <= 1.0  # Ensure valid bbox
        ]
        
        geometric_fields = [
            create_field_detection(
                page_index=0,
                x=0.1 + i * 0.1,
                y=0.3,
                label=f"Geometric {i}",
                source=DetectionSource.GEOMETRIC,
            )
            for i in range(num_geometric_fields)
            if 0.1 + i * 0.1 + 0.3 <= 1.0
        ]
        
        vision_fields = [
            create_field_detection(
                page_index=0,
                x=0.1 + i * 0.1,
                y=0.5,
                label=f"Vision {i}",
                source=DetectionSource.VISION,
            )
            for i in range(num_vision_fields)
            if 0.1 + i * 0.1 + 0.3 <= 1.0
        ]
        
        fake_structure = FakePDFStructureDetector(fields=structure_fields)
        fake_geometric = FakeGeometricDetector(fields_per_page={0: geometric_fields})
        fake_vision = FakeVisionDetector(fields=vision_fields)
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=fake_geometric,
            vision_detector=fake_vision,
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=1)
        
        try:
            # Should never crash
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            assert isinstance(result, list)
            
        finally:
            os.unlink(pdf_path)
    
    @given(
        num_fields=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20, deadline=None)
    def test_property_fields_passed_through_correctly(self, num_fields: int):
        """
        Property: Fields from detectors should be passed to merger correctly.
        
        **Feature: hybrid-detection-pipeline, Property 2: Field passthrough**
        **Validates: Requirements 5.2**
        """
        # Create fields that fit within valid bbox range
        fields = [
            create_field_detection(
                page_index=0,
                x=0.05 + (i % 5) * 0.15,
                y=0.05 + (i // 5) * 0.15,
                width=0.1,
                height=0.05,
                label=f"Field {i}",
                source=DetectionSource.STRUCTURE,
            )
            for i in range(num_fields)
        ]
        
        fake_structure = FakePDFStructureDetector(fields=fields)
        fake_geometric = FakeGeometricDetector(fields_per_page={})
        fake_merger = FakeEnsembleMerger()
        
        # No vision detector to keep test simple
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=fake_geometric,
            vision_detector=None,  # Explicitly None
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=1)
        
        try:
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Merger should receive exactly the fields we provided
            assert fake_merger.last_pdf_structure_fields == fields
            
            # Result length should match what merger returns
            assert len(result) == len(fields)
            
        finally:
            os.unlink(pdf_path)
    
    @given(
        page_index=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=20, deadline=None)
    def test_property_page_index_preserved(self, page_index: int):
        """
        Property: Page indices should be preserved through the pipeline.
        
        **Feature: hybrid-detection-pipeline, Property 3: Page index preservation**
        **Validates: Requirements 5.3**
        """
        fields = [
            create_field_detection(
                page_index=page_index,
                x=0.1,
                y=0.1,
                label=f"Field on page {page_index}",
                source=DetectionSource.STRUCTURE,
            ),
        ]
        
        fake_structure = FakePDFStructureDetector(fields=fields)
        fake_merger = FakeEnsembleMerger()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=fake_structure,
            geometric_detector=FakeGeometricDetector(fields_per_page={}),
            vision_detector=None,
            ensemble_merger=fake_merger,
        )
        
        pdf_path = create_blank_test_pdf(num_pages=max(page_index + 1, 1))
        
        try:
            result = pipeline.detect_fields_for_pdf(pdf_path)
            
            # Page index should be preserved
            assert len(result) >= 1
            assert result[0].page_index == page_index
            
        finally:
            os.unlink(pdf_path)


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases"""
    
    def test_none_vision_detector(self):
        """Test pipeline works with None vision detector"""
        pipeline = HybridDetectionPipeline(
            vision_detector=None,
        )
        
        pdf_path = create_blank_test_pdf()
        
        try:
            result = pipeline.detect_fields_for_pdf(pdf_path)
            assert isinstance(result, list)
            
        finally:
            os.unlink(pdf_path)
    
    def test_empty_pdf(self):
        """Test pipeline handles empty PDF"""
        pipeline = HybridDetectionPipeline()
        
        pdf_path = create_blank_test_pdf(num_pages=1)
        
        try:
            result = pipeline.detect_fields_for_pdf(pdf_path)
            assert isinstance(result, list)
            
        finally:
            os.unlink(pdf_path)
    
    def test_document_id_passed_to_vision(self):
        """Test that document_id is passed to vision detector"""
        fake_vision = FakeVisionDetector()
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=FakePDFStructureDetector(fields=[]),
            geometric_detector=FakeGeometricDetector(fields_per_page={}),
            vision_detector=fake_vision,
            ensemble_merger=FakeEnsembleMerger(),
        )
        
        pdf_path = create_blank_test_pdf()
        
        try:
            result = pipeline.detect_fields_for_pdf(
                pdf_path,
                document_id="test-doc-123",
            )
            
            assert fake_vision.last_document_id == "test-doc-123"
            
        finally:
            os.unlink(pdf_path)
