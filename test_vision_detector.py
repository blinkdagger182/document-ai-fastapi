#!/usr/bin/env python3
"""
Test script for Vision Field Detector

Usage:
    python test_vision_detector.py <document_id>
    
Environment variables:
    OPENAI_API_KEY - OpenAI API key (for GPT-4o-mini)
    GEMINI_API_KEY - Google Gemini API key (for Gemini Flash)
"""

import sys
import os
import asyncio
from uuid import UUID

# Add workers directory to path
sys.path.insert(0, os.path.dirname(__file__))

from workers.vision_field_detector import VisionFieldDetector, detect_fields_openai, detect_fields_gemini


async def test_vision_detection(document_id: str, provider: str = "openai"):
    """Test vision-based field detection"""
    
    print(f"\n{'='*60}")
    print(f"Testing Vision Field Detection")
    print(f"{'='*60}")
    print(f"Document ID: {document_id}")
    print(f"Provider: {provider}")
    print(f"{'='*60}\n")
    
    try:
        # Validate UUID
        UUID(document_id)
        
        # Run detection
        if provider == "openai":
            print("Using OpenAI GPT-4o-mini...")
            result = detect_fields_openai(document_id, force=True)
        elif provider == "gemini":
            print("Using Google Gemini Flash...")
            result = detect_fields_gemini(document_id, force=True)
        else:
            print(f"Unknown provider: {provider}")
            return
        
        # Print results
        print(f"\n{'='*60}")
        print("RESULTS")
        print(f"{'='*60}")
        print(f"Status: {result['status']}")
        
        if result['status'] == 'success':
            print(f"Pages processed: {result['page_count']}")
            print(f"Total fields found: {result['fields_found']}")
            print(f"\nFields by page:")
            for page_num, count in result['fields_by_page'].items():
                print(f"  Page {page_num + 1}: {count} fields")
        elif result['status'] == 'skipped':
            print(f"Reason: {result['reason']}")
            print(f"Existing fields: {result.get('existing_fields', 0)}")
        
        print(f"{'='*60}\n")
        
    except ValueError as e:
        print(f"❌ Invalid document ID: {e}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_vision_detector.py <document_id> [provider]")
        print("Provider: openai (default) or gemini")
        sys.exit(1)
    
    document_id = sys.argv[1]
    provider = sys.argv[2] if len(sys.argv) > 2 else "openai"
    
    # Check API keys
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    if provider == "gemini" and not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Run test
    asyncio.run(test_vision_detection(document_id, provider))


if __name__ == "__main__":
    main()
