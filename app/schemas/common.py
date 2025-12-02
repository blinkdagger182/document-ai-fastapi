from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum


class DocumentStatus(str, Enum):
    imported = "imported"
    processing = "processing"
    ready = "ready"
    filling = "filling"
    filled = "filled"
    failed = "failed"


class FieldType(str, Enum):
    text = "text"
    multiline = "multiline"
    checkbox = "checkbox"
    date = "date"
    number = "number"
    signature = "signature"
    unknown = "unknown"


class FieldSource(str, Enum):
    manual = "manual"
    autofill = "autofill"
    ai = "ai"


class HealthResponse(BaseModel):
    status: str = "ok"
