"""
Hybrid Detection Pipeline - Phase 5

This module implements the orchestration layer that ties together all detection sources:
- PDFStructureDetector (native PDF form fields)
- GeometricDetector (OpenCV-based visual detection)
- VisionDetector (LLM-based semantic detection)
- EnsembleMerger (deduplication and prioritization)

The pipeline is a pure orchestration layer with no database, FastAPI, or cloud dependencies.
It takes a PDF path and returns a unified List[FieldDetection].

Usage:
    pipeline = HybridDetectionPipeline()
    fields = pipeline.detect_fields_for_pdf("form.pdf")
"""

import logging
from typing import List, Optional, Protocol, runtime_checkable
import numpy as np

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .detection_models import BBox, FieldDetection, FieldType, DetectionSource
from .pdf_structure_detector import PDFStructureDetector
from .geometric_detector import GeometricDetector
from .ensemble_merger import EnsembleMerger


# Configure logging
logger = logging.getLogger(__name__)


@runtime_checkable
class VisionDetectorProtocol(Protocol):
    """
    Protocol for vision-based field detectors.
    
    Any vision detector that implements this interface can be used
    with the HybridDetectionPipeline.
    """
    
    def detect_fields(
        self,
        pdf_path: str,
        document_id: Optional[str] = None,
    ) -> List[FieldDetection]:
        """
        Detect form fields in a PDF using vision/LLM analysis.
        
        Args:
            pdf_path: Path to the PDF file
            document_id: Optional document identifier for tracking
        
        Returns:
            List of FieldDetection objects
        """
        ...


class HybridDetectionPipeline:
    """
    Orchestrates all detection sources for comprehensive form field detection.
    
    This pipeline:
    1. Runs PDFStructureDetector to extract native PDF form fields
    2. Renders PDF pages to images for visual detection
    3. Runs GeometricDetector on each page image
    4. Optionally runs a VisionDetector (LLM-based)
    5. Merges all results via EnsembleMerger
    
    The pipeline is designed to be:
    - Pure: No database, FastAPI, or cloud dependencies
    - Fault-tolerant: Individual detector failures don't crash the pipeline
    - Configurable: Detectors can be injected or disabled
    - Testable: Easy to mock individual components
    
    Example:
        pipeline = HybridDetectionPipeline()
        fields = pipeline.detect_fields_for_pdf("form.pdf")
        
        # With custom detectors
        pipeline = HybridDetectionPipeline(
            pdf_structure_detector=my_structure_detector,
            geometric_detector=my_geo_detector,
            vision_detector=my_vision_detector,
            debug=True
        )
    """
    
    # Default DPI for rendering PDF pages to images
    DEFAULT_RENDER_DPI = 144
    
    def __init__(
        self,
        pdf_structure_detector: Optional[PDFStructureDetector] = None,
        geometric_detector: Optional[GeometricDetector] = None,
        vision_detector: Optional[VisionDetectorProtocol] = None,
        ensemble_merger: Optional[EnsembleMerger] = None,
        render_dpi: int = DEFAULT_RENDER_DPI,
        debug: bool = False,
    ):
        """
        Initialize the hybrid detection pipeline.
        
        Args:
            pdf_structure_detector: PDFStructureDetector instance (created if None)
            geometric_detector: GeometricDetector instance (created if None)
            vision_detector: VisionDetector instance (optional, skipped if None)
            ensemble_merger: EnsembleMerger instance (created if None)
            render_dpi: DPI for rendering PDF pages to images
            debug: If True, enable verbose logging
        """
        self.debug = debug
        self.render_dpi = render_dpi
        
        # Initialize detectors (create defaults if not provided)
        self.pdf_structure_detector = pdf_structure_detector or PDFStructureDetector(debug=debug)
        self.geometric_detector = geometric_detector or GeometricDetector(debug=debug)
        self.vision_detector = vision_detector  # Optional, may be None
        self.ensemble_merger = ensemble_merger or EnsembleMerger(debug=debug)
        
        if self.debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.debug("HybridDetectionPipeline initialized")
            logger.debug(f"  PDF Structure Detector: {type(self.pdf_structure_detector).__name__}")
            logger.debug(f"  Geometric Detector: {type(self.geometric_detector).__name__}")
            logger.debug(f"  Vision Detector: {type(self.vision_detector).__name__ if self.vision_detector else 'None'}")
            logger.debug(f"  Ensemble Merger: {type(self.ensemble_merger).__name__}")
            logger.debug(f"  Render DPI: {self.render_dpi}")
    
    def detect_fields_for_pdf(
        self,
        pdf_path: str,
        document_id: Optional[str] = None,
    ) -> List[FieldDetection]:
        """
        High-level entry point for detecting form fields in a PDF.
        
        This method:
        1. Runs PDFStructureDetector to extract native PDF form fields
        2. Renders PDF pages to images
        3. Runs GeometricDetector on each page image
        4. Optionally runs VisionDetector
        5. Merges all results via EnsembleMerger
        
        Args:
            pdf_path: Path to the PDF file
            document_id: Optional document identifier for tracking
        
        Returns:
            Unified list of FieldDetection objects, deduplicated and sorted
        """
        if self.debug:
            logger.debug(f"Starting hybrid detection for: {pdf_path}")
        
        # Collect detections from each source
        pdf_structure_fields: List[FieldDetection] = []
        geometric_fields: List[FieldDetection] = []
        vision_fields: List[FieldDetection] = []
        
        # Step 1: Run PDF Structure Detector
        pdf_structure_fields = self._run_pdf_structure_detector(pdf_path)
        
        # Step 2: Render PDF to images and run Geometric Detector
        geometric_fields = self._run_geometric_detector(pdf_path)
        
        # Step 3: Run Vision Detector (if available)
        vision_fields = self._run_vision_detector(pdf_path, document_id)
        
        # Step 4: Merge all detections
        if self.debug:
            logger.debug(f"Merging detections:")
            logger.debug(f"  PDF Structure: {len(pdf_structure_fields)} fields")
            logger.debug(f"  Geometric: {len(geometric_fields)} fields")
            logger.debug(f"  Vision: {len(vision_fields)} fields")
        
        merged_fields = self.ensemble_merger.merge(
            pdf_structure_fields=pdf_structure_fields,
            geometric_fields=geometric_fields,
            vision_fields=vision_fields,
        )
        
        if self.debug:
            logger.debug(f"Final merged result: {len(merged_fields)} fields")
        
        return merged_fields
    
    def _run_pdf_structure_detector(self, pdf_path: str) -> List[FieldDetection]:
        """
        Run the PDF structure detector with error handling.
        
        Args:
            pdf_path: Path to the PDF file
        
        Returns:
            List of FieldDetection objects (empty list on error)
        """
        if self.pdf_structure_detector is None:
            if self.debug:
                logger.debug("PDF Structure Detector is None, skipping")
            return []
        
        try:
            fields = self.pdf_structure_detector.detect_fields(pdf_path)
            
            if self.debug:
                logger.debug(f"PDF Structure Detector found {len(fields)} fields")
            
            return fields
            
        except Exception as e:
            logger.error(f"PDF Structure Detector failed: {type(e).__name__}: {e}")
            if self.debug:
                import traceback
                logger.debug(traceback.format_exc())
            return []
    
    def _run_geometric_detector(self, pdf_path: str) -> List[FieldDetection]:
        """
        Render PDF pages to images and run the geometric detector.
        
        Args:
            pdf_path: Path to the PDF file
        
        Returns:
            List of FieldDetection objects (empty list on error)
        """
        if self.geometric_detector is None:
            if self.debug:
                logger.debug("Geometric Detector is None, skipping")
            return []
        
        try:
            # Render PDF to images
            page_images = self._render_pdf_to_images(pdf_path)
            
            if not page_images:
                if self.debug:
                    logger.debug("No page images rendered, skipping geometric detection")
                return []
            
            # Run geometric detector on each page
            all_fields: List[FieldDetection] = []
            
            for page_index, image in enumerate(page_images):
                try:
                    page_fields = self.geometric_detector.detect_page_fields(
                        page_image=image,
                        page_index=page_index,
                    )
                    all_fields.extend(page_fields)
                    
                    if self.debug:
                        logger.debug(f"Geometric Detector found {len(page_fields)} fields on page {page_index}")
                        
                except Exception as e:
                    logger.error(f"Geometric Detector failed on page {page_index}: {type(e).__name__}: {e}")
                    continue
            
            if self.debug:
                logger.debug(f"Geometric Detector total: {len(all_fields)} fields")
            
            return all_fields
            
        except Exception as e:
            logger.error(f"Geometric Detector failed: {type(e).__name__}: {e}")
            if self.debug:
                import traceback
                logger.debug(traceback.format_exc())
            return []
    
    def _run_vision_detector(
        self,
        pdf_path: str,
        document_id: Optional[str] = None
    ) -> List[FieldDetection]:
        """
        Run the vision detector with error handling.
        
        Args:
            pdf_path: Path to the PDF file
            document_id: Optional document identifier
        
        Returns:
            List of FieldDetection objects (empty list on error or if no detector)
        """
        if self.vision_detector is None:
            if self.debug:
                logger.debug("Vision Detector is None, skipping")
            return []
        
        try:
            fields = self.vision_detector.detect_fields(
                pdf_path=pdf_path,
                document_id=document_id,
            )
            
            if self.debug:
                logger.debug(f"Vision Detector found {len(fields)} fields")
            
            return fields
            
        except Exception as e:
            logger.error(f"Vision Detector failed: {type(e).__name__}: {e}")
            if self.debug:
                import traceback
                logger.debug(traceback.format_exc())
            return []
    
    def _render_pdf_to_images(self, pdf_path: str) -> List[np.ndarray]:
        """
        Render each PDF page to an RGB numpy array.
        
        Uses PyMuPDF (fitz) for rendering.
        
        Args:
            pdf_path: Path to the PDF file
        
        Returns:
            List of numpy arrays (H x W x 3, RGB format)
        """
        if fitz is None:
            logger.error("PyMuPDF (fitz) not available, cannot render PDF")
            return []
        
        images: List[np.ndarray] = []
        
        try:
            doc = fitz.open(pdf_path)
            
            # Calculate zoom factor for desired DPI
            # PyMuPDF default is 72 DPI
            zoom = self.render_dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            for page_index in range(len(doc)):
                try:
                    page = doc[page_index]
                    
                    # Render to pixmap
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    
                    # Convert to numpy array (RGB)
                    img = np.frombuffer(pix.samples, dtype=np.uint8)
                    img = img.reshape(pix.height, pix.width, 3)
                    
                    images.append(img)
                    
                    if self.debug:
                        logger.debug(f"Rendered page {page_index}: {pix.width}x{pix.height}")
                        
                except Exception as e:
                    logger.error(f"Failed to render page {page_index}: {type(e).__name__}: {e}")
                    # Append None placeholder to maintain page indexing
                    images.append(np.zeros((1, 1, 3), dtype=np.uint8))
            
            doc.close()
            
            if self.debug:
                logger.debug(f"Rendered {len(images)} pages from PDF")
            
            return images
            
        except Exception as e:
            logger.error(f"Failed to render PDF: {type(e).__name__}: {e}")
            return []
