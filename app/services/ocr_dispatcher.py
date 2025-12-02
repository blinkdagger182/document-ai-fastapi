from typing import Protocol, List, Dict, Any
from dataclasses import dataclass
from app.config import settings
import httpx


@dataclass
class OCRBox:
    text: str
    confidence: float
    bbox: List[float]  # [x, y, width, height]
    page_index: int


@dataclass
class OCRResult:
    boxes: List[OCRBox]
    page_count: int


class OCRBackend(Protocol):
    def run_ocr(self, local_pdf_path: str) -> OCRResult:
        ...


class LocalPaddleOCRBackend:
    def __init__(self):
        from paddleocr import PaddleOCR
        self.ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
    
    def run_ocr(self, local_pdf_path: str) -> OCRResult:
        import fitz  # PyMuPDF
        from PIL import Image
        import io
        
        doc = fitz.open(local_pdf_path)
        page_count = len(doc)
        all_boxes = []
        
        for page_num in range(page_count):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))
            
            # Run PaddleOCR
            result = self.ocr.ocr(img_bytes, cls=True)
            
            if result and result[0]:
                for line in result[0]:
                    bbox_points = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    text_info = line[1]  # (text, confidence)
                    
                    # Convert to normalized coordinates [0,1]
                    x_coords = [p[0] for p in bbox_points]
                    y_coords = [p[1] for p in bbox_points]
                    x = min(x_coords) / pix.width
                    y = min(y_coords) / pix.height
                    width = (max(x_coords) - min(x_coords)) / pix.width
                    height = (max(y_coords) - min(y_coords)) / pix.height
                    
                    all_boxes.append(OCRBox(
                        text=text_info[0],
                        confidence=text_info[1],
                        bbox=[x, y, width, height],
                        page_index=page_num
                    ))
        
        doc.close()
        return OCRResult(boxes=all_boxes, page_count=page_count)


class GCPHTTPBackend:
    def __init__(self):
        self.endpoint = settings.gcp_ocr_endpoint
    
    def run_ocr(self, local_pdf_path: str) -> OCRResult:
        with open(local_pdf_path, 'rb') as f:
            files = {'file': f}
            response = httpx.post(f"{self.endpoint}/ocr", files=files, timeout=300)
            response.raise_for_status()
            data = response.json()
        
        boxes = [
            OCRBox(
                text=box['text'],
                confidence=box['confidence'],
                bbox=box['bbox'],
                page_index=box['page_index']
            )
            for box in data['boxes']
        ]
        return OCRResult(boxes=boxes, page_count=data['page_count'])


class ModalHTTPBackend:
    def __init__(self):
        self.endpoint = settings.modal_ocr_endpoint
    
    def run_ocr(self, local_pdf_path: str) -> OCRResult:
        with open(local_pdf_path, 'rb') as f:
            files = {'file': f}
            response = httpx.post(f"{self.endpoint}/ocr", files=files, timeout=300)
            response.raise_for_status()
            data = response.json()
        
        boxes = [
            OCRBox(
                text=box['text'],
                confidence=box['confidence'],
                bbox=box['bbox'],
                page_index=box['page_index']
            )
            for box in data['boxes']
        ]
        return OCRResult(boxes=boxes, page_count=data['page_count'])


def get_ocr_backend() -> OCRBackend:
    if settings.ocr_backend == "local":
        return LocalPaddleOCRBackend()
    elif settings.ocr_backend == "gcp":
        return GCPHTTPBackend()
    elif settings.ocr_backend == "modal":
        return ModalHTTPBackend()
    else:
        raise ValueError(f"Unknown OCR backend: {settings.ocr_backend}")
