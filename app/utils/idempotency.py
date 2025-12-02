from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.document import Document


def find_duplicate_document(db: Session, user_id: UUID, file_hash: str) -> Optional[Document]:
    """Find existing document with same hash for template reuse"""
    return db.query(Document).filter(
        Document.user_id == user_id,
        Document.hash_fingerprint == file_hash
    ).first()
