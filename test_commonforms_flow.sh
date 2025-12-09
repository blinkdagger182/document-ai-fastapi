#!/bin/bash

API_URL="https://documentai-api-824241800977.us-central1.run.app"

echo "Testing CommonForms Flow..."
echo "=============================="

# Test 1: Health check
echo -e "\n1. Health Check"
curl -s "$API_URL/api/v1/health" | python3 -m json.tool

# Test 2: Upload document
echo -e "\n2. Upload Document"
cd "$(dirname "$0")/.." || exit 1
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/documents/init-upload" \
  -F "file=@test_form.pdf")

echo "$UPLOAD_RESPONSE" | python3 -m json.tool

DOCUMENT_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['documentId'])")

if [ -z "$DOCUMENT_ID" ]; then
  echo "Failed to upload document"
  exit 1
fi

echo "Document ID: $DOCUMENT_ID"

# Test 3: Process with CommonForms
echo -e "\n3. Process with CommonForms"
PROCESS_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/process/commonforms/$DOCUMENT_ID")
echo "$PROCESS_RESPONSE" | python3 -m json.tool

JOB_ID=$(echo "$PROCESS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['jobId'])" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
  echo "Failed to start processing"
  exit 1
fi

echo "Job ID: $JOB_ID"

# Test 4: Poll status
echo -e "\n4. Polling Status (max 60s)"
for i in {1..12}; do
  echo "Attempt $i/12..."
  STATUS_RESPONSE=$(curl -s "$API_URL/api/v1/process/status/$JOB_ID")
  echo "$STATUS_RESPONSE" | python3 -m json.tool
  
  STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
  
  if [ "$STATUS" = "completed" ]; then
    echo -e "\n✅ Processing completed!"
    exit 0
  elif [ "$STATUS" = "failed" ]; then
    echo -e "\n❌ Processing failed!"
    exit 1
  fi
  
  sleep 5
done

echo -e "\n⏱️ Timeout waiting for processing"
exit 1
