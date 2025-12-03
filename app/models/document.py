from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class DocumentStatus(str, enum.Enum):
    imported = "imported"
    processing = "processing"
    ready = "ready"
    filling = "filling"
    filled = "filled"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    file_name = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    storage_key_original = Column(String, nullable=False)
    storage_key_filled = Column(String, nullable=True)
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.imported, nullable=False, index=True)
    page_count = Column(Integer, nullable=True)
    hash_fingerprint = Column(String, nullable=True, index=True)
    acroform = Column(Boolean, default=False, nullable=False)  # True if PDF has AcroForm fields
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="documents")
    field_regions = relationship("FieldRegion", back_populates="document", cascade="all, delete-orphan")
    field_values = relationship("FieldValue", back_populates="document", cascade="all, delete-orphan")
