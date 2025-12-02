import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data


@patch("app.routers.documents.get_storage_service")
def test_upload_document(mock_storage, client, test_user):
    """Test document upload"""
    # Mock storage service
    mock_storage_instance = MagicMock()
    mock_storage_instance.upload_file = MagicMock(return_value="gs://bucket/file")
    mock_storage.return_value = mock_storage_instance
    
    # Create a fake PDF file
    pdf_content = b"%PDF-1.4\n%fake pdf content"
    files = {"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")}
    
    response = client.post("/api/v1/documents/init-upload", files=files)
    
    assert response.status_code == 201
    data = response.json()
    assert "documentId" in data
    assert "document" in data
    assert data["document"]["fileName"] == "test.pdf"
    assert data["document"]["status"] == "imported"


@patch("app.routers.documents.run_ocr")
def test_process_document(mock_run_ocr, client, test_user, db_session):
    """Test document processing"""
    from app.models.document import Document, DocumentStatus
    
    # Create a document
    doc = Document(
        user_id=test_user.id,
        file_name="test.pdf",
        mime_type="application/pdf",
        storage_key_original="test/key",
        status=DocumentStatus.imported
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    
    # Mock Celery task
    mock_run_ocr.delay = MagicMock()
    
    response = client.post(f"/api/v1/documents/{doc.id}/process")
    
    assert response.status_code == 200
    data = response.json()
    assert data["documentId"] == str(doc.id)
    assert data["status"] == "processing"


def test_get_document(client, test_user, db_session):
    """Test getting document details"""
    from app.models.document import Document, DocumentStatus
    
    # Create a document
    doc = Document(
        user_id=test_user.id,
        file_name="test.pdf",
        mime_type="application/pdf",
        storage_key_original="test/key",
        status=DocumentStatus.ready,
        page_count=1
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    
    response = client.get(f"/api/v1/documents/{doc.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert "document" in data
    assert "components" in data
    assert "fieldMap" in data
    assert data["document"]["id"] == str(doc.id)


def test_submit_values(client, test_user, db_session):
    """Test submitting field values"""
    from app.models.document import Document, DocumentStatus
    from app.models.field import FieldRegion, FieldType
    
    # Create document and field region
    doc = Document(
        user_id=test_user.id,
        file_name="test.pdf",
        mime_type="application/pdf",
        storage_key_original="test/key",
        status=DocumentStatus.ready
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    
    field = FieldRegion(
        document_id=doc.id,
        page_index=0,
        x=0.1,
        y=0.1,
        width=0.2,
        height=0.05,
        field_type=FieldType.text,
        label="Name",
        confidence=0.95
    )
    db_session.add(field)
    db_session.commit()
    db_session.refresh(field)
    
    # Submit values
    payload = {
        "values": [
            {
                "fieldRegionId": str(field.id),
                "value": "John Doe",
                "source": "manual"
            }
        ]
    }
    
    response = client.post(f"/api/v1/documents/{doc.id}/values", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["documentId"] == str(doc.id)
    assert data["status"] == "filling"
