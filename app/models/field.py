from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class FieldType(str, enum.Enum):
    text = "text"
    multiline = "multiline"
    checkbox = "checkbox"
    date = "date"
    number = "number"
    signature = "signature"
    unknown = "unknown"


class FieldSource(str, enum.Enum):
    manual = "manual"
    autofill = "autofill"
    ai = "ai"


class FieldRegion(Base):
    __tablename__ = "field_regions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    page_index = Column(Integer, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    field_type = Column(SQLEnum(FieldType), default=FieldType.unknown, nullable=False)
    label = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    template_key = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="field_regions")
    field_values = relationship("FieldValue", back_populates="field_region")


class FieldValue(Base):
    __tablename__ = "field_values"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    field_region_id = Column(UUID(as_uuid=True), ForeignKey("field_regions.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    value = Column(Text, nullable=False)
    source = Column(SQLEnum(FieldSource), default=FieldSource.manual, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="field_values")
    field_region = relationship("FieldRegion", back_populates="field_values")
    user = relationship("User", back_populates="field_values")
