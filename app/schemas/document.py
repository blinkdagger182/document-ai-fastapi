from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.schemas.common import DocumentStatus, FieldType


class DocumentSummary(BaseModel):
    id: UUID
    fileName: str = Field(alias="file_name")
    mimeType: str = Field(alias="mime_type")
    status: DocumentStatus
    pageCount: Optional[int] = Field(None, alias="page_count")
    createdAt: datetime = Field(alias="created_at")
    updatedAt: datetime = Field(alias="updated_at")
    
    class Config:
        from_attributes = True
        populate_by_name = True


class InitUploadResponse(BaseModel):
    documentId: UUID
    document: DocumentSummary


class ProcessDocumentResponse(BaseModel):
    documentId: UUID
    status: DocumentStatus


class DownloadResponse(BaseModel):
    documentId: UUID
    filledPdfUrl: str
