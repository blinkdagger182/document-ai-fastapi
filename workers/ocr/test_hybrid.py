#!/usr/bin/env python3
"""
Test hybrid OCR worker locally
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import fitz
from main import detect_acroform_fields, detect_ocr_fields


def test_pdf(pdf_path: str):
    """Test hybrid detection on a PDF"""
    print(f"🧪 Testing: {pdf_path}")
    print()
    
    # Open PDF
    doc = fitz.open(pdf_path)
    print(f"📄 Pages: {len(doc)}")
    print(f"📋 Is Form PDF: {doc.is_form_pdf}")
    print()
    
    # Try AcroForm detection
    print("1️⃣ Testing AcroForm detection...")
    acroform_fields = detect_acroform_fields(doc)
    
    if acroform_fields:
        print(f"✅ AcroForm detected: {len(acroform_fields)} fields")
        print()
        print("Fields found:")
        for i, field in enumerate(acroform_fields[:5], 1):
            print(f"  {i}. {field['label']}")
            print(f"     Type: {field['field_type']}")
            print(f"     Position: ({field['x']:.3f}, {field['y']:.3f})")
            print(f"     Size: {field['width']:.3f} x {field['height']:.3f}")
            print(f"     Confidence: {field['confidence']}")
            print()
    else:
        print("❌ No AcroForm found")
        print()
        print("2️⃣ Falling back to OCR...")
        ocr_fields = detect_ocr_fields(doc, pdf_path)
        
        if ocr_fields:
            print(f"✅ OCR detected: {len(ocr_fields)} fields")
            print()
            print("Fields found:")
            for i, field in enumerate(ocr_fields[:5], 1):
                print(f"  {i}. {field['label'][:50]}")
                print(f"     Type: {field['field_type']}")
                print(f"     Confidence: {field['confidence']:.2f}")
                print()
        else:
            print("❌ No fields detected")
    
    doc.close()
    print()
    print("🎉 Test complete!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_hybrid.py <pdf_file>")
        sys.exit(1)
    
    test_pdf(sys.argv[1])
