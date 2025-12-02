"""
Modal.com worker for OCR processing.
Deploy with: modal deploy deployment/modal_worker.py
"""
import modal
from typing import List, Dict

# Create Modal app
stub = modal.Stub("documentai-ocr")

# Define image with PaddleOCR dependencies
image = modal.Image.debian_slim().pip_install(
    "paddleocr==2.7.0.3",
    "paddlepaddle==2.6.0",
    "PyMuPDF==1.23.21",
    "Pillow==10.2.0"
)


@stub.function(
    image=image,
    gpu="T4",  # Use GPU for faster OCR
    timeout=600,
    memory=4096
)
def run_ocr_modal(pdf_bytes: bytes) -> Dict:
    """
    Run PaddleOCR on a PDF document.
    
    Args:
        pdf_bytes: PDF file as bytes
        
    Returns:
        Dict with boxes and page_count
    """
    from paddleocr import PaddleOCR
    import fitz
    from PIL import Image
    import io
    
    ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
    
    # Open PDF from bytes
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    all_boxes = []
    
    for page_num in range(page_count):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        
        # Run OCR
        result = ocr.ocr(img_bytes, cls=True)
        
        if result and result[0]:
            for line in result[0]:
                bbox_points = line[0]
                text_info = line[1]
                
                # Normalize coordinates
                x_coords = [p[0] for p in bbox_points]
                y_coords = [p[1] for p in bbox_points]
                x = min(x_coords) / pix.width
                y = min(y_coords) / pix.height
                width = (max(x_coords) - min(x_coords)) / pix.width
                height = (max(y_coords) - min(y_coords)) / pix.height
                
                all_boxes.append({
                    "text": text_info[0],
                    "confidence": float(text_info[1]),
                    "bbox": [x, y, width, height],
                    "page_index": page_num
                })
    
    doc.close()
    
    return {
        "boxes": all_boxes,
        "page_count": page_count
    }


@stub.local_entrypoint()
def main():
    """Test the OCR function locally"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: modal run deployment/modal_worker.py <pdf_file>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    result = run_ocr_modal.remote(pdf_bytes)
    print(f"Found {len(result['boxes'])} text boxes in {result['page_count']} pages")
    for box in result['boxes'][:5]:
        print(f"  - {box['text'][:50]} (confidence: {box['confidence']:.2f})")
