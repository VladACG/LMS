from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.core.config import settings


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _fmt_google(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _parse_webinar_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _webinar_description_lines(lessons: list) -> list[str]:
    lines: list[str] = []
    for lesson in lessons:
        webinar_at = _parse_webinar_datetime(lesson.content_json.get('webinar_start_at'))
        webinar_url = lesson.content_json.get('webinar_join_url')
        if webinar_at is None and not webinar_url:
            continue
        segment = f'- {lesson.title}'
        if webinar_at is not None:
            segment += f' | {webinar_at.strftime("%Y-%m-%d %H:%M UTC")}'
        if webinar_url:
            segment += f' | {webinar_url}'
        lines.append(segment)
    return lines


def build_calendar_event_text(*, group, lessons: list) -> tuple[str, datetime, datetime, str]:
    start = _as_utc(group.start_date) or datetime.now(timezone.utc)
    end = _as_utc(group.end_date) or (start + timedelta(days=30))
    if end <= start:
        end = start + timedelta(days=1)

    title = f'Курс: {group.program.name} ({group.name})'
    description_lines = [
        f'Программа: {group.program.name}',
        f'Группа: {group.name}',
        f'Период: {start.date().isoformat()} — {end.date().isoformat()}',
    ]
    webinar_lines = _webinar_description_lines(lessons)
    if webinar_lines:
        description_lines.append('')
        description_lines.append('Вебинарные занятия:')
        description_lines.extend(webinar_lines)

    return title, start, end, '\n'.join(description_lines)


def build_google_calendar_link(*, group, lessons: list) -> str:
    title, start, end, description = build_calendar_event_text(group=group, lessons=lessons)
    params = {
        'action': 'TEMPLATE',
        'text': title,
        'dates': f'{_fmt_google(start)}/{_fmt_google(end)}',
        'details': description,
    }
    return f'https://calendar.google.com/calendar/render?{urlencode(params)}'


def build_yandex_calendar_link(*, group, lessons: list) -> str:
    title, start, end, description = build_calendar_event_text(group=group, lessons=lessons)
    params = {
        'name': title,
        'start': start.isoformat(),
        'end': end.isoformat(),
        'description': description,
    }
    return f'https://calendar.yandex.ru/?add-event&{urlencode(params)}'


def build_ics_content(*, group, lessons: list) -> str:
    title, start, end, description = build_calendar_event_text(group=group, lessons=lessons)
    uid = f'{group.id}@lms.local'
    dtstamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dtstart = start.strftime('%Y%m%dT%H%M%SZ')
    dtend = end.strftime('%Y%m%dT%H%M%SZ')
    safe_description = description.replace('\\', '\\\\').replace('\n', '\\n').replace(',', '\\,')
    safe_title = title.replace('\\', '\\\\').replace(',', '\\,')
    return (
        'BEGIN:VCALENDAR\r\n'
        'VERSION:2.0\r\n'
        'PRODID:-//LMS//Course Calendar//RU\r\n'
        'BEGIN:VEVENT\r\n'
        f'UID:{uid}\r\n'
        f'DTSTAMP:{dtstamp}\r\n'
        f'DTSTART:{dtstart}\r\n'
        f'DTEND:{dtend}\r\n'
        f'SUMMARY:{safe_title}\r\n'
        f'DESCRIPTION:{safe_description}\r\n'
        f'URL:{settings.app_base_url}/groups/{group.id}\r\n'
        'END:VEVENT\r\n'
        'END:VCALENDAR\r\n'
    )
