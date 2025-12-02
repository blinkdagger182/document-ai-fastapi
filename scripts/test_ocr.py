#!/usr/bin/env python3
"""
Test OCR functionality locally.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.ocr_dispatcher import get_ocr_backend


def test_ocr(pdf_path: str):
    """Test OCR on a PDF file"""
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)
    
    print(f"Testing OCR on: {pdf_path}")
    print("Loading OCR backend...")
    
    backend = get_ocr_backend()
    print(f"Using backend: {backend.__class__.__name__}")
    
    print("Running OCR...")
    result = backend.run_ocr(pdf_path)
    
    print(f"\nResults:")
    print(f"  Pages: {result.page_count}")
    print(f"  Text boxes found: {len(result.boxes)}")
    
    print(f"\nFirst 10 boxes:")
    for i, box in enumerate(result.boxes[:10]):
        print(f"  {i+1}. [{box.page_index}] {box.text[:50]} (conf: {box.confidence:.2f})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_ocr.py <pdf_file>")
        sys.exit(1)
    
    test_ocr(sys.argv[1])
