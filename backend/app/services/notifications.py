from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.entities import (
    AssignmentSubmission,
    CuratorGroupLink,
    Enrollment,
    Group,
    Lesson,
    LessonProgress,
    Module,
    Notification,
    TeacherGroupLink,
    User,
    UserRoleLink,
    UserStudentLink,
)
from app.models.enums import (
    AssignmentStatus,
    NotificationChannel,
    PaymentStatus,
    ProgramProgressStatus,
    ProgressStatus,
    UserRole,
)
from app.services.integration_errors import log_integration_error
from app.services.payments import mark_payment_overdue
from app.services.telegram import send_telegram_message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _notification_exists(db, event_key: str) -> bool:
    return db.execute(select(Notification.id).where(Notification.event_key == event_key)).first() is not None


def _create_db_notification(
    db,
    *,
    recipient_user_id: str,
    channel: NotificationChannel,
    subject: str,
    body: str,
    link_url: str | None,
    event_key: str | None,
) -> bool:
    if event_key and _notification_exists(db, event_key):
        return False
    db.add(
        Notification(
            recipient_user_id=recipient_user_id,
            channel=channel,
            subject=subject,
            body=body,
            link_url=link_url,
            event_key=event_key,
        )
    )
    return True


def create_notification(
    db,
    *,
    recipient_user_id: str,
    subject: str,
    body: str,
    link_url: str | None = None,
    channels: tuple[NotificationChannel, ...] = (NotificationChannel.in_app, NotificationChannel.email),
    event_key: str | None = None,
    duplicate_to_telegram: bool = True,
    fallback_to_email_if_no_telegram: bool = True,
    fallback_to_email_if_telegram_error: bool = True,
) -> int:
    created = 0
    user = db.get(User, recipient_user_id)
    requested_channels = list(dict.fromkeys(channels))
    created_channels: set[NotificationChannel] = set()

    # All stage-4 notifications are duplicated to Telegram when account is linked.
    if duplicate_to_telegram and NotificationChannel.telegram not in requested_channels:
        requested_channels.append(NotificationChannel.telegram)

    for channel in requested_channels:
        resolved_key = f'{event_key}:{channel.value}' if event_key else None

        if channel == NotificationChannel.telegram:
            if user is None or not user.telegram_chat_id:
                # Fallback to email when Telegram is not linked.
                if fallback_to_email_if_no_telegram and NotificationChannel.email not in created_channels:
                    fallback_key = f'{event_key}:email-fallback' if event_key else None
                    if _create_db_notification(
                        db,
                        recipient_user_id=recipient_user_id,
                        channel=NotificationChannel.email,
                        subject=subject,
                        body=body,
                        link_url=link_url,
                        event_key=fallback_key,
                    ):
                        created += 1
                        created_channels.add(NotificationChannel.email)
                continue

            if resolved_key and _notification_exists(db, resolved_key):
                continue

            try:
                send_telegram_message(
                    chat_id=user.telegram_chat_id,
                    subject=subject,
                    body=body,
                    link_url=link_url,
                )
                if _create_db_notification(
                    db,
                    recipient_user_id=recipient_user_id,
                    channel=NotificationChannel.telegram,
                    subject=subject,
                    body=body,
                    link_url=link_url,
                    event_key=resolved_key,
                ):
                    created += 1
                    created_channels.add(NotificationChannel.telegram)
            except Exception as exc:  # pragma: no cover - depends on external telegram API
                log_integration_error(
                    db,
                    service='telegram',
                    operation='send_message',
                    error_text=str(exc),
                    context={'recipient_user_id': recipient_user_id, 'subject': subject},
                    user_id=recipient_user_id,
                )
                if fallback_to_email_if_telegram_error and NotificationChannel.email not in created_channels:
                    fallback_key = f'{event_key}:email-fallback' if event_key else None
                    if _create_db_notification(
                        db,
                        recipient_user_id=recipient_user_id,
                        channel=NotificationChannel.email,
                        subject=subject,
                        body=body,
                        link_url=link_url,
                        event_key=fallback_key,
                    ):
                        created += 1
                        created_channels.add(NotificationChannel.email)
            continue

        if _create_db_notification(
            db,
            recipient_user_id=recipient_user_id,
            channel=channel,
            subject=subject,
            body=body,
            link_url=link_url,
            event_key=resolved_key,
        ):
            created += 1
            created_channels.add(channel)

    return created


def _program_total_lessons(db) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    rows = db.execute(select(Module.program_id).join(Lesson, Lesson.module_id == Module.id)).all()
    for (program_id,) in rows:
        totals[program_id] += 1
    return dict(totals)


def _ordered_program_lessons(db, program_id: str) -> list[str]:
    rows = db.execute(
        select(Lesson.id)
        .join(Module, Module.id == Lesson.module_id)
        .where(Module.program_id == program_id)
        .order_by(Module.order_index.asc(), Lesson.order_index.asc())
    ).all()
    return [lesson_id for (lesson_id,) in rows]


def _current_lesson_id_for_enrollment(db, enrollment: Enrollment) -> str | None:
    ordered_ids = _ordered_program_lessons(db, enrollment.group.program_id)
    if not ordered_ids:
        return None

    progress_rows = db.execute(
        select(LessonProgress.lesson_id, LessonProgress.status).where(LessonProgress.enrollment_id == enrollment.id)
    ).all()
    status_map = {lesson_id: status for lesson_id, status in progress_rows}

    if enrollment.group.program.strict_order:
        for lesson_id in ordered_ids:
            if status_map.get(lesson_id) != ProgressStatus.completed:
                return lesson_id
        return ordered_ids[-1]

    in_progress_ids = [lesson_id for lesson_id in ordered_ids if status_map.get(lesson_id) == ProgressStatus.in_progress]
    if in_progress_ids:
        return in_progress_ids[0]

    for lesson_id in ordered_ids:
        if status_map.get(lesson_id) != ProgressStatus.completed:
            return lesson_id

    return ordered_ids[-1]


def _completed_lessons_by_enrollment(db, enrollment_ids: list[str]) -> dict[str, int]:
    if not enrollment_ids:
        return {}
    completed: dict[str, int] = defaultdict(int)
    rows = db.execute(
        select(LessonProgress.enrollment_id).where(
            LessonProgress.enrollment_id.in_(enrollment_ids),
            LessonProgress.status == ProgressStatus.completed,
        )
    ).all()
    for (enrollment_id,) in rows:
        completed[enrollment_id] += 1
    return dict(completed)


def _notify_overdue_payments(db, *, now: datetime) -> int:
    created_total = 0
    pending = db.execute(
        select(Enrollment).where(Enrollment.payment_status == PaymentStatus.pending)
    ).scalars().all()
    for enrollment in pending:
        due_at = _as_utc(enrollment.payment_due_at)
        if due_at is None or due_at > now:
            continue

        mark_payment_overdue(enrollment=enrollment)

        student_user = db.execute(
            select(User)
            .join(UserStudentLink, UserStudentLink.user_id == User.id)
            .where(UserStudentLink.student_id == enrollment.student_id)
        ).scalar_one_or_none()
        if student_user:
            created_total += create_notification(
                db,
                recipient_user_id=student_user.id,
                subject='Оплата просрочена',
                body='Доступ к материалам закрыт до подтверждения оплаты курса.',
                link_url=enrollment.payment_link,
                event_key=f'payment-overdue-student-{enrollment.id}-{now.date().isoformat()}',
                channels=(NotificationChannel.email, NotificationChannel.in_app),
            )

        admin_ids = db.execute(
            select(UserRoleLink.user_id).where(UserRoleLink.role == UserRole.admin)
        ).all()
        for (admin_id,) in admin_ids:
            created_total += create_notification(
                db,
                recipient_user_id=admin_id,
                subject='Просроченная оплата по слушателю',
                body=f'{enrollment.student.full_name} не оплатил курс в течение 3 дней.',
                link_url=f'/groups/{enrollment.group_id}/progress',
                event_key=f'payment-overdue-admin-{admin_id}-{enrollment.id}-{now.date().isoformat()}',
                channels=(NotificationChannel.in_app, NotificationChannel.email),
            )
    return created_total


def run_scheduled_notifications(db, *, now: datetime | None = None) -> int:
    now = now or _utcnow()
    created_total = 0

    created_total += _notify_overdue_payments(db, now=now)

    # Student inactivity > 3 days.
    inactive_students = db.execute(
        select(User)
        .join(UserRoleLink, UserRoleLink.user_id == User.id)
        .where(UserRoleLink.role == UserRole.student)
    ).scalars().all()

    for user in inactive_students:
        last_login_at = _as_utc(user.last_login_at)
        if last_login_at and last_login_at > now - timedelta(days=3):
            continue
        if not user.student_link:
            continue

        enrollments = db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == user.student_link.student_id)
            .order_by(Enrollment.enrolled_at.asc())
        ).scalars().all()
        if not enrollments:
            continue
        enrollment = next(
            (item for item in enrollments if item.program_status != ProgramProgressStatus.completed),
            enrollments[0],
        )
        lesson_id = _current_lesson_id_for_enrollment(db, enrollment) or ''
        created_total += create_notification(
            db,
            recipient_user_id=user.id,
            subject='Напоминание о прохождении',
            body='Вы не заходили в систему более 3 дней. Продолжите обучение с текущего урока.',
            link_url=f'/groups/{enrollment.group_id}/lessons/{lesson_id}' if lesson_id else None,
            event_key=f'student-inactive-3d-{user.id}-{enrollment.id}-{now.date().isoformat()}',
        )

    # Teacher reminder for assignments waiting > 2 days.
    stale_submissions = db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.status == AssignmentStatus.submitted)
    ).scalars().all()

    for submission in stale_submissions:
        submitted_at = _as_utc(submission.submitted_at)
        if submitted_at is None or submitted_at > now - timedelta(days=2):
            continue
        teacher_ids = db.execute(
            select(TeacherGroupLink.user_id).where(TeacherGroupLink.group_id == submission.enrollment.group_id)
        ).all()
        for (teacher_id,) in teacher_ids:
            created_total += create_notification(
                db,
                recipient_user_id=teacher_id,
                subject='Задание ожидает проверки > 2 дней',
                body=(
                    f'Слушатель: {submission.enrollment.student.full_name}. '
                    f'Урок: {submission.lesson.title}. '
                    'Проверьте задание, чтобы не задерживать прогресс.'
                ),
                link_url=f'/assignments/{submission.id}',
                event_key=f'teacher-stale-assignment-{submission.id}-{teacher_id}-{now.date().isoformat()}',
                channels=(NotificationChannel.in_app,),
            )

    # Curator alerts: lagging >20% and inactive >5 days.
    totals = _program_total_lessons(db)
    enrollments = db.execute(select(Enrollment)).scalars().all()
    completed_map = _completed_lessons_by_enrollment(db, [item.id for item in enrollments])

    student_last_login: dict[str, datetime | None] = {}
    student_logins = db.execute(
        select(UserStudentLink.student_id, User.last_login_at).join(User, User.id == UserStudentLink.user_id)
    ).all()
    for student_id, last_login in student_logins:
        student_last_login[student_id] = last_login

    curators = db.execute(select(CuratorGroupLink)).scalars().all()
    for link in curators:
        for enrollment in [item for item in enrollments if item.group_id == link.group_id]:
            total_lessons = totals.get(enrollment.group.program_id, 0)
            completed = completed_map.get(enrollment.id, 0)
            progress = (completed / total_lessons * 100) if total_lessons else 0.0

            start_date = _as_utc(enrollment.group.start_date)
            end_date = _as_utc(enrollment.group.end_date)
            if start_date and end_date and end_date > start_date:
                duration = (end_date - start_date).total_seconds()
                elapsed = max(0.0, min((now - start_date).total_seconds(), duration))
                expected = (elapsed / duration) * 100 if duration > 0 else 0.0
                if expected - progress > 20:
                    days_to_end = (end_date.date() - now.date()).days
                    created_total += create_notification(
                        db,
                        recipient_user_id=link.user_id,
                        subject='Слушатель отстаёт от графика',
                        body=f'{enrollment.student.full_name}: прогресс {round(progress, 2)}%, до конца курса {days_to_end} дн.',
                        link_url=f'/groups/{enrollment.group_id}/progress',
                        event_key=f'curator-lag-{link.user_id}-{enrollment.id}-{now.date().isoformat()}',
                        channels=(NotificationChannel.telegram,),
                        duplicate_to_telegram=False,
                        fallback_to_email_if_no_telegram=False,
                    )

            last_login = _as_utc(student_last_login.get(enrollment.student_id))
            if last_login is None or last_login <= now - timedelta(days=5):
                created_total += create_notification(
                    db,
                    recipient_user_id=link.user_id,
                    subject='Слушатель не заходил более 5 дней',
                    body=f'{enrollment.student.full_name} давно не заходил в LMS.',
                    link_url=f'/groups/{enrollment.group_id}/progress',
                    event_key=f'curator-inactive-{link.user_id}-{enrollment.id}-{now.date().isoformat()}',
                    channels=(NotificationChannel.in_app,),
                )

    # Weekly customer summary.
    week_key = now.strftime('%G-W%V')
    customers = db.execute(
        select(User)
        .join(UserRoleLink, UserRoleLink.user_id == User.id)
        .where(UserRoleLink.role == UserRole.customer)
    ).scalars().all()
    for customer in customers:
        related_enrollments = [
            enrollment
            for enrollment in enrollments
            if any(link.student_id == enrollment.student_id for link in customer.customer_students)
        ]
        if not related_enrollments:
            continue

        completed_count = sum(1 for item in related_enrollments if item.program_status == ProgramProgressStatus.completed)
        in_progress_count = sum(1 for item in related_enrollments if item.program_status == ProgramProgressStatus.in_progress)
        not_started_count = sum(1 for item in related_enrollments if item.program_status == ProgramProgressStatus.not_started)

        created_total += create_notification(
            db,
            recipient_user_id=customer.id,
            subject='Еженедельная сводка по слушателям',
            body=f'Завершили: {completed_count}, в процессе: {in_progress_count}, не начали: {not_started_count}.',
            link_url='/progress',
            event_key=f'customer-weekly-{customer.id}-{week_key}',
            channels=(NotificationChannel.in_app, NotificationChannel.email),
        )

    return created_total
