"""
Ensemble Merger for Hybrid Detection Pipeline

This module implements Phase 4 of the Hybrid Detection Pipeline: merging detections
from multiple sources into a unified, deduplicated list of form fields.

How it works:
1. Receives detections from multiple sources:
   - PDFStructureDetector (highest priority)
   - GeometricDetector (medium priority)
   - VisionAI detector (lowest priority)
2. Deduplicates overlapping detections using IoU threshold
3. Resolves conflicts using priority and semantic rules
4. Returns a unified list sorted by page and position

Priority Order (highest to lowest):
1. PDF_STRUCTURE - Native PDF form fields (most accurate)
2. GEOMETRIC - OpenCV line/box detection
3. VISION - AI semantic understanding

Deduplication Rules:
- IoU threshold of 0.30 for considering fields as duplicates
- Higher priority source wins when fields overlap
- Label inheritance: prefer labeled fields over unlabeled
- Type conflicts: checkbox > text, signature geometry > AI guess

Output:
- Deduplicated List[FieldDetection]
- Sorted by page_index ascending
- Within each page, sorted by bbox.y descending (top to bottom visually)
"""

import logging
from typing import List, Optional, Tuple, Set
from dataclasses import dataclass, replace

from .detection_models import BBox, FieldDetection, FieldType, DetectionSource


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class MergeCandidate:
    """
    Internal representation of a detection during merge process.
    
    Attributes:
        detection: Original FieldDetection
        merged: Whether this detection has been merged into another
        merged_into_id: ID of the detection this was merged into
    """
    detection: FieldDetection
    merged: bool = False
    merged_into_id: Optional[int] = None


class EnsembleMerger:
    """
    Merges detections from multiple sources into a unified list.
    
    Responsibilities:
    - Combine detections from PDFStructureDetector, GeometricDetector, and VisionAI
    - Deduplicate overlapping fields using IoU threshold
    - Resolve conflicts using priority and semantic rules
    - Return sorted, deduplicated list of FieldDetection objects
    
    Priority Order:
    1. PDF_STRUCTURE (always preferred)
    2. GEOMETRIC
    3. VISION
    
    Conflict Resolution:
    - Higher priority source wins for overlapping fields
    - Labeled fields preferred over unlabeled
    - Checkbox type preferred over text for small squares
    - Signature geometry overrides AI type guesses
    """
    
    # Default IoU threshold for considering fields as duplicates
    DEFAULT_IOU_THRESHOLD = 0.30
    
    def __init__(
        self,
        iou_threshold: float = DEFAULT_IOU_THRESHOLD,
        debug: bool = False
    ):
        """
        Initialize the ensemble merger.
        
        Args:
            iou_threshold: IoU threshold for deduplication (default 0.30)
            debug: If True, enable verbose logging
        """
        self.iou_threshold = iou_threshold
        self.debug = debug
        
        if self.debug:
            logging.basicConfig(level=logging.DEBUG)
    
    def merge(
        self,
        pdf_structure_fields: List[FieldDetection],
        geometric_fields: List[FieldDetection],
        vision_fields: List[FieldDetection],
    ) -> List[FieldDetection]:
        """
        Merge detections from all sources into a unified list.
        
        Args:
            pdf_structure_fields: Detections from PDFStructureDetector
            geometric_fields: Detections from GeometricDetector
            vision_fields: Detections from VisionAI detector
        
        Returns:
            Unified list of FieldDetection sorted by page_index and position
        """
        # Handle empty inputs gracefully
        if not pdf_structure_fields and not geometric_fields and not vision_fields:
            return []
        
        # Combine all detections with their source priority
        all_detections: List[FieldDetection] = []
        all_detections.extend(pdf_structure_fields or [])
        all_detections.extend(geometric_fields or [])
        all_detections.extend(vision_fields or [])
        
        if self.debug:
            logger.debug(f"Total detections before merge: {len(all_detections)}")
            logger.debug(f"  PDF Structure: {len(pdf_structure_fields or [])}")
            logger.debug(f"  Geometric: {len(geometric_fields or [])}")
            logger.debug(f"  Vision: {len(vision_fields or [])}")
        
        # Sort by priority (lower = higher priority)
        all_detections.sort(key=lambda d: d.source.priority)
        
        # Deduplicate using IoU
        merged_detections = self._deduplicate_by_iou(all_detections)
        
        if self.debug:
            logger.debug(f"Total detections after merge: {len(merged_detections)}")
        
        # Sort by page_index, then by y position (top to bottom)
        merged_detections = self._sort_detections(merged_detections)
        
        return merged_detections
    
    def _deduplicate_by_iou(
        self,
        detections: List[FieldDetection]
    ) -> List[FieldDetection]:
        """
        Deduplicate detections using IoU threshold.
        
        Higher priority detections are kept when IoU exceeds threshold.
        
        Args:
            detections: List of detections sorted by priority
        
        Returns:
            Deduplicated list of detections
        """
        if not detections:
            return []
        
        # Track which detections to keep
        kept: List[FieldDetection] = []
        
        for detection in detections:
            # Check if this detection overlaps with any kept detection
            should_keep = True
            merge_target: Optional[FieldDetection] = None
            merge_target_idx: Optional[int] = None
            
            for idx, existing in enumerate(kept):
                # Only compare detections on the same page
                if detection.page_index != existing.page_index:
                    continue
                
                # Calculate IoU
                iou = detection.bbox.iou(existing.bbox)
                
                if iou > self.iou_threshold:
                    # These detections overlap significantly
                    should_keep = False
                    merge_target = existing
                    merge_target_idx = idx
                    
                    if self.debug:
                        logger.debug(
                            f"Overlap detected (IoU={iou:.3f}): "
                            f"{detection.source.value} vs {existing.source.value}"
                        )
                    break
            
            if should_keep:
                kept.append(detection)
            elif merge_target is not None and merge_target_idx is not None:
                # Resolve conflict and potentially update the kept detection
                resolved = self._resolve_conflict(merge_target, detection)
                kept[merge_target_idx] = resolved
        
        return kept
    
    def _resolve_conflict(
        self,
        higher_priority: FieldDetection,
        lower_priority: FieldDetection
    ) -> FieldDetection:
        """
        Resolve conflict between two overlapping detections.
        
        Rules:
        1. Keep higher priority source
        2. Inherit label if higher priority has none
        3. Prefer checkbox over text for small fields
        4. Prefer signature from geometric detector
        
        Args:
            higher_priority: Detection with higher priority (to keep)
            lower_priority: Detection with lower priority (to merge)
        
        Returns:
            Resolved FieldDetection (may be modified copy of higher_priority)
        """
        # Start with the higher priority detection
        result = higher_priority
        
        # Label inheritance: if higher priority has no label, use lower priority's
        if self._is_generic_label(higher_priority.label) and not self._is_generic_label(lower_priority.label):
            if self.debug:
                logger.debug(
                    f"Inheriting label '{lower_priority.label}' from "
                    f"{lower_priority.source.value}"
                )
            result = replace(result, label=lower_priority.label)
        
        # Type conflict resolution
        result = self._resolve_type_conflict(result, lower_priority)
        
        # Confidence: take the higher confidence
        if lower_priority.confidence > result.confidence:
            result = replace(result, confidence=lower_priority.confidence)
        
        return result
    
    def _resolve_type_conflict(
        self,
        primary: FieldDetection,
        secondary: FieldDetection
    ) -> FieldDetection:
        """
        Resolve field type conflicts between two detections.
        
        Rules:
        - Checkbox from structure/geometric overrides text from vision
        - Signature from geometric overrides text from vision
        - Widget type from PDF structure is authoritative
        
        Args:
            primary: Primary detection (higher priority)
            secondary: Secondary detection (lower priority)
        
        Returns:
            Detection with resolved field type
        """
        # If types match, no conflict
        if primary.field_type == secondary.field_type:
            return primary
        
        # Checkbox vs Text: prefer checkbox for small fields
        if (secondary.field_type == FieldType.CHECKBOX and 
            primary.field_type == FieldType.TEXT):
            # Check if the field is small enough to be a checkbox
            if self._is_checkbox_sized(primary.bbox):
                if self.debug:
                    logger.debug(
                        f"Overriding TEXT with CHECKBOX based on size"
                    )
                return replace(primary, field_type=FieldType.CHECKBOX)
        
        # Signature from geometric detector is authoritative
        if (secondary.source == DetectionSource.GEOMETRIC and
            secondary.field_type == FieldType.SIGNATURE and
            primary.field_type == FieldType.TEXT):
            if self.debug:
                logger.debug(
                    f"Overriding TEXT with SIGNATURE from geometric detector"
                )
            return replace(primary, field_type=FieldType.SIGNATURE)
        
        # PDF structure widget type is authoritative
        if primary.source == DetectionSource.STRUCTURE:
            return primary
        
        return primary
    
    def _is_generic_label(self, label: str) -> bool:
        """
        Check if a label is generic (auto-generated).
        
        Args:
            label: Label string to check
        
        Returns:
            True if label appears to be auto-generated
        """
        if not label:
            return True
        
        generic_patterns = [
            "Field ",
            "Text Field ",
            "Checkbox ",
            "Signature ",
            "Widget ",
            "XObject Field ",
        ]
        
        for pattern in generic_patterns:
            if label.startswith(pattern):
                # Check if followed by a number
                suffix = label[len(pattern):]
                if suffix.isdigit():
                    return True
        
        return False
    
    def _is_checkbox_sized(self, bbox: BBox) -> bool:
        """
        Check if a bounding box is sized like a checkbox.
        
        Args:
            bbox: Bounding box to check
        
        Returns:
            True if bbox is small and approximately square
        """
        # Checkbox should be small (< 5% of page in either dimension)
        if bbox.width > 0.05 or bbox.height > 0.05:
            return False
        
        # Checkbox should be approximately square
        aspect_ratio = bbox.width / bbox.height if bbox.height > 0 else 0
        if aspect_ratio < 0.5 or aspect_ratio > 2.0:
            return False
        
        return True
    
    def _sort_detections(
        self,
        detections: List[FieldDetection]
    ) -> List[FieldDetection]:
        """
        Sort detections by page and position.
        
        Sorting order:
        1. page_index ascending
        2. bbox.y descending (top to bottom in visual terms)
        3. bbox.x ascending (left to right)
        
        Args:
            detections: List of detections to sort
        
        Returns:
            Sorted list of detections
        """
        return sorted(
            detections,
            key=lambda d: (
                d.page_index,
                -(d.bbox.y + d.bbox.height),  # Higher y = lower on page visually
                d.bbox.x
            )
        )
    
    def merge_with_acroform(
        self,
        acroform_fields: List[FieldDetection],
        other_fields: List[FieldDetection]
    ) -> List[FieldDetection]:
        """
        Merge AcroForm fields with other detections.
        
        AcroForm fields are always authoritative when they exist.
        
        Args:
            acroform_fields: Detections from AcroForm extraction
            other_fields: Detections from other sources
        
        Returns:
            Merged list with AcroForm fields taking precedence
        """
        if not acroform_fields:
            return other_fields
        
        if not other_fields:
            return acroform_fields
        
        # AcroForm fields are highest priority
        all_detections = list(acroform_fields) + list(other_fields)
        all_detections.sort(key=lambda d: d.source.priority)
        
        return self._deduplicate_by_iou(all_detections)
