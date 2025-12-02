from sqlalchemy.orm import Session
from uuid import UUID
from app.models.usage import UsageEvent, EventType


class UsageTracker:
    @staticmethod
    def log_event(db: Session, user_id: UUID, event_type: EventType, value: int = 1) -> UsageEvent:
        """Log a usage event"""
        event = UsageEvent(
            user_id=user_id,
            event_type=event_type,
            value=value
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
