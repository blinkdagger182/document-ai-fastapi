"""
Core Data Models for Hybrid Detection Pipeline

This module defines the shared data structures used across all detection components:
- BBox: Bounding box with normalized coordinates (0-1)
- FieldDetection: Internal representation of a detected field
- DetectionSource: Enum for tracking detection method

These models serve as the common interface between:
- AcroFormDetector
- VisionAIDetector
- GeometricDetector
- PDFStructureDetector
- EnsembleMerger

Coordinate System:
- All coordinates are normalized to [0.0, 1.0] range
- Origin is at bottom-left (PDF standard)
- x, y = bottom-left corner of bounding box
- width, height = dimensions of bounding box
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class DetectionSource(str, Enum):
    """
    Source of field detection.
    
    Priority order (highest to lowest):
    1. ACROFORM - Native PDF form fields (100% accurate)
    2. VISION - AI semantic understanding (80-85% accurate)
    3. GEOMETRIC - OpenCV line/box detection (catches what AI misses)
    4. STRUCTURE - PDF object tree parsing (fallback)
    5. MERGED - Result of ensemble merging multiple sources
    """
    ACROFORM = "acroform"
    VISION = "vision"
    GEOMETRIC = "geometric"
    STRUCTURE = "structure"
    MERGED = "merged"
    
    @property
    def priority(self) -> int:
        """Return priority value (lower = higher priority)"""
        priority_map = {
            DetectionSource.ACROFORM: 1,
            DetectionSource.VISION: 2,
            DetectionSource.GEOMETRIC: 3,
            DetectionSource.STRUCTURE: 4,
            DetectionSource.MERGED: 5
        }
        return priority_map[self]


class FieldType(str, Enum):
    """
    Type of form field.
    
    Maps to database FieldType enum.
    """
    TEXT = "text"
    MULTILINE = "multiline"
    CHECKBOX = "checkbox"
    DATE = "date"
    NUMBER = "number"
    SIGNATURE = "signature"
    UNKNOWN = "unknown"


@dataclass
class BBox:
    """
    Bounding box in normalized coordinates (0-1).
    
    Coordinate system:
    - Origin at bottom-left (PDF standard)
    - x, y = bottom-left corner
    - width, height = dimensions
    - All values in range [0.0, 1.0]
    
    Example:
        # Box at bottom-left quarter of page
        bbox = BBox(x=0.0, y=0.0, width=0.5, height=0.5)
        
        # Convert to rect format
        x_min, y_min, x_max, y_max = bbox.to_rect()
        # (0.0, 0.0, 0.5, 0.5)
    """
    x: float  # bottom-left x (0-1)
    y: float  # bottom-left y (0-1)
    width: float  # width (0-1)
    height: float  # height (0-1)
    
    def __post_init__(self):
        """Validate coordinates are in valid range"""
        if not (0.0 <= self.x <= 1.0):
            raise ValueError(f"x must be in [0, 1], got {self.x}")
        if not (0.0 <= self.y <= 1.0):
            raise ValueError(f"y must be in [0, 1], got {self.y}")
        if not (0.0 <= self.width <= 1.0):
            raise ValueError(f"width must be in [0, 1], got {self.width}")
        if not (0.0 <= self.height <= 1.0):
            raise ValueError(f"height must be in [0, 1], got {self.height}")
        if self.x + self.width > 1.0:
            raise ValueError(f"x + width must be <= 1.0, got {self.x + self.width}")
        if self.y + self.height > 1.0:
            raise ValueError(f"y + height must be <= 1.0, got {self.y + self.height}")
    
    def to_rect(self) -> Tuple[float, float, float, float]:
        """
        Convert to rect format (x_min, y_min, x_max, y_max).
        
        Returns:
            Tuple of (x_min, y_min, x_max, y_max) in normalized coordinates
        """
        return (
            self.x,
            self.y,
            self.x + self.width,
            self.y + self.height
        )
    
    def area(self) -> float:
        """
        Calculate area of bounding box.
        
        Returns:
            Area in normalized coordinate space (0-1)
        """
        return self.width * self.height
    
    def center(self) -> Tuple[float, float]:
        """
        Calculate center point of bounding box.
        
        Returns:
            Tuple of (center_x, center_y) in normalized coordinates
        """
        return (
            self.x + self.width / 2.0,
            self.y + self.height / 2.0
        )
    
    def intersects(self, other: 'BBox') -> bool:
        """
        Check if this bbox intersects with another bbox.
        
        Args:
            other: Another BBox instance
            
        Returns:
            True if bboxes overlap, False otherwise
        """
        x1_min, y1_min, x1_max, y1_max = self.to_rect()
        x2_min, y2_min, x2_max, y2_max = other.to_rect()
        
        # Check if one box is to the left of the other
        if x1_max <= x2_min or x2_max <= x1_min:
            return False
        
        # Check if one box is above the other
        if y1_max <= y2_min or y2_max <= y1_min:
            return False
        
        return True
    
    def intersection_area(self, other: 'BBox') -> float:
        """
        Calculate intersection area with another bbox.
        
        Args:
            other: Another BBox instance
            
        Returns:
            Intersection area in normalized coordinate space (0-1)
        """
        if not self.intersects(other):
            return 0.0
        
        x1_min, y1_min, x1_max, y1_max = self.to_rect()
        x2_min, y2_min, x2_max, y2_max = other.to_rect()
        
        # Calculate intersection rectangle
        x_min = max(x1_min, x2_min)
        y_min = max(y1_min, y2_min)
        x_max = min(x1_max, x2_max)
        y_max = min(y1_max, y2_max)
        
        width = x_max - x_min
        height = y_max - y_min
        
        return width * height
    
    @classmethod
    def from_rect(cls, x_min: float, y_min: float, x_max: float, y_max: float) -> 'BBox':
        """
        Create BBox from rect format (x_min, y_min, x_max, y_max).
        
        Args:
            x_min: Left edge (0-1)
            y_min: Bottom edge (0-1)
            x_max: Right edge (0-1)
            y_max: Top edge (0-1)
            
        Returns:
            BBox instance
        """
        return cls(
            x=x_min,
            y=y_min,
            width=x_max - x_min,
            height=y_max - y_min
        )
    
    @classmethod
    def from_pixels(
        cls,
        x_px: float,
        y_px: float,
        width_px: float,
        height_px: float,
        page_width_px: float,
        page_height_px: float
    ) -> 'BBox':
        """
        Create BBox from pixel coordinates.
        
        Args:
            x_px: Left edge in pixels
            y_px: Bottom edge in pixels (PDF coordinate system)
            width_px: Width in pixels
            height_px: Height in pixels
            page_width_px: Page width in pixels
            page_height_px: Page height in pixels
            
        Returns:
            BBox instance with normalized coordinates
        """
        return cls(
            x=x_px / page_width_px,
            y=y_px / page_height_px,
            width=width_px / page_width_px,
            height=height_px / page_height_px
        )


@dataclass
class FieldDetection:
    """
    Internal representation of a detected form field.
    
    This is the common data structure used by all detectors:
    - AcroFormDetector
    - VisionAIDetector
    - GeometricDetector
    - PDFStructureDetector
    
    After detection, these objects are passed to EnsembleMerger for deduplication,
    then saved to the database as FieldRegion records.
    
    Attributes:
        page_index: Zero-based page number
        bbox: Bounding box in normalized coordinates
        field_type: Type of field (text, checkbox, etc.)
        label: Human-readable label for the field
        confidence: Detection confidence score (0-1)
        source: Which detector found this field
        template_key: Optional key for template matching
    """
    page_index: int
    bbox: BBox
    field_type: FieldType
    label: str
    confidence: float
    source: DetectionSource
    template_key: Optional[str] = None
    
    def __post_init__(self):
        """Validate field detection data"""
        if self.page_index < 0:
            raise ValueError(f"page_index must be >= 0, got {self.page_index}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if not isinstance(self.bbox, BBox):
            raise TypeError(f"bbox must be BBox instance, got {type(self.bbox)}")
        if not isinstance(self.field_type, FieldType):
            raise TypeError(f"field_type must be FieldType enum, got {type(self.field_type)}")
        if not isinstance(self.source, DetectionSource):
            raise TypeError(f"source must be DetectionSource enum, got {type(self.source)}")
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dict representation suitable for JSON serialization
        """
        return {
            'page_index': self.page_index,
            'bbox': {
                'x': self.bbox.x,
                'y': self.bbox.y,
                'width': self.bbox.width,
                'height': self.bbox.height
            },
            'field_type': self.field_type.value,
            'label': self.label,
            'confidence': self.confidence,
            'source': self.source.value,
            'template_key': self.template_key
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FieldDetection':
        """
        Create FieldDetection from dictionary.
        
        Args:
            data: Dict with field detection data
            
        Returns:
            FieldDetection instance
        """
        bbox_data = data['bbox']
        return cls(
            page_index=data['page_index'],
            bbox=BBox(
                x=bbox_data['x'],
                y=bbox_data['y'],
                width=bbox_data['width'],
                height=bbox_data['height']
            ),
            field_type=FieldType(data['field_type']),
            label=data['label'],
            confidence=data['confidence'],
            source=DetectionSource(data['source']),
            template_key=data.get('template_key')
        )
