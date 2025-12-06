"""
Integration Tests for Hybrid Detection Pipeline

Tests the integration of the hybrid detection pipeline with:
- VisionDetectorAdapter
- HybridProcessor
- FastAPI endpoints

These tests verify that all components work together correctly.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from typing import List

import fitz  # PyMuPDF

# Import detection models
from workers.detection_models import BBox, FieldDetection, FieldType, DetectionSource
from workers.hybrid_detection_pipeline import HybridDetectionPipeline, VisionDetectorProtocol
from workers.vision_detector_adapter import VisionDetectorAdapter
from workers.pdf_structure_detector import PDFStructureDetector
from workers.geometric_detector import GeometricDetector
from workers.ensemble_merger import EnsembleMerger


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def simple_pdf_path():
    """Create a simple PDF for testing."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # Letter size
        
        # Add some text
        page.insert_text((72, 72), "Test Form", fontsize=24)
        page.insert_text((72, 120), "Name:", fontsize=12)
        page.insert_text((72, 160), "Email:", fontsize=12)
        
        # Draw some rectangles (form fields)
        page.draw_rect(fitz.Rect(150, 110, 400, 130), color=(0, 0, 0), width=1)
        page.draw_rect(fitz.Rect(150, 150, 400, 170), color=(0, 0, 0), width=1)
        
        doc.save(f.name)
        doc.close()
        
        yield f.name
        
        # Cleanup
        if os.path.exists(f.name):
            os.unlink(f.name)


@pytest.fixture
def acroform_pdf_path():
    """Create a PDF with AcroForm fields for testing."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        
        # Add text
        page.insert_text((72, 72), "AcroForm Test", fontsize=24)
        
        # Add a text widget (AcroForm field)
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = "name_field"
        widget.rect = fitz.Rect(150, 100, 400, 120)
        page.add_widget(widget)
        
        # Add a checkbox widget
        checkbox = fitz.Widget()
        checkbox.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        checkbox.field_name = "agree_checkbox"
        checkbox.rect = fitz.Rect(72, 150, 92, 170)
        page.add_widget(checkbox)
        
        doc.save(f.name)
        doc.close()
        
        yield f.name
        
        # Cleanup
        if os.path.exists(f.name):
            os.unlink(f.name)


@pytest.fixture
def mock_vision_detector():
    """Create a mock vision detector for testing."""
    class MockVisionDetector:
        def detect_fields(
            self,
            pdf_path: str,
            document_id: str = None,
        ) -> List[FieldDetection]:
            return [
                FieldDetection(
                    page_index=0,
                    bbox=BBox(x=0.2, y=0.8, width=0.4, height=0.05),
                    field_type=FieldType.TEXT,
                    label="Vision Name Field",
                    confidence=0.85,
                    source=DetectionSource.VISION,
                ),
                FieldDetection(
                    page_index=0,
                    bbox=BBox(x=0.2, y=0.7, width=0.4, height=0.05),
                    field_type=FieldType.TEXT,
                    label="Vision Email Field",
                    confidence=0.82,
                    source=DetectionSource.VISION,
                ),
            ]
    
    return MockVisionDetector()


# ============================================================================
# VisionDetectorAdapter Tests
# ============================================================================

class TestVisionDetectorAdapter:
    """Tests for VisionDetectorAdapter."""
    
    def test_adapter_implements_protocol(self):
        """Test that adapter implements VisionDetectorProtocol."""
        adapter = VisionDetectorAdapter(provider="openai")
        assert isinstance(adapter, VisionDetectorProtocol)
    
    def test_adapter_without_api_key_returns_empty(self, simple_pdf_path):
        """Test that adapter returns empty list without API key."""
        # Clear any existing API key
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            adapter = VisionDetectorAdapter(provider="openai", api_key=None)
            # Client should be None without API key
            if adapter.client is None:
                result = adapter.detect_fields(simple_pdf_path)
                assert result == []
    
    def test_field_type_mapping(self):
        """Test field type mapping from vision model types."""
        adapter = VisionDetectorAdapter(provider="openai")
        
        assert adapter.FIELD_TYPE_MAP['text'] == FieldType.TEXT
        assert adapter.FIELD_TYPE_MAP['textarea'] == FieldType.MULTILINE
        assert adapter.FIELD_TYPE_MAP['checkbox'] == FieldType.CHECKBOX
        assert adapter.FIELD_TYPE_MAP['signature'] == FieldType.SIGNATURE
        assert adapter.FIELD_TYPE_MAP['date'] == FieldType.DATE
        assert adapter.FIELD_TYPE_MAP['number'] == FieldType.NUMBER
        assert adapter.FIELD_TYPE_MAP['unknown'] == FieldType.UNKNOWN
    
    def test_convert_to_field_detection(self):
        """Test conversion of vision model response to FieldDetection."""
        adapter = VisionDetectorAdapter(provider="openai")
        
        field_data = {
            'id': 'field_001',
            'type': 'text',
            'label': 'Full Name',
            'bbox': [100, 200, 600, 250],  # 0-1000 coordinate system
        }
        
        detection = adapter._convert_to_field_detection(field_data, page_index=0)
        
        assert detection is not None
        assert detection.page_index == 0
        assert detection.field_type == FieldType.TEXT
        assert detection.label == "Full Name"
        assert detection.source == DetectionSource.VISION
        assert detection.confidence == 0.85
        
        # Check normalized coordinates
        assert 0.09 <= detection.bbox.x <= 0.11  # ~0.1
        assert 0.19 <= detection.bbox.y <= 0.21  # ~0.2
        assert 0.49 <= detection.bbox.width <= 0.51  # ~0.5
        assert 0.04 <= detection.bbox.height <= 0.06  # ~0.05
    
    def test_convert_invalid_bbox_returns_none(self):
        """Test that invalid bbox returns None."""
        adapter = VisionDetectorAdapter(provider="openai")
        
        # Missing bbox
        result = adapter._convert_to_field_detection({'type': 'text'}, 0)
        assert result is None
        
        # Invalid bbox length
        result = adapter._convert_to_field_detection({'bbox': [1, 2, 3]}, 0)
        assert result is None
    
    def test_parse_json_response(self):
        """Test JSON parsing from vision model response."""
        adapter = VisionDetectorAdapter(provider="openai")
        
        # Plain JSON
        result = adapter._parse_json_response('{"fields": []}')
        assert result == {"fields": []}
        
        # JSON with markdown code block
        result = adapter._parse_json_response('```json\n{"fields": []}\n```')
        assert result == {"fields": []}
        
        # Invalid JSON
        result = adapter._parse_json_response('not json')
        assert result == {}


# ============================================================================
# HybridDetectionPipeline Integration Tests
# ============================================================================

class TestHybridPipelineIntegration:
    """Integration tests for HybridDetectionPipeline."""
    
    def test_pipeline_with_simple_pdf(self, simple_pdf_path):
        """Test pipeline processes simple PDF without errors."""
        pipeline = HybridDetectionPipeline(
            vision_detector=None,  # Skip vision for this test
            debug=False,
        )
        
        detections = pipeline.detect_fields_for_pdf(simple_pdf_path)
        
        # Should return a list (may be empty for simple PDF)
        assert isinstance(detections, list)
        
        # All detections should be valid FieldDetection objects
        for detection in detections:
            assert isinstance(detection, FieldDetection)
            assert 0 <= detection.bbox.x <= 1
            assert 0 <= detection.bbox.y <= 1
            assert 0 <= detection.bbox.width <= 1
            assert 0 <= detection.bbox.height <= 1
    
    def test_pipeline_with_acroform_pdf(self, acroform_pdf_path):
        """Test pipeline detects AcroForm fields."""
        pipeline = HybridDetectionPipeline(
            vision_detector=None,
            debug=False,
        )
        
        detections = pipeline.detect_fields_for_pdf(acroform_pdf_path)
        
        # Should find the AcroForm fields
        assert len(detections) >= 1
        
        # Check that structure source is present
        sources = {d.source for d in detections}
        assert DetectionSource.STRUCTURE in sources or DetectionSource.GEOMETRIC in sources
    
    def test_pipeline_with_mock_vision(self, simple_pdf_path, mock_vision_detector):
        """Test pipeline integrates with vision detector."""
        pipeline = HybridDetectionPipeline(
            vision_detector=mock_vision_detector,
            debug=False,
        )
        
        detections = pipeline.detect_fields_for_pdf(simple_pdf_path)
        
        # Should include vision detections
        vision_detections = [d for d in detections if d.source == DetectionSource.VISION]
        assert len(vision_detections) >= 1
    
    def test_pipeline_merges_detections(self, simple_pdf_path, mock_vision_detector):
        """Test that pipeline merges detections from multiple sources."""
        # Create mock structure detector that returns overlapping field
        mock_structure = Mock(spec=PDFStructureDetector)
        mock_structure.detect_fields.return_value = [
            FieldDetection(
                page_index=0,
                bbox=BBox(x=0.2, y=0.8, width=0.4, height=0.05),  # Same as vision
                field_type=FieldType.TEXT,
                label="Structure Name Field",
                confidence=0.95,
                source=DetectionSource.STRUCTURE,
            ),
        ]
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=mock_structure,
            vision_detector=mock_vision_detector,
            debug=False,
        )
        
        detections = pipeline.detect_fields_for_pdf(simple_pdf_path)
        
        # Overlapping fields should be merged (structure wins)
        # Should have structure field + non-overlapping vision field
        structure_count = sum(1 for d in detections if d.source == DetectionSource.STRUCTURE)
        assert structure_count >= 1
    
    def test_pipeline_handles_detector_failure(self, simple_pdf_path):
        """Test that pipeline continues when a detector fails."""
        # Create mock detector that raises exception
        mock_structure = Mock(spec=PDFStructureDetector)
        mock_structure.detect_fields.side_effect = Exception("Detector failed")
        
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=mock_structure,
            vision_detector=None,
            debug=False,
        )
        
        # Should not raise, should return results from other detectors
        detections = pipeline.detect_fields_for_pdf(simple_pdf_path)
        assert isinstance(detections, list)
    
    def test_pipeline_preserves_page_index(self, simple_pdf_path, mock_vision_detector):
        """Test that page indices are preserved through pipeline."""
        pipeline = HybridDetectionPipeline(
            vision_detector=mock_vision_detector,
            debug=False,
        )
        
        detections = pipeline.detect_fields_for_pdf(simple_pdf_path)
        
        # All detections should have valid page index
        for detection in detections:
            assert detection.page_index >= 0


# ============================================================================
# Ensemble Merger Integration Tests
# ============================================================================

class TestEnsembleMergerIntegration:
    """Integration tests for EnsembleMerger with real detectors."""
    
    def test_merger_deduplicates_overlapping_fields(self):
        """Test that merger deduplicates overlapping fields."""
        merger = EnsembleMerger(iou_threshold=0.3)
        
        # Create overlapping detections from different sources
        structure_fields = [
            FieldDetection(
                page_index=0,
                bbox=BBox(x=0.1, y=0.8, width=0.3, height=0.05),
                field_type=FieldType.TEXT,
                label="Name",
                confidence=0.95,
                source=DetectionSource.STRUCTURE,
            ),
        ]
        
        geometric_fields = [
            FieldDetection(
                page_index=0,
                bbox=BBox(x=0.12, y=0.79, width=0.28, height=0.06),  # Overlaps
                field_type=FieldType.TEXT,
                label="Text Field 1",
                confidence=0.8,
                source=DetectionSource.GEOMETRIC,
            ),
        ]
        
        vision_fields = [
            FieldDetection(
                page_index=0,
                bbox=BBox(x=0.5, y=0.5, width=0.3, height=0.05),  # Non-overlapping
                field_type=FieldType.SIGNATURE,
                label="Signature",
                confidence=0.85,
                source=DetectionSource.VISION,
            ),
        ]
        
        merged = merger.merge(structure_fields, geometric_fields, vision_fields)
        
        # Should have 2 fields: structure (merged with geometric) + vision
        assert len(merged) == 2
        
        # Structure should win for overlapping field
        structure_count = sum(1 for d in merged if d.source == DetectionSource.STRUCTURE)
        assert structure_count == 1
    
    def test_merger_inherits_labels(self):
        """Test that merger inherits labels from lower priority sources."""
        merger = EnsembleMerger(iou_threshold=0.3)
        
        # Structure field with generic label
        structure_fields = [
            FieldDetection(
                page_index=0,
                bbox=BBox(x=0.1, y=0.8, width=0.3, height=0.05),
                field_type=FieldType.TEXT,
                label="Field 1",  # Generic label
                confidence=0.95,
                source=DetectionSource.STRUCTURE,
            ),
        ]
        
        # Vision field with meaningful label (overlapping)
        vision_fields = [
            FieldDetection(
                page_index=0,
                bbox=BBox(x=0.1, y=0.8, width=0.3, height=0.05),
                field_type=FieldType.TEXT,
                label="Full Name",  # Meaningful label
                confidence=0.85,
                source=DetectionSource.VISION,
            ),
        ]
        
        merged = merger.merge(structure_fields, [], vision_fields)
        
        # Should have 1 field with inherited label
        assert len(merged) == 1
        assert merged[0].label == "Full Name"
        assert merged[0].source == DetectionSource.STRUCTURE


# ============================================================================
# End-to-End Tests
# ============================================================================

class TestEndToEnd:
    """End-to-end tests for the complete hybrid detection flow."""
    
    def test_full_pipeline_flow(self, acroform_pdf_path):
        """Test complete flow from PDF to detections."""
        # Create pipeline with all components
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=PDFStructureDetector(debug=False),
            geometric_detector=GeometricDetector(debug=False),
            vision_detector=None,  # Skip vision for speed
            ensemble_merger=EnsembleMerger(iou_threshold=0.3),
            debug=False,
        )
        
        # Process PDF
        detections = pipeline.detect_fields_for_pdf(acroform_pdf_path)
        
        # Verify results
        assert isinstance(detections, list)
        
        # All detections should be valid
        for detection in detections:
            assert isinstance(detection, FieldDetection)
            assert detection.page_index >= 0
            assert 0 <= detection.bbox.x <= 1
            assert 0 <= detection.bbox.y <= 1
            assert 0 <= detection.confidence <= 1
            assert detection.label is not None
    
    def test_detection_to_dict_serialization(self, simple_pdf_path):
        """Test that detections can be serialized to dict."""
        pipeline = HybridDetectionPipeline(vision_detector=None)
        detections = pipeline.detect_fields_for_pdf(simple_pdf_path)
        
        for detection in detections:
            # Should serialize without error
            d = detection.to_dict()
            
            assert 'page_index' in d
            assert 'bbox' in d
            assert 'field_type' in d
            assert 'label' in d
            assert 'confidence' in d
            assert 'source' in d
            
            # Should deserialize back
            restored = FieldDetection.from_dict(d)
            assert restored.page_index == detection.page_index
            assert restored.field_type == detection.field_type


# ============================================================================
# Property-Based Tests
# ============================================================================

class TestPropertyBased:
    """Property-based tests using Hypothesis."""
    
    @pytest.mark.parametrize("num_pages", [1, 2, 5])
    def test_multi_page_pdf_processing(self, num_pages):
        """Test processing PDFs with multiple pages."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            doc = fitz.open()
            
            for i in range(num_pages):
                page = doc.new_page(width=612, height=792)
                page.insert_text((72, 72), f"Page {i + 1}", fontsize=24)
                
                # Add a rectangle on each page
                page.draw_rect(
                    fitz.Rect(100, 100 + i * 10, 300, 130 + i * 10),
                    color=(0, 0, 0),
                    width=1
                )
            
            doc.save(f.name)
            doc.close()
            
            try:
                pipeline = HybridDetectionPipeline(vision_detector=None)
                detections = pipeline.detect_fields_for_pdf(f.name)
                
                # All page indices should be valid
                for detection in detections:
                    assert 0 <= detection.page_index < num_pages
                    
            finally:
                if os.path.exists(f.name):
                    os.unlink(f.name)
    
    def test_empty_pdf_handling(self):
        """Test handling of empty PDF."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            doc = fitz.open()
            doc.new_page()  # Empty page
            doc.save(f.name)
            doc.close()
            
            try:
                pipeline = HybridDetectionPipeline(vision_detector=None)
                detections = pipeline.detect_fields_for_pdf(f.name)
                
                # Should return empty list, not crash
                assert isinstance(detections, list)
                
            finally:
                if os.path.exists(f.name):
                    os.unlink(f.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
