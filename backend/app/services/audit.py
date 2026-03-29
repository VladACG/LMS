from __future__ import annotations

from app.models.entities import AuditEvent


def log_audit(
    db,
    *,
    actor_user_id: str | None,
    event_type: str,
    entity_type: str,
    entity_id: str,
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        from_status=from_status,
        to_status=to_status,
        payload_json=payload,
    )
    db.add(event)
    return event
