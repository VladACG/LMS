from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.models.enums import PaymentStatus
from app.services.integration_errors import log_integration_error


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_payment_link(
    db,
    *,
    enrollment_id: str,
    amount: float,
    description: str,
    user_id: str | None = None,
) -> str:
    if settings.yookassa_shop_id and settings.yookassa_secret_key:
        payload = {
            'amount': {'value': f'{amount:.2f}', 'currency': 'RUB'},
            'capture': True,
            'confirmation': {'type': 'redirect', 'return_url': settings.yookassa_return_url},
            'description': description,
            'metadata': {'enrollment_id': enrollment_id},
        }
        try:
            response = httpx.post(
                'https://api.yookassa.ru/v3/payments',
                json=payload,
                headers={'Idempotence-Key': str(uuid.uuid4())},
                auth=(settings.yookassa_shop_id, settings.yookassa_secret_key),
                timeout=12.0,
            )
            response.raise_for_status()
            body = response.json()
            url = body.get('confirmation', {}).get('confirmation_url')
            if url:
                return str(url)
        except Exception as exc:  # pragma: no cover - external dependency path
            log_integration_error(
                db,
                service='yookassa',
                operation='create_payment',
                error_text=str(exc),
                context={'enrollment_id': enrollment_id},
                user_id=user_id,
            )

    return f'{settings.app_base_url}/api/payments/mock/{enrollment_id}'


def apply_paid_program_on_enrollment(db, *, enrollment, actor_user_id: str | None) -> None:
    if not enrollment.group.program.is_paid:
        enrollment.payment_status = PaymentStatus.not_required
        enrollment.payment_link = None
        enrollment.payment_due_at = None
        enrollment.payment_provider = None
        return

    price = enrollment.group.program.price_amount or 0.0
    enrollment.payment_status = PaymentStatus.pending
    enrollment.payment_due_at = _utcnow() + timedelta(days=3)
    enrollment.payment_provider = 'yookassa'
    enrollment.payment_link = create_payment_link(
        db,
        enrollment_id=enrollment.id,
        amount=price,
        description=f'Оплата курса {enrollment.group.program.name}',
        user_id=actor_user_id,
    )


def mark_payment_paid(*, enrollment, external_id: str | None = None) -> None:
    enrollment.payment_status = PaymentStatus.paid
    enrollment.payment_confirmed_at = _utcnow()
    if external_id:
        enrollment.payment_external_id = external_id


def mark_payment_overdue(*, enrollment) -> None:
    if enrollment.payment_status == PaymentStatus.pending:
        enrollment.payment_status = PaymentStatus.overdue
