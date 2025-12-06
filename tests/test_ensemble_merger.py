"""
Unit Tests for EnsembleMerger

Tests for:
- PDF_STRUCTURE overrides all overlapping detections
- Geometric signature lines override vision guesses
- IoU-based deduplication
- Label inheritance rules
- Merging across pages
- Property-based tests for no duplicates after merge
- Property-based tests for BBox normalization
- Non-overlapping fields from all detectors remain

All tests use synthetic FieldDetection objects.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List

from workers.ensemble_merger import EnsembleMerger, MergeCandidate
from workers.detection_models import BBox, FieldDetection, FieldType, DetectionSource


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def merger():
    """Create an EnsembleMerger instance"""
    return EnsembleMerger(iou_threshold=0.30, debug=False)

@pytest.fixture
def debug_merger():
    """Create an EnsembleMerger with debug enabled"""
    return EnsembleMerger(iou_threshold=0.30, debug=True)


# ============================================================================
# Helper Functions
# ============================================================================

def create_detection(
    x: float = 0.1,
    y: float = 0.1,
    width: float = 0.3,
    height: float = 0.05,
    page_index: int = 0,
    field_type: FieldType = FieldType.TEXT,
    label: str = "Test Field",
    confidence: float = 0.9,
    source: DetectionSource = DetectionSource.STRUCTURE
) -> FieldDetection:
    """Helper to create a FieldDetection for testing"""
    return FieldDetection(
        page_index=page_index,
        bbox=BBox(x=x, y=y, width=width, height=height),
        field_type=field_type,
        label=label,
        confidence=confidence,
        source=source
    )


# ============================================================================
# Unit Tests - Initialization
# ============================================================================

class TestEnsembleMergerInit:
    """Tests for EnsembleMerger initialization"""
    
    def test_default_initialization(self):
        """Test creating an EnsembleMerger with default parameters"""
        merger = EnsembleMerger()
        
        assert merger.iou_threshold == 0.30
        assert merger.debug == False
    
    def test_custom_iou_threshold(self):
        """Test creating an EnsembleMerger with custom IoU threshold"""
        merger = EnsembleMerger(iou_threshold=0.5)
        
        assert merger.iou_threshold == 0.5
    
    def test_debug_mode(self):
        """Test creating an EnsembleMerger with debug enabled"""
        merger = EnsembleMerger(debug=True)
        
        assert merger.debug == True


# ============================================================================
# Unit Tests - PDF Structure Priority
# ============================================================================

class TestPDFStructurePriority:
    """Tests that PDF_STRUCTURE overrides all overlapping detections"""
    
    def test_structure_overrides_geometric(self, merger):
        """Test that PDF structure detection overrides geometric detection"""
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE,
            label="Name Field"
        )
        
        geometric_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.GEOMETRIC,
            label="Text Field 1"
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[geometric_field],
            vision_fields=[]
        )
        
        assert len(result) == 1
        assert result[0].source == DetectionSource.STRUCTURE
        assert result[0].label == "Name Field"
    
    def test_structure_overrides_vision(self, merger):
        """Test that PDF structure detection overrides vision detection"""
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE,
            label="Email Field"
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.VISION,
            label="Input Area"
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[],
            vision_fields=[vision_field]
        )
        
        assert len(result) == 1
        assert result[0].source == DetectionSource.STRUCTURE
        assert result[0].label == "Email Field"
    
    def test_structure_overrides_both(self, merger):
        """Test that PDF structure overrides both geometric and vision"""
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE,
            label="Phone Field"
        )
        
        geometric_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.GEOMETRIC,
            label="Text Field 1"
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.VISION,
            label="Text Input"
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[geometric_field],
            vision_fields=[vision_field]
        )
        
        assert len(result) == 1
        assert result[0].source == DetectionSource.STRUCTURE


# ============================================================================
# Unit Tests - Geometric Signature Override
# ============================================================================

class TestGeometricSignatureOverride:
    """Tests that geometric signature lines override vision guesses"""
    
    def test_geometric_signature_overrides_vision_text(self, merger):
        """Test that geometric signature detection overrides vision text"""
        geometric_field = create_detection(
            x=0.1, y=0.1, width=0.4, height=0.02,
            source=DetectionSource.GEOMETRIC,
            field_type=FieldType.SIGNATURE,
            label="Signature 1"
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.4, height=0.02,
            source=DetectionSource.VISION,
            field_type=FieldType.TEXT,
            label="Text Area"
        )
        
        result = merger.merge(
            pdf_structure_fields=[],
            geometric_fields=[geometric_field],
            vision_fields=[vision_field]
        )
        
        assert len(result) == 1
        assert result[0].field_type == FieldType.SIGNATURE


# ============================================================================
# Unit Tests - IoU Deduplication
# ============================================================================

class TestIoUDeduplication:
    """Tests for IoU-based deduplication"""
    
    def test_overlapping_fields_deduplicated(self, merger):
        """Test that overlapping fields are deduplicated"""
        field1 = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE
        )
        
        # Slightly offset but still overlapping
        field2 = create_detection(
            x=0.12, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.GEOMETRIC
        )
        
        result = merger.merge(
            pdf_structure_fields=[field1],
            geometric_fields=[field2],
            vision_fields=[]
        )
        
        # Should be deduplicated to 1 field
        assert len(result) == 1
    
    def test_non_overlapping_fields_kept(self, merger):
        """Test that non-overlapping fields are all kept"""
        field1 = create_detection(
            x=0.1, y=0.1, width=0.2, height=0.05,
            source=DetectionSource.STRUCTURE,
            label="Field 1"
        )
        
        field2 = create_detection(
            x=0.5, y=0.1, width=0.2, height=0.05,
            source=DetectionSource.GEOMETRIC,
            label="Field 2"
        )
        
        field3 = create_detection(
            x=0.1, y=0.5, width=0.2, height=0.05,
            source=DetectionSource.VISION,
            label="Field 3"
        )
        
        result = merger.merge(
            pdf_structure_fields=[field1],
            geometric_fields=[field2],
            vision_fields=[field3]
        )
        
        # All 3 should be kept (no overlap)
        assert len(result) == 3
    
    def test_iou_threshold_respected(self):
        """Test that IoU threshold is respected"""
        # Use a higher threshold
        merger = EnsembleMerger(iou_threshold=0.8)
        
        field1 = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE
        )
        
        # Slightly offset - IoU will be less than 0.8
        field2 = create_detection(
            x=0.15, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.GEOMETRIC
        )
        
        result = merger.merge(
            pdf_structure_fields=[field1],
            geometric_fields=[field2],
            vision_fields=[]
        )
        
        # With high threshold, both should be kept
        assert len(result) == 2


# ============================================================================
# Unit Tests - Label Inheritance
# ============================================================================

class TestLabelInheritance:
    """Tests for label inheritance rules"""
    
    def test_inherit_label_from_lower_priority(self, merger):
        """Test that meaningful label is inherited from lower priority source"""
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE,
            label="Field 1"  # Generic label
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.VISION,
            label="Customer Name"  # Meaningful label
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[],
            vision_fields=[vision_field]
        )
        
        assert len(result) == 1
        assert result[0].label == "Customer Name"
    
    def test_keep_meaningful_label_from_higher_priority(self, merger):
        """Test that meaningful label from higher priority is kept"""
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE,
            label="Email Address"  # Meaningful label
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.VISION,
            label="Text Input"  # Less meaningful
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[],
            vision_fields=[vision_field]
        )
        
        assert len(result) == 1
        assert result[0].label == "Email Address"
    
    def test_generic_label_detection(self, merger):
        """Test that generic labels are correctly identified"""
        assert merger._is_generic_label("Field 1") == True
        assert merger._is_generic_label("Text Field 2") == True
        assert merger._is_generic_label("Checkbox 3") == True
        assert merger._is_generic_label("Customer Name") == False
        assert merger._is_generic_label("Email") == False
        assert merger._is_generic_label("") == True


# ============================================================================
# Unit Tests - Multi-Page Merging
# ============================================================================

class TestMultiPageMerging:
    """Tests for merging across pages"""
    
    def test_fields_on_different_pages_not_deduplicated(self, merger):
        """Test that fields on different pages are not deduplicated"""
        field_page0 = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=0,
            source=DetectionSource.STRUCTURE
        )
        
        field_page1 = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=1,
            source=DetectionSource.GEOMETRIC
        )
        
        result = merger.merge(
            pdf_structure_fields=[field_page0],
            geometric_fields=[field_page1],
            vision_fields=[]
        )
        
        # Both should be kept (different pages)
        assert len(result) == 2
    
    def test_sorting_by_page_index(self, merger):
        """Test that results are sorted by page_index"""
        field_page2 = create_detection(page_index=2, source=DetectionSource.STRUCTURE)
        field_page0 = create_detection(page_index=0, source=DetectionSource.GEOMETRIC)
        field_page1 = create_detection(page_index=1, source=DetectionSource.VISION)
        
        result = merger.merge(
            pdf_structure_fields=[field_page2],
            geometric_fields=[field_page0],
            vision_fields=[field_page1]
        )
        
        assert result[0].page_index == 0
        assert result[1].page_index == 1
        assert result[2].page_index == 2
    
    def test_sorting_within_page_by_position(self, merger):
        """Test that fields within a page are sorted by position"""
        # Field at top of page (high y in normalized coords)
        field_top = create_detection(
            x=0.1, y=0.8, width=0.3, height=0.05,
            page_index=0,
            source=DetectionSource.STRUCTURE,
            label="Top Field"
        )
        
        # Field at bottom of page (low y in normalized coords)
        field_bottom = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=0,
            source=DetectionSource.GEOMETRIC,
            label="Bottom Field"
        )
        
        # Field in middle
        field_middle = create_detection(
            x=0.1, y=0.4, width=0.3, height=0.05,
            page_index=0,
            source=DetectionSource.VISION,
            label="Middle Field"
        )
        
        result = merger.merge(
            pdf_structure_fields=[field_top],
            geometric_fields=[field_bottom],
            vision_fields=[field_middle]
        )
        
        # Should be sorted top to bottom (high y first)
        assert result[0].label == "Top Field"
        assert result[1].label == "Middle Field"
        assert result[2].label == "Bottom Field"


# ============================================================================
# Unit Tests - Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""
    
    def test_empty_inputs(self, merger):
        """Test that empty inputs return empty list"""
        result = merger.merge(
            pdf_structure_fields=[],
            geometric_fields=[],
            vision_fields=[]
        )
        
        assert result == []
    
    def test_none_inputs(self, merger):
        """Test that None inputs are handled gracefully"""
        result = merger.merge(
            pdf_structure_fields=None,
            geometric_fields=None,
            vision_fields=None
        )
        
        assert result == []
    
    def test_single_source_only(self, merger):
        """Test merging with only one source"""
        fields = [
            create_detection(x=0.1, y=0.1, source=DetectionSource.STRUCTURE),
            create_detection(x=0.5, y=0.1, source=DetectionSource.STRUCTURE),
        ]
        
        result = merger.merge(
            pdf_structure_fields=fields,
            geometric_fields=[],
            vision_fields=[]
        )
        
        assert len(result) == 2
    
    def test_all_detections_are_field_detection_type(self, merger):
        """Test that all results are FieldDetection instances"""
        structure_field = create_detection(source=DetectionSource.STRUCTURE)
        geometric_field = create_detection(x=0.4, source=DetectionSource.GEOMETRIC)
        vision_field = create_detection(x=0.1, y=0.5, source=DetectionSource.VISION)
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[geometric_field],
            vision_fields=[vision_field]
        )
        
        for detection in result:
            assert isinstance(detection, FieldDetection)
            assert isinstance(detection.bbox, BBox)


# ============================================================================
# Unit Tests - Type Conflict Resolution
# ============================================================================

class TestTypeConflictResolution:
    """Tests for field type conflict resolution"""
    
    def test_checkbox_overrides_text_for_small_fields(self, merger):
        """Test that checkbox type is preferred for small fields"""
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.03, height=0.03,
            source=DetectionSource.STRUCTURE,
            field_type=FieldType.TEXT
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.03, height=0.03,
            source=DetectionSource.VISION,
            field_type=FieldType.CHECKBOX
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[],
            vision_fields=[vision_field]
        )
        
        assert len(result) == 1
        assert result[0].field_type == FieldType.CHECKBOX
    
    def test_structure_type_authoritative(self, merger):
        """Test that PDF structure field type is authoritative"""
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE,
            field_type=FieldType.TEXT
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.VISION,
            field_type=FieldType.DATE
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[],
            vision_fields=[vision_field]
        )
        
        assert len(result) == 1
        # Structure type should be kept (it's authoritative)
        assert result[0].field_type == FieldType.TEXT


# ============================================================================
# Property-Based Tests
# ============================================================================

class TestPropertyBasedNoDuplicates:
    """Property-based tests for no duplicates after merge"""
    
    @given(
        num_structure=st.integers(min_value=0, max_value=5),
        num_geometric=st.integers(min_value=0, max_value=5),
        num_vision=st.integers(min_value=0, max_value=5)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_no_exact_duplicates(
        self,
        num_structure: int,
        num_geometric: int,
        num_vision: int
    ):
        """
        Property: After merging, there should be no exact duplicate bboxes
        on the same page.
        
        **Feature: hybrid-detection-pipeline, Property 1: No duplicates**
        **Validates: Requirements 4.1**
        """
        merger = EnsembleMerger(iou_threshold=0.30)
        
        # Create non-overlapping fields for each source
        structure_fields = [
            create_detection(
                x=0.1 + i * 0.15, y=0.1,
                width=0.1, height=0.05,
                source=DetectionSource.STRUCTURE,
                label=f"Structure {i}"
            )
            for i in range(num_structure)
        ]
        
        geometric_fields = [
            create_detection(
                x=0.1 + i * 0.15, y=0.3,
                width=0.1, height=0.05,
                source=DetectionSource.GEOMETRIC,
                label=f"Geometric {i}"
            )
            for i in range(num_geometric)
        ]
        
        vision_fields = [
            create_detection(
                x=0.1 + i * 0.15, y=0.5,
                width=0.1, height=0.05,
                source=DetectionSource.VISION,
                label=f"Vision {i}"
            )
            for i in range(num_vision)
        ]
        
        result = merger.merge(
            pdf_structure_fields=structure_fields,
            geometric_fields=geometric_fields,
            vision_fields=vision_fields
        )
        
        # Check for exact duplicates
        seen_bboxes = set()
        for detection in result:
            bbox_key = (
                detection.page_index,
                round(detection.bbox.x, 4),
                round(detection.bbox.y, 4),
                round(detection.bbox.width, 4),
                round(detection.bbox.height, 4)
            )
            assert bbox_key not in seen_bboxes, f"Duplicate bbox found: {bbox_key}"
            seen_bboxes.add(bbox_key)


class TestPropertyBasedBBoxNormalization:
    """Property-based tests for BBox normalization"""
    
    @given(
        x=st.floats(min_value=0.0, max_value=0.7),
        y=st.floats(min_value=0.0, max_value=0.7),
        width=st.floats(min_value=0.05, max_value=0.25),
        height=st.floats(min_value=0.02, max_value=0.25)
    )
    @settings(max_examples=100, deadline=None)
    def test_property_all_bboxes_normalized(
        self,
        x: float,
        y: float,
        width: float,
        height: float
    ):
        """
        Property: All BBoxes in merged results should have coordinates
        in [0, 1] range.
        
        **Feature: hybrid-detection-pipeline, Property 2: BBox normalization**
        **Validates: Requirements 4.2**
        """
        assume(x + width <= 1.0)
        assume(y + height <= 1.0)
        
        merger = EnsembleMerger()
        
        field = create_detection(
            x=x, y=y, width=width, height=height,
            source=DetectionSource.STRUCTURE
        )
        
        result = merger.merge(
            pdf_structure_fields=[field],
            geometric_fields=[],
            vision_fields=[]
        )
        
        for detection in result:
            assert 0.0 <= detection.bbox.x <= 1.0
            assert 0.0 <= detection.bbox.y <= 1.0
            assert 0.0 <= detection.bbox.width <= 1.0
            assert 0.0 <= detection.bbox.height <= 1.0
            assert detection.bbox.x + detection.bbox.width <= 1.0
            assert detection.bbox.y + detection.bbox.height <= 1.0


class TestPropertyBasedOverlapDeduplication:
    """Property-based tests for overlap deduplication"""
    
    @given(
        offset=st.floats(min_value=0.0, max_value=0.05)
    )
    @settings(max_examples=50, deadline=None)
    def test_property_overlapping_fields_deduplicated(self, offset: float):
        """
        Property: Fields with high IoU should be deduplicated to a single field.
        
        **Feature: hybrid-detection-pipeline, Property 3: Deduplication**
        **Validates: Requirements 4.3**
        """
        merger = EnsembleMerger(iou_threshold=0.30)
        
        # Create two highly overlapping fields
        field1 = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.STRUCTURE
        )
        
        field2 = create_detection(
            x=0.1 + offset, y=0.1, width=0.3, height=0.05,
            source=DetectionSource.GEOMETRIC
        )
        
        result = merger.merge(
            pdf_structure_fields=[field1],
            geometric_fields=[field2],
            vision_fields=[]
        )
        
        # Calculate expected IoU
        iou = field1.bbox.iou(field2.bbox)
        
        if iou > 0.30:
            # Should be deduplicated
            assert len(result) == 1
        else:
            # Should both be kept
            assert len(result) == 2


class TestPropertyBasedPriorityOrder:
    """Property-based tests for priority order"""
    
    @given(
        page_index=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=30, deadline=None)
    def test_property_structure_always_wins(self, page_index: int):
        """
        Property: When fields overlap, STRUCTURE source should always win.
        
        **Feature: hybrid-detection-pipeline, Property 4: Priority order**
        **Validates: Requirements 4.4**
        """
        merger = EnsembleMerger(iou_threshold=0.30)
        
        # Create identical fields from different sources
        structure_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=page_index,
            source=DetectionSource.STRUCTURE,
            label="Structure Label"
        )
        
        geometric_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=page_index,
            source=DetectionSource.GEOMETRIC,
            label="Geometric Label"
        )
        
        vision_field = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=page_index,
            source=DetectionSource.VISION,
            label="Vision Label"
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_field],
            geometric_fields=[geometric_field],
            vision_fields=[vision_field]
        )
        
        # Should be deduplicated to 1 field
        assert len(result) == 1
        # Structure should win
        assert result[0].source == DetectionSource.STRUCTURE


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for full merge pipeline"""
    
    def test_complex_merge_scenario(self, merger):
        """Test a complex merge scenario with multiple overlaps"""
        # Page 0: Structure and Vision overlap
        structure_p0 = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=0,
            source=DetectionSource.STRUCTURE,
            label="Name"
        )
        vision_p0 = create_detection(
            x=0.1, y=0.1, width=0.3, height=0.05,
            page_index=0,
            source=DetectionSource.VISION,
            label="Text Input"
        )
        
        # Page 0: Non-overlapping geometric
        geometric_p0 = create_detection(
            x=0.5, y=0.1, width=0.3, height=0.05,
            page_index=0,
            source=DetectionSource.GEOMETRIC,
            label="Signature 1",
            field_type=FieldType.SIGNATURE
        )
        
        # Page 1: Only vision
        vision_p1 = create_detection(
            x=0.1, y=0.5, width=0.3, height=0.05,
            page_index=1,
            source=DetectionSource.VISION,
            label="Address"
        )
        
        result = merger.merge(
            pdf_structure_fields=[structure_p0],
            geometric_fields=[geometric_p0],
            vision_fields=[vision_p0, vision_p1]
        )
        
        # Should have 3 fields total
        assert len(result) == 3
        
        # Check page 0 fields
        page0_fields = [f for f in result if f.page_index == 0]
        assert len(page0_fields) == 2
        
        # Check page 1 fields
        page1_fields = [f for f in result if f.page_index == 1]
        assert len(page1_fields) == 1
        assert page1_fields[0].label == "Address"
    
    def test_deterministic_results(self, merger):
        """Test that merge results are deterministic"""
        structure_fields = [
            create_detection(x=0.1, y=0.1, source=DetectionSource.STRUCTURE),
            create_detection(x=0.5, y=0.1, source=DetectionSource.STRUCTURE),
        ]
        geometric_fields = [
            create_detection(x=0.1, y=0.5, source=DetectionSource.GEOMETRIC),
        ]
        vision_fields = [
            create_detection(x=0.5, y=0.5, source=DetectionSource.VISION),
        ]
        
        # Run merge multiple times
        results = []
        for _ in range(3):
            result = merger.merge(
                pdf_structure_fields=structure_fields,
                geometric_fields=geometric_fields,
                vision_fields=vision_fields
            )
            results.append(result)
        
        # All results should be identical
        for i in range(1, len(results)):
            assert len(results[i]) == len(results[0])
            for j in range(len(results[0])):
                assert results[i][j].bbox.x == results[0][j].bbox.x
                assert results[i][j].bbox.y == results[0][j].bbox.y
                assert results[i][j].source == results[0][j].source
