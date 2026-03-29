from __future__ import annotations

from app.models.entities import IntegrationErrorLog


def log_integration_error(
    db,
    *,
    service: str,
    operation: str,
    error_text: str,
    context: dict | None = None,
    user_id: str | None = None,
) -> IntegrationErrorLog:
    item = IntegrationErrorLog(
        service=service,
        operation=operation,
        error_text=error_text[:4000],
        context_json=context,
        user_id=user_id,
    )
    db.add(item)
    return item
