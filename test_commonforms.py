#!/usr/bin/env python3
"""
End-to-end test for CommonForms integration.

Usage:
    # Test with existing document ID
    python test_commonforms.py --document-id <uuid>
    
    # Test with PDF upload (full flow)
    python test_commonforms.py --pdf path/to/test.pdf
    
    # Test sync endpoint (immediate processing)
    python test_commonforms.py --pdf path/to/test.pdf --sync
"""
import argparse
import httpx
import time
import json
import sys

BASE_URL = "http://localhost:8000"


def upload_pdf(pdf_path: str) -> str:
    """Upload a PDF and return the document ID."""
    print(f"📤 Uploading PDF: {pdf_path}")
    
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.split("/")[-1], f, "application/pdf")}
        response = httpx.post(
            f"{BASE_URL}/api/v1/documents/init-upload",
            files=files,
            timeout=60.0
        )
    
    if response.status_code != 201:
        print(f"❌ Upload failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    document_id = data["documentId"]
    print(f"✅ Document uploaded: {document_id}")
    return document_id


def process_commonforms_async(document_id: str) -> str:
    """Start async CommonForms processing and return job ID."""
    print(f"🔄 Starting CommonForms processing for document: {document_id}")
    
    response = httpx.post(
        f"{BASE_URL}/api/v1/process/commonforms/{document_id}",
        timeout=30.0
    )
    
    if response.status_code != 200:
        print(f"❌ Process request failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    job_id = data["jobId"]
    print(f"✅ Job queued: {job_id}")
    return job_id


def poll_job_status(job_id: str, max_attempts: int = 30, interval: int = 2) -> dict:
    """Poll job status until completion or failure."""
    print(f"⏳ Polling job status: {job_id}")
    
    for attempt in range(max_attempts):
        response = httpx.get(
            f"{BASE_URL}/api/v1/process/status/{job_id}",
            timeout=30.0
        )
        
        if response.status_code != 200:
            print(f"❌ Status check failed: {response.status_code}")
            print(response.text)
            sys.exit(1)
        
        data = response.json()
        status = data["status"]
        
        print(f"   Attempt {attempt + 1}/{max_attempts}: {status}")
        
        if status == "completed":
            print("✅ Processing completed!")
            return data
        elif status == "failed":
            print(f"❌ Processing failed: {data.get('error')}")
            sys.exit(1)
        
        time.sleep(interval)
    
    print("❌ Timeout waiting for processing to complete")
    sys.exit(1)


def process_commonforms_sync(document_id: str) -> dict:
    """Process CommonForms synchronously (for testing)."""
    print(f"🔄 Processing CommonForms synchronously for document: {document_id}")
    
    response = httpx.post(
        f"{BASE_URL}/api/v1/process/commonforms/{document_id}/sync",
        timeout=120.0
    )
    
    if response.status_code != 200:
        print(f"❌ Sync process failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    data = response.json()
    print("✅ Processing completed!")
    return data


def print_results(result: dict):
    """Print processing results."""
    print("\n" + "=" * 60)
    print("📋 COMMONFORMS PROCESSING RESULTS")
    print("=" * 60)
    
    print(f"\nStatus: {result['status']}")
    
    if result.get('outputPdfUrl'):
        print(f"\n📄 Fillable PDF URL:")
        print(f"   {result['outputPdfUrl']}")
    
    fields = result.get('fields', [])
    print(f"\n🔍 Detected Fields: {len(fields)}")
    
    for i, field in enumerate(fields, 1):
        print(f"\n   Field {i}:")
        print(f"      ID: {field['id']}")
        print(f"      Type: {field['type']}")
        print(f"      Page: {field['page']}")
        print(f"      BBox: {field['bbox']}")
        if field.get('label'):
            print(f"      Label: {field['label']}")
    
    print("\n" + "=" * 60)
    print("✅ END-TO-END TEST PASSED")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Test CommonForms integration")
    parser.add_argument("--document-id", help="Existing document ID to process")
    parser.add_argument("--pdf", help="Path to PDF file to upload and process")
    parser.add_argument("--sync", action="store_true", help="Use synchronous processing")
    parser.add_argument("--base-url", default=BASE_URL, help="API base URL")
    
    args = parser.parse_args()
    
    global BASE_URL
    BASE_URL = args.base_url
    
    if not args.document_id and not args.pdf:
        print("❌ Please provide either --document-id or --pdf")
        parser.print_help()
        sys.exit(1)
    
    # Get document ID
    if args.pdf:
        document_id = upload_pdf(args.pdf)
    else:
        document_id = args.document_id
    
    # Process with CommonForms
    if args.sync:
        result = process_commonforms_sync(document_id)
    else:
        job_id = process_commonforms_async(document_id)
        result = poll_job_status(job_id)
    
    # Print results
    print_results(result)


if __name__ == "__main__":
    main()
