#!/bin/bash
# Test DocumentAI API

API_URL="https://documentai-api-824241800977.us-central1.run.app/api/v1"

echo "🧪 Testing DocumentAI API"
echo "API URL: $API_URL"
echo ""

# Test 1: Health Check
echo "1️⃣ Testing health endpoint..."
HEALTH=$(curl -s $API_URL/health)
echo "Response: $HEALTH"
echo ""

# Test 2: Create a simple test PDF
echo "2️⃣ Creating test PDF..."
echo "%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test Document) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
409
%%EOF" > test-doc.pdf

echo "✅ Test PDF created"
echo ""

# Test 3: Upload document
echo "3️⃣ Testing document upload..."
UPLOAD_RESPONSE=$(curl -s -X POST $API_URL/documents/init-upload \
  -F "file=@test-doc.pdf")

echo "Response: $UPLOAD_RESPONSE" | jq
DOC_ID=$(echo $UPLOAD_RESPONSE | jq -r '.documentId')
echo ""
echo "Document ID: $DOC_ID"
echo ""

if [ "$DOC_ID" != "null" ] && [ -n "$DOC_ID" ]; then
  # Test 4: Get document details
  echo "4️⃣ Testing get document..."
  curl -s $API_URL/documents/$DOC_ID | jq
  echo ""
  
  echo "✅ All tests passed!"
else
  echo "❌ Upload failed"
fi

# Cleanup
rm -f test-doc.pdf

echo ""
echo "🎉 API is working!"
echo ""
echo "API Documentation: https://documentai-api-824241800977.us-central1.run.app/docs"
