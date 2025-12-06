"""
Vision Field Detection Worker - Cloud Run Service

This is a separate Cloud Run service that performs vision-based field detection
for PDFs without AcroForm fields. It can be triggered via Cloud Tasks.

Endpoints:
    POST /detect - Detect form fields using vision AI
    GET /health - Health check
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
import os
import sys

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from workers.vision_field_detector import VisionFieldDetector
from app.utils.logging import get_logger

app = FastAPI(title="DocumentAI Vision Field Detection Worker")
logger = get_logger(__name__)


class VisionDetectionRequest(BaseModel):
    document_id: str
    provider: Optional[Literal["openai", "gemini"]] = "openai"
    force: Optional[bool] = False


class VisionDetectionResponse(BaseModel):
    document_id: str
    status: str
    page_count: Optional[int] = None
    fields_found: Optional[int] = None
    reason: Optional[str] = None


@app.post("/detect", response_model=VisionDetectionResponse)
async def detect_fields(request: VisionDetectionRequest):
    """
    Detect form fields using vision AI.
    
    This endpoint is called by Cloud Tasks after a document is uploaded
    and determined to have no AcroForm fields.
    """
    logger.info(f"Starting vision detection for document {request.document_id} using {request.provider}")
    
    try:
        # Get API key from environment
        if request.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
        elif request.provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {request.provider}")
        
        # Initialize detector
        detector = VisionFieldDetector(
            provider=request.provider,
            api_key=api_key
        )
        
        # Run detection
        result = detector.detect_form_fields(
            document_id=request.document_id,
            force=request.force
        )
        
        # Return response
        return VisionDetectionResponse(
            document_id=result['document_id'],
            status=result['status'],
            page_count=result.get('page_count'),
            fields_found=result.get('fields_found'),
            reason=result.get('reason')
        )
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Vision detection failed for document {request.document_id}: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "vision-detection-worker",
        "providers": ["openai", "gemini"]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
