from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from uuid import UUID
from app.schemas.common import FieldType, FieldSource


class FieldComponent(BaseModel):
    id: UUID
    fieldId: UUID
    type: FieldType
    label: str
    placeholder: Optional[str] = None
    pageIndex: int
    defaultValue: Optional[str] = None
    options: Optional[List[str]] = None


class FieldRegionDTO(BaseModel):
    id: UUID
    pageIndex: int
    x: float
    y: float
    width: float
    height: float
    fieldType: FieldType
    label: str
    confidence: float


class FieldMapDTO(BaseModel):
    components: Dict[str, FieldRegionDTO]


class DocumentDetailResponse(BaseModel):
    document: "DocumentSummary"
    components: List[FieldComponent]
    fieldMap: Dict[str, FieldRegionDTO]


class FieldValueInput(BaseModel):
    fieldRegionId: UUID
    value: str
    source: FieldSource = FieldSource.manual


class SubmitValuesRequest(BaseModel):
    values: List[FieldValueInput]


class SubmitValuesResponse(BaseModel):
    documentId: UUID
    status: str


from app.schemas.document import DocumentSummary
DocumentDetailResponse.model_rebuild()
