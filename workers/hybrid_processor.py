"""
Hybrid Detection Processor

This module provides the integration layer between the HybridDetectionPipeline
and the FastAPI/database infrastructure.

It handles:
1. Loading documents from storage
2. Running the hybrid detection pipeline
3. Saving detected fields to the database
4. Updating document status

This is the main entry point for processing documents with the new
hybrid detection system.
"""

import os
import sys
import tempfile
from typing import Dict, List, Optional
from uuid import UUID
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.field import FieldRegion, FieldType as DBFieldType
from app.services.storage import get_storage_service
from app.utils.logging import get_logger

from .detection_models import FieldDetection, FieldType, DetectionSource
from .hybrid_detection_pipeline import HybridDetectionPipeline
from .vision_detector_adapter import VisionDetectorAdapter

logger = get_logger(__name__)


class HybridProcessor:
    """
    Processes documents using the HybridDetectionPipeline.
    
    This class:
    1. Downloads the PDF from storage
    2. Runs the hybrid detection pipeline
    3. Saves detected fields to the database
    4. Updates document status
    
    Example:
        processor = HybridProcessor()
        result = processor.process_document("doc-uuid-123")
    """
    
    # Mapping from detection FieldType to database FieldType
    FIELD_TYPE_MAP = {
        FieldType.TEXT: DBFieldType.text,
        FieldType.MULTILINE: DBFieldType.multiline,
        FieldType.CHECKBOX: DBFieldType.checkbox,
        FieldType.DATE: DBFieldType.date,
        FieldType.NUMBER: DBFieldType.number,
        FieldType.SIGNATURE: DBFieldType.signature,
        FieldType.UNKNOWN: DBFieldType.unknown,
    }
    
    def __init__(
        self,
        enable_vision: bool = True,
        vision_provider: str = "openai",
        vision_api_key: Optional[str] = None,
        debug: bool = False,
    ):
        """
        Initialize the hybrid processor.
        
        Args:
            enable_vision: If True, include vision AI detection
            vision_provider: Vision provider ("openai" or "gemini")
            vision_api_key: API key for vision provider
            debug: If True, enable verbose logging
        """
        self.debug = debug
        self.enable_vision = enable_vision
        
        # Create vision detector if enabled
        vision_detector = None
        if enable_vision:
            vision_detector = VisionDetectorAdapter(
                provider=vision_provider,
                api_key=vision_api_key,
                debug=debug,
            )
        
        # Create the hybrid pipeline
        self.pipeline = HybridDetectionPipeline(
            vision_detector=vision_detector,
            debug=debug,
        )
        
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.debug(f"HybridProcessor initialized (vision={enable_vision})")
    
    def process_document(
        self,
        document_id: str,
        force: bool = False,
    ) -> Dict:
        """
        Process a document using hybrid detection.
        
        Args:
            document_id: UUID of the document to process
            force: If True, re-process even if fields already exist
        
        Returns:
            Dict with processing results
        """
        logger.info(f"Starting hybrid processing for document {document_id}")
        
        db = SessionLocal()
        try:
            # Fetch document
            doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
            if not doc:
                raise ValueError(f"Document {document_id} not found")
            
            # Check if already processed (unless force=True)
            if not force:
                existing_fields = db.query(FieldRegion).filter(
                    FieldRegion.document_id == doc.id
                ).count()
                
                if existing_fields > 0:
                    logger.info(
                        f"Document {document_id} already has {existing_fields} fields, "
                        "skipping (use force=True to re-process)"
                    )
                    return {
                        'document_id': document_id,
                        'status': 'skipped',
                        'reason': 'already_processed',
                        'existing_fields': existing_fields
                    }
            else:
                # Delete existing fields if force=True
                db.query(FieldRegion).filter(FieldRegion.document_id == doc.id).delete()
                db.commit()
                logger.info(f"Deleted existing fields for document {document_id}")
            
            # Update status to processing
            doc.status = DocumentStatus.processing
            db.commit()
            
            # Download file from storage
            storage = get_storage_service()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_path = tmp_file.name
            
            try:
                # Download PDF
                storage.download_to_path(key=doc.storage_key_original, local_path=tmp_path)
                
                # Run hybrid detection pipeline
                detections = self.pipeline.detect_fields_for_pdf(
                    pdf_path=tmp_path,
                    document_id=document_id,
                )
                
                # Get page count from pipeline (via PyMuPDF)
                import fitz
                pdf_doc = fitz.open(tmp_path)
                page_count = len(pdf_doc)
                pdf_doc.close()
                
                # Determine if document has AcroForm (structure detections)
                has_acroform = any(
                    d.source == DetectionSource.STRUCTURE
                    for d in detections
                )
                
                # Save detections to database
                self._save_detections_to_db(db, doc.id, detections)
                
                # Update document status
                doc.status = DocumentStatus.ready
                doc.page_count = page_count
                doc.acroform = has_acroform
                db.commit()
                
                # Build result summary
                fields_by_source = {}
                for d in detections:
                    source = d.source.value
                    fields_by_source[source] = fields_by_source.get(source, 0) + 1
                
                fields_by_page = {}
                for d in detections:
                    page = d.page_index
                    fields_by_page[page] = fields_by_page.get(page, 0) + 1
                
                logger.info(
                    f"Hybrid processing completed for document {document_id}: "
                    f"{len(detections)} fields found"
                )
                
                return {
                    'document_id': document_id,
                    'status': 'success',
                    'page_count': page_count,
                    'fields_found': len(detections),
                    'fields_by_source': fields_by_source,
                    'fields_by_page': fields_by_page,
                    'acroform': has_acroform,
                }
                
            finally:
                # Cleanup temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Hybrid processing failed for document {document_id}: {error_msg}")
            
            try:
                doc = db.query(Document).filter(Document.id == UUID(document_id)).first()
                if doc:
                    doc.status = DocumentStatus.failed
                    doc.error_message = error_msg
                    db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update document status: {db_error}")
            
            raise
        
        finally:
            db.close()
    
    def _save_detections_to_db(
        self,
        db,
        document_id: UUID,
        detections: List[FieldDetection],
    ) -> None:
        """
        Save field detections to the database.
        
        Args:
            db: Database session
            document_id: Document UUID
            detections: List of FieldDetection objects
        """
        for detection in detections:
            # Map field type
            db_field_type = self.FIELD_TYPE_MAP.get(
                detection.field_type,
                DBFieldType.unknown
            )
            
            # Create field region record
            field_region = FieldRegion(
                document_id=document_id,
                page_index=detection.page_index,
                x=detection.bbox.x,
                y=detection.bbox.y,
                width=detection.bbox.width,
                height=detection.bbox.height,
                field_type=db_field_type,
                label=detection.label[:255] if detection.label else "Unnamed Field",
                confidence=detection.confidence,
                template_key=detection.template_key,
            )
            db.add(field_region)
        
        db.commit()
        logger.info(f"Saved {len(detections)} field regions to database")
    
    def process_document_from_path(
        self,
        pdf_path: str,
        document_id: Optional[str] = None,
    ) -> List[FieldDetection]:
        """
        Process a PDF file directly without database interaction.
        
        Useful for testing or standalone processing.
        
        Args:
            pdf_path: Path to the PDF file
            document_id: Optional document identifier
        
        Returns:
            List of FieldDetection objects
        """
        return self.pipeline.detect_fields_for_pdf(
            pdf_path=pdf_path,
            document_id=document_id,
        )


# Convenience function for direct usage
def process_document_hybrid(
    document_id: str,
    force: bool = False,
    enable_vision: bool = True,
    vision_provider: str = "openai",
    debug: bool = False,
) -> Dict:
    """
    Process a document using hybrid detection.
    
    Args:
        document_id: UUID of the document
        force: Re-process even if fields exist
        enable_vision: Include vision AI detection
        vision_provider: Vision provider ("openai" or "gemini")
        debug: Enable verbose logging
    
    Returns:
        Processing results dict
    """
    processor = HybridProcessor(
        enable_vision=enable_vision,
        vision_provider=vision_provider,
        debug=debug,
    )
    return processor.process_document(document_id, force=force)


if __name__ == "__main__":
    """
    CLI usage:
    python hybrid_processor.py <document_id> [--force] [--no-vision] [--debug]
    """
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Hybrid document processing")
    parser.add_argument("document_id", help="Document UUID")
    parser.add_argument("--force", action="store_true", help="Re-process even if fields exist")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision AI detection")
    parser.add_argument("--vision-provider", choices=["openai", "gemini"], default="openai")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    result = process_document_hybrid(
        document_id=args.document_id,
        force=args.force,
        enable_vision=not args.no_vision,
        vision_provider=args.vision_provider,
        debug=args.debug,
    )
    
    print(json.dumps(result, indent=2))
