from __future__ import annotations

import secrets
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.models.entities import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_telegram_link_token(user: User) -> str:
    if user.telegram_link_token:
        return user.telegram_link_token
    user.telegram_link_token = secrets.token_urlsafe(24)
    return user.telegram_link_token


def telegram_invite_url(user: User) -> str:
    token = ensure_telegram_link_token(user)
    bot_name = settings.telegram_bot_username or 'your_lms_bot'
    return f'https://t.me/{bot_name}?start={token}'


def link_telegram_account(*, user: User, chat_id: str, username: str | None = None) -> None:
    user.telegram_chat_id = chat_id
    user.telegram_username = username
    user.telegram_linked_at = _utcnow()
    user.telegram_link_token = None


def send_telegram_message(*, chat_id: str, subject: str, body: str, link_url: str | None = None) -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError('telegram_bot_token is not configured')

    text = f'{subject}\n\n{body}'
    if link_url:
        text += f'\n\n{link_url}'

    response = httpx.post(
        f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage',
        json={'chat_id': chat_id, 'text': text[:4000]},
        timeout=10.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f'telegram send failed: {response.status_code} {response.text[:500]}')
