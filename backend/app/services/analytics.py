from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    AssignmentSubmission,
    Enrollment,
    Group,
    IntegrationErrorLog,
    LessonProgress,
    Module,
    ReminderLog,
    StudentQuestion,
    TeacherGroupLink,
    TestAttempt,
    User,
    UserStudentLink,
)
from app.models.enums import AssignmentStatus, ProgressStatus

PeriodPreset = Literal['7d', '30d', '3m', 'custom']


@dataclass
class PeriodWindow:
    start: datetime
    end: datetime
    previous_start: datetime
    previous_end: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_period_window(
    *,
    period: PeriodPreset,
    date_from: datetime | None,
    date_to: datetime | None,
) -> PeriodWindow:
    now = _utcnow()
    if period == '7d':
        start = now - timedelta(days=7)
        end = now
    elif period == '30d':
        start = now - timedelta(days=30)
        end = now
    elif period == '3m':
        start = now - timedelta(days=90)
        end = now
    else:
        if date_from is None or date_to is None:
            raise ValueError('date_from and date_to are required for custom period')
        start = _as_utc(date_from) or now
        end = _as_utc(date_to) or now
        if end < start:
            start, end = end, start

    duration = end - start
    if duration.total_seconds() <= 0:
        duration = timedelta(days=1)
    previous_end = start
    previous_start = start - duration
    return PeriodWindow(start=start, end=end, previous_start=previous_start, previous_end=previous_end)


def _in_range(value: datetime | None, *, start: datetime, end: datetime) -> bool:
    dt = _as_utc(value)
    if dt is None:
        return False
    return start <= dt <= end


def _month_key(value: datetime) -> str:
    dt = _as_utc(value) or value
    return f'{dt.year:04d}-{dt.month:02d}'


def _week_key(value: datetime) -> str:
    dt = _as_utc(value) or value
    iso = dt.isocalendar()
    return f'{iso.year:04d}-W{iso.week:02d}'


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _round2(value: float) -> float:
    return round(value, 2)


def _build_program_structure(db: Session, program_ids: list[str]) -> dict[str, dict]:
    structure: dict[str, dict] = {
        program_id: {'total_lessons': 0, 'ordered_lessons': [], 'modules': []}
        for program_id in program_ids
    }
    if not program_ids:
        return structure

    modules = db.execute(
        select(Module)
        .where(Module.program_id.in_(program_ids))
        .options(selectinload(Module.lessons))
    ).scalars().all()

    for module in modules:
        lessons = sorted(module.lessons, key=lambda item: item.order_index)
        module_row = {
            'module_id': module.id,
            'module_title': module.title,
            'module_order': module.order_index,
            'lesson_ids': [lesson.id for lesson in lessons],
            'lessons': [
                {
                    'lesson_id': lesson.id,
                    'lesson_title': lesson.title,
                    'lesson_type': lesson.type.value,
                    'lesson_order': lesson.order_index,
                }
                for lesson in lessons
            ],
        }
        bucket = structure.setdefault(
            module.program_id,
            {'total_lessons': 0, 'ordered_lessons': [], 'modules': []},
        )
        bucket['modules'].append(module_row)
        for lesson in lessons:
            bucket['ordered_lessons'].append(
                {
                    'lesson_id': lesson.id,
                    'lesson_title': lesson.title,
                    'lesson_type': lesson.type.value,
                    'module_title': module.title,
                    'module_order': module.order_index,
                    'lesson_order': lesson.order_index,
                }
            )
            bucket['total_lessons'] += 1

    for program_id, bucket in structure.items():
        bucket['modules'].sort(key=lambda item: item['module_order'])
        bucket['ordered_lessons'].sort(key=lambda item: (item['module_order'], item['lesson_order']))
        bucket['total_lessons'] = int(bucket.get('total_lessons', 0))
        if not bucket['modules']:
            bucket['modules'] = []
            bucket['ordered_lessons'] = []
            bucket['total_lessons'] = 0
        structure[program_id] = bucket
    return structure


def _load_enrollments(
    db: Session,
    *,
    group_ids: set[str] | None = None,
    student_ids: set[str] | None = None,
) -> list[Enrollment]:
    query = (
        select(Enrollment)
        .options(
            selectinload(Enrollment.student),
            selectinload(Enrollment.group).selectinload(Group.program),
            selectinload(Enrollment.progress_items),
            selectinload(Enrollment.test_attempts),
            selectinload(Enrollment.assignment_submissions),
        )
    )
    if group_ids is not None:
        if not group_ids:
            return []
        query = query.where(Enrollment.group_id.in_(group_ids))
    if student_ids is not None:
        if not student_ids:
            return []
        query = query.where(Enrollment.student_id.in_(student_ids))
    return db.execute(query).scalars().all()


def _student_last_login_map(db: Session, student_ids: set[str]) -> dict[str, datetime | None]:
    if not student_ids:
        return {}
    rows = db.execute(
        select(UserStudentLink.student_id, User.last_login_at)
        .join(User, User.id == UserStudentLink.user_id)
        .where(UserStudentLink.student_id.in_(student_ids))
    ).all()
    return {student_id: _as_utc(last_login_at) for student_id, last_login_at in rows}


def _enrollment_metrics(enrollment: Enrollment, program_structure: dict[str, dict]) -> dict:
    bucket = program_structure.get(enrollment.group.program_id, {'total_lessons': 0, 'ordered_lessons': []})
    total_lessons = int(bucket.get('total_lessons', 0))
    progress_items = enrollment.progress_items or []
    completed = sum(1 for item in progress_items if item.status == ProgressStatus.completed)
    progress_percent = _round2(_safe_divide(completed, total_lessons) * 100) if total_lessons > 0 else 0.0
    scores = [float(item.score) for item in progress_items if item.score is not None]
    avg_score = _round2(sum(scores) / len(scores)) if scores else 0.0

    last_activity = None
    for item in progress_items:
        for candidate in (_as_utc(item.completed_at), _as_utc(item.last_opened_at)):
            if candidate and (last_activity is None or candidate > last_activity):
                last_activity = candidate

    current_lesson = None
    progress_by_lesson = {item.lesson_id: item for item in progress_items}
    for lesson_ref in bucket.get('ordered_lessons', []):
        progress = progress_by_lesson.get(lesson_ref['lesson_id'])
        status = progress.status if progress else ProgressStatus.not_started
        if status != ProgressStatus.completed:
            current_lesson = lesson_ref['lesson_title']
            break
    if current_lesson is None and bucket.get('ordered_lessons'):
        current_lesson = 'Курс завершён'

    return {
        'total_lessons': total_lessons,
        'completed_lessons': completed,
        'progress_percent': progress_percent,
        'avg_score': avg_score,
        'last_activity': last_activity,
        'current_lesson': current_lesson,
    }


def executive_dashboard(db: Session, window: PeriodWindow) -> dict:
    enrollments = _load_enrollments(db)
    programs: dict[str, dict] = {}
    groups: dict[str, Group] = {}
    for enrollment in enrollments:
        programs[enrollment.group.program_id] = {
            'id': enrollment.group.program.id,
            'name': enrollment.group.program.name,
        }
        groups[enrollment.group.id] = enrollment.group

    program_structure = _build_program_structure(db, list(programs.keys()))
    metrics_by_enrollment = {
        enrollment.id: _enrollment_metrics(enrollment, program_structure)
        for enrollment in enrollments
    }

    active_learners = len(
        {
            enrollment.student_id
            for enrollment in enrollments
            if enrollment.program_status.value in {'not_started', 'in_progress'}
        }
    )

    by_program: dict[str, dict] = defaultdict(
        lambda: {
            'program_id': '',
            'program_name': '',
            'enrolled': 0,
            'completed': 0,
            'dropped': 0,
            'score_sum': 0.0,
            'score_count': 0,
        }
    )
    now = _utcnow()
    for enrollment in enrollments:
        pid = enrollment.group.program_id
        row = by_program[pid]
        row['program_id'] = pid
        row['program_name'] = enrollment.group.program.name
        row['enrolled'] += 1
        if enrollment.program_status.value == 'completed':
            row['completed'] += 1
        if enrollment.group.end_date and _as_utc(enrollment.group.end_date) and _as_utc(enrollment.group.end_date) < now:
            if enrollment.program_status.value != 'completed':
                row['dropped'] += 1
        score = float(metrics_by_enrollment[enrollment.id]['avg_score'])
        row['score_sum'] += score
        row['score_count'] += 1 if score > 0 else 0

    program_completion = []
    top_students = []
    top_scores = []
    for row in by_program.values():
        enrolled = int(row['enrolled'])
        completed = int(row['completed'])
        average_score = _round2(_safe_divide(float(row['score_sum']), float(row['score_count'])))
        completion_percent = _round2(_safe_divide(completed, enrolled) * 100)
        payload = {
            'program_id': row['program_id'],
            'program_name': row['program_name'],
            'enrolled': enrolled,
            'completed': completed,
            'dropped': int(row['dropped']),
            'completion_percent': completion_percent,
            'average_score': average_score,
        }
        program_completion.append(payload)
        top_students.append({'program_id': row['program_id'], 'program_name': row['program_name'], 'value': enrolled})
        top_scores.append({'program_id': row['program_id'], 'program_name': row['program_name'], 'value': average_score})

    program_completion.sort(key=lambda item: item['program_name'])
    top_students.sort(key=lambda item: item['value'], reverse=True)
    top_scores.sort(key=lambda item: item['value'], reverse=True)

    enrollment_months: dict[str, int] = defaultdict(int)
    for enrollment in enrollments:
        if _in_range(enrollment.enrolled_at, start=window.start, end=window.end):
            enrollment_months[_month_key(_as_utc(enrollment.enrolled_at) or enrollment.enrolled_at)] += 1
    enrollments_by_month = [
        {'period': month, 'value': value}
        for month, value in sorted(enrollment_months.items())
    ]

    revenue_months: dict[str, float] = defaultdict(float)
    for enrollment in enrollments:
        confirmed_at = _as_utc(enrollment.payment_confirmed_at)
        if not _in_range(confirmed_at, start=window.start, end=window.end):
            continue
        if not enrollment.group.program.is_paid:
            continue
        revenue_months[_month_key(confirmed_at)] += float(enrollment.group.program.price_amount or 0)
    revenue_by_month = [
        {'period': month, 'value': _round2(value)}
        for month, value in sorted(revenue_months.items())
    ]

    def _completion_for_range(range_start: datetime, range_end: datetime) -> float:
        scoped = [item for item in enrollments if _in_range(item.enrolled_at, start=range_start, end=range_end)]
        if not scoped:
            return 0.0
        values = [float(metrics_by_enrollment[item.id]['progress_percent']) for item in scoped]
        return _round2(sum(values) / len(values))

    current_completion = _completion_for_range(window.start, window.end)
    previous_completion = _completion_for_range(window.previous_start, window.previous_end)
    delta = _round2(current_completion - previous_completion)
    if delta > 0:
        direction = 'up'
    elif delta < 0:
        direction = 'down'
    else:
        direction = 'flat'

    return {
        'summary': {
            'active_learners': active_learners,
            'programs': len(programs),
            'groups': len(groups),
        },
        'program_completion': program_completion,
        'enrollments_by_month': enrollments_by_month,
        'top_programs_by_students': top_students[:5],
        'top_programs_by_score': top_scores[:5],
        'completion_trend': {
            'current': current_completion,
            'previous': previous_completion,
            'delta': delta,
            'direction': direction,
        },
        'revenue_by_month': revenue_by_month,
    }


def admin_dashboard(db: Session, window: PeriodWindow) -> dict:
    executive = executive_dashboard(db, window)
    enrollments = _load_enrollments(db)
    program_structure = _build_program_structure(db, list({item.group.program_id for item in enrollments}))
    metrics_by_enrollment = {
        enrollment.id: _enrollment_metrics(enrollment, program_structure)
        for enrollment in enrollments
    }

    groups = db.execute(
        select(Group)
        .options(selectinload(Group.program), selectinload(Group.enrollments))
    ).scalars().all()

    now = _utcnow()
    group_rows = []
    for group in groups:
        scoped_enrollments = [item for item in enrollments if item.group_id == group.id]
        total = len(scoped_enrollments)
        completed = sum(1 for item in scoped_enrollments if item.program_status.value == 'completed')
        completion_percent = _round2(_safe_divide(completed, total) * 100)
        start_date = _as_utc(group.start_date)
        end_date = _as_utc(group.end_date)
        if end_date and end_date < now:
            status = 'completed'
        elif start_date and start_date > now:
            status = 'planned'
        else:
            status = 'active'
        group_rows.append(
            {
                'group_id': group.id,
                'group_name': group.name,
                'program_name': group.program.name,
                'end_date': end_date.isoformat() if end_date else None,
                'students_count': total,
                'completion_percent': completion_percent,
                'status': status,
            }
        )
    group_rows.sort(key=lambda item: item['group_name'])

    last_login_map = _student_last_login_map(db, {item.student_id for item in enrollments})
    inactive_students = []
    for enrollment in enrollments:
        last_login = last_login_map.get(enrollment.student_id)
        stale = last_login is None or last_login <= now - timedelta(days=7)
        if not stale:
            continue
        metrics = metrics_by_enrollment[enrollment.id]
        inactive_students.append(
            {
                'student_id': enrollment.student_id,
                'full_name': enrollment.student.full_name,
                'group_name': enrollment.group.name,
                'program_name': enrollment.group.program.name,
                'last_login_at': last_login.isoformat() if last_login else None,
                'progress_percent': float(metrics['progress_percent']),
            }
        )
    inactive_students.sort(
        key=lambda item: item['last_login_at'] or '1970-01-01T00:00:00+00:00'
    )

    teacher_names = db.execute(
        select(TeacherGroupLink.group_id, User.full_name)
        .join(User, User.id == TeacherGroupLink.user_id)
    ).all()
    teachers_by_group: dict[str, list[str]] = defaultdict(list)
    for group_id, teacher_name in teacher_names:
        teachers_by_group[group_id].append(teacher_name)

    queue_items = db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.status == AssignmentStatus.submitted)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.student),
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.group).selectinload(Group.program),
            selectinload(AssignmentSubmission.lesson),
        )
    ).scalars().all()

    delayed_reviews = []
    for item in queue_items:
        submitted_at = _as_utc(item.submitted_at)
        if not submitted_at or submitted_at > now - timedelta(days=2):
            continue
        delayed_reviews.append(
            {
                'assignment_id': item.id,
                'student_name': item.enrollment.student.full_name,
                'lesson_title': item.lesson.title,
                'teacher_name': ', '.join(teachers_by_group.get(item.enrollment.group_id, [])) or 'Не назначен',
                'group_name': item.enrollment.group.name,
                'submitted_at': submitted_at.isoformat(),
                'waiting_days': _round2((now - submitted_at).total_seconds() / 86400),
            }
        )
    delayed_reviews.sort(key=lambda row: row['submitted_at'])

    integration_errors = db.execute(
        select(IntegrationErrorLog)
        .where(IntegrationErrorLog.created_at >= now - timedelta(days=30))
        .order_by(IntegrationErrorLog.created_at.desc())
    ).scalars().all()
    integration_rows = [
        {
            'id': row.id,
            'service': row.service,
            'operation': row.operation,
            'error_text': row.error_text,
            'created_at': (_as_utc(row.created_at) or row.created_at).isoformat(),
        }
        for row in integration_errors
    ]

    return {
        'executive': executive,
        'groups': group_rows,
        'inactive_students': inactive_students,
        'delayed_reviews': delayed_reviews,
        'integration_errors': integration_rows,
    }


def methodist_dashboard(db: Session, window: PeriodWindow) -> dict:
    _ = window
    enrollments = _load_enrollments(db)
    program_ids = list({item.group.program_id for item in enrollments})
    program_structure = _build_program_structure(db, program_ids)
    metrics_by_enrollment = {
        enrollment.id: _enrollment_metrics(enrollment, program_structure)
        for enrollment in enrollments
    }

    program_rows: dict[str, dict] = defaultdict(
        lambda: {
            'program_id': '',
            'program_name': '',
            'groups_count': 0,
            'enrollments_count': 0,
            'progress_sum': 0.0,
            'score_sum': 0.0,
            'score_count': 0,
            'duration_sum_days': 0.0,
            'duration_count': 0,
        }
    )
    group_seen: set[tuple[str, str]] = set()
    now = _utcnow()
    for enrollment in enrollments:
        pid = enrollment.group.program_id
        bucket = program_rows[pid]
        bucket['program_id'] = pid
        bucket['program_name'] = enrollment.group.program.name
        if (pid, enrollment.group_id) not in group_seen:
            bucket['groups_count'] += 1
            group_seen.add((pid, enrollment.group_id))
        bucket['enrollments_count'] += 1
        metrics = metrics_by_enrollment[enrollment.id]
        bucket['progress_sum'] += float(metrics['progress_percent'])
        if float(metrics['avg_score']) > 0:
            bucket['score_sum'] += float(metrics['avg_score'])
            bucket['score_count'] += 1
        end_date = _as_utc(enrollment.certification_issued_at) or now
        start_date = _as_utc(enrollment.enrolled_at) or now
        bucket['duration_sum_days'] += max((end_date - start_date).total_seconds() / 86400, 0)
        bucket['duration_count'] += 1

    program_metrics = []
    for row in program_rows.values():
        enrollments_count = int(row['enrollments_count'])
        program_metrics.append(
            {
                'program_id': row['program_id'],
                'program_name': row['program_name'],
                'groups_count': int(row['groups_count']),
                'enrollments_count': enrollments_count,
                'average_score': _round2(_safe_divide(float(row['score_sum']), float(row['score_count']))),
                'average_progress_percent': _round2(_safe_divide(float(row['progress_sum']), enrollments_count)),
                'average_duration_days': _round2(_safe_divide(float(row['duration_sum_days']), float(row['duration_count']))),
            }
        )
    program_metrics.sort(key=lambda item: item['program_name'])

    lesson_meta: dict[str, dict] = {}
    for pid, bucket in program_structure.items():
        program_name = next((item.group.program.name for item in enrollments if item.group.program_id == pid), '')
        for lesson in bucket['ordered_lessons']:
            lesson_meta[lesson['lesson_id']] = {
                'lesson_title': lesson['lesson_title'],
                'program_id': pid,
                'program_name': program_name,
                'module_title': lesson['module_title'],
            }

    repeated_attempts: dict[str, int] = defaultdict(int)
    failures: dict[str, int] = defaultdict(int)
    stuck_days_sum: dict[str, float] = defaultdict(float)
    stuck_count: dict[str, int] = defaultdict(int)

    for enrollment in enrollments:
        for progress in enrollment.progress_items:
            lesson_id = progress.lesson_id
            if lesson_id not in lesson_meta:
                continue
            if progress.attempts_used > 1:
                repeated_attempts[lesson_id] += progress.attempts_used - 1
            if progress.status != ProgressStatus.completed:
                anchor = _as_utc(progress.last_opened_at) or _as_utc(enrollment.enrolled_at) or now
                stuck_days_sum[lesson_id] += max((now - anchor).total_seconds() / 86400, 0)
                stuck_count[lesson_id] += 1

    test_attempts = db.execute(select(TestAttempt)).scalars().all()
    for attempt in test_attempts:
        if not attempt.passed and attempt.lesson_id in lesson_meta:
            failures[attempt.lesson_id] += 1

    submissions = db.execute(select(AssignmentSubmission)).scalars().all()
    for submission in submissions:
        if submission.status == AssignmentStatus.returned_for_revision and submission.lesson_id in lesson_meta:
            failures[submission.lesson_id] += 1

    problem_lessons = []
    all_lesson_ids = set(lesson_meta.keys())
    for lesson_id in all_lesson_ids:
        meta = lesson_meta[lesson_id]
        problem_lessons.append(
            {
                'lesson_id': lesson_id,
                'lesson_title': meta['lesson_title'],
                'program_name': meta['program_name'],
                'module_title': meta['module_title'],
                'repeat_attempts': repeated_attempts.get(lesson_id, 0),
                'failed_checks': failures.get(lesson_id, 0),
                'avg_stuck_days': _round2(_safe_divide(stuck_days_sum.get(lesson_id, 0.0), float(stuck_count.get(lesson_id, 0)))),
            }
        )
    problem_lessons.sort(
        key=lambda row: (row['repeat_attempts'] + row['failed_checks'], row['avg_stuck_days']),
        reverse=True,
    )

    funnel_rows = []
    for pid, bucket in program_structure.items():
        for module in bucket['modules']:
            reached = 0
            for enrollment in [item for item in enrollments if item.group.program_id == pid]:
                progress_map = {item.lesson_id: item.status for item in enrollment.progress_items}
                if any(progress_map.get(lesson_id, ProgressStatus.not_started) != ProgressStatus.not_started for lesson_id in module['lesson_ids']):
                    reached += 1
            funnel_rows.append(
                {
                    'program_id': pid,
                    'program_name': next((item.group.program.name for item in enrollments if item.group.program_id == pid), ''),
                    'module_id': module['module_id'],
                    'module_title': module['module_title'],
                    'module_order': module['module_order'],
                    'reached_count': reached,
                }
            )
    funnel_rows.sort(key=lambda row: row['reached_count'], reverse=True)

    comparison_source = sorted(program_metrics, key=lambda item: item['enrollments_count'], reverse=True)
    comparison = {
        'left': comparison_source[0] if len(comparison_source) > 0 else None,
        'right': comparison_source[1] if len(comparison_source) > 1 else None,
    }

    return {
        'program_metrics': program_metrics,
        'problem_lessons': problem_lessons[:15],
        'program_funnel': funnel_rows,
        'comparison': comparison,
    }


def curator_dashboard(db: Session, *, user_id: str, group_ids: set[str], window: PeriodWindow) -> dict:
    enrollments = _load_enrollments(db, group_ids=group_ids)
    program_structure = _build_program_structure(db, list({item.group.program_id for item in enrollments}))
    metrics_by_enrollment = {
        enrollment.id: _enrollment_metrics(enrollment, program_structure)
        for enrollment in enrollments
    }
    last_login_map = _student_last_login_map(db, {item.student_id for item in enrollments})
    now = _utcnow()

    rows = []
    for enrollment in enrollments:
        metrics = metrics_by_enrollment[enrollment.id]
        progress_percent = float(metrics['progress_percent'])
        start_date = _as_utc(enrollment.group.start_date)
        end_date = _as_utc(enrollment.group.end_date)
        if start_date and end_date and end_date > start_date:
            course_seconds = (end_date - start_date).total_seconds()
            elapsed = min(max((_as_utc(now) - start_date).total_seconds(), 0), course_seconds)
            expected_progress = _round2(_safe_divide(elapsed, course_seconds) * 100)
        else:
            expected_progress = progress_percent
        lag_percent = _round2(expected_progress - progress_percent)

        last_login = last_login_map.get(enrollment.student_id)
        if last_login is None or last_login <= now - timedelta(days=5) or lag_percent > 20:
            signal = 'red'
        elif lag_percent > 0:
            signal = 'yellow'
        else:
            signal = 'green'

        days_left = None
        if end_date:
            days_left = int((end_date - now).total_seconds() // 86400)

        rows.append(
            {
                'student_id': enrollment.student_id,
                'full_name': enrollment.student.full_name,
                'group_name': enrollment.group.name,
                'program_name': enrollment.group.program.name,
                'progress_percent': progress_percent,
                'last_login_at': last_login.isoformat() if last_login else None,
                'current_lesson': metrics['current_lesson'],
                'signal': signal,
                'lag_percent': lag_percent,
                'days_left': days_left,
            }
        )
    rows.sort(key=lambda item: item['full_name'])

    reminders = db.execute(
        select(ReminderLog)
        .where(ReminderLog.curator_user_id == user_id)
        .options(selectinload(ReminderLog.student))
    ).scalars().all()
    reminder_rows = []
    for item in reminders:
        sent_at = _as_utc(item.sent_at)
        if not _in_range(sent_at, start=window.start, end=window.end):
            continue
        last_login = last_login_map.get(item.student_id)
        reminder_rows.append(
            {
                'id': item.id,
                'student_id': item.student_id,
                'student_name': item.student.full_name,
                'message': item.message,
                'sent_at': sent_at.isoformat() if sent_at else None,
                'effect': bool(last_login and sent_at and last_login > sent_at),
            }
        )
    reminder_rows.sort(
        key=lambda row: row['sent_at'] or '1970-01-01T00:00:00+00:00',
        reverse=True,
    )

    signal_counts = {'green': 0, 'yellow': 0, 'red': 0}
    for row in rows:
        signal_counts[row['signal']] += 1

    return {
        'students': rows,
        'signal_counts': signal_counts,
        'reminders': reminder_rows,
    }


def teacher_dashboard(db: Session, *, user_id: str, group_ids: set[str], window: PeriodWindow) -> dict:
    _ = window
    enrollments = _load_enrollments(db, group_ids=group_ids)
    program_structure = _build_program_structure(db, list({item.group.program_id for item in enrollments}))
    metrics_by_enrollment = {
        enrollment.id: _enrollment_metrics(enrollment, program_structure)
        for enrollment in enrollments
    }

    course_rows: dict[str, dict] = defaultdict(
        lambda: {
            'group_id': '',
            'group_name': '',
            'program_name': '',
            'score_sum': 0.0,
            'score_count': 0,
            'distribution': {'0-59': 0, '60-74': 0, '75-89': 0, '90-100': 0},
        }
    )
    for enrollment in enrollments:
        gid = enrollment.group_id
        row = course_rows[gid]
        row['group_id'] = gid
        row['group_name'] = enrollment.group.name
        row['program_name'] = enrollment.group.program.name
        avg_score = float(metrics_by_enrollment[enrollment.id]['avg_score'])
        if avg_score > 0:
            row['score_sum'] += avg_score
            row['score_count'] += 1

    submissions = db.execute(
        select(AssignmentSubmission)
        .join(Enrollment, Enrollment.id == AssignmentSubmission.enrollment_id)
        .where(Enrollment.group_id.in_(group_ids) if group_ids else False)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.student),
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.group),
            selectinload(AssignmentSubmission.lesson),
        )
    ).scalars().all()

    review_durations: list[float] = []
    queue_rows = []
    for item in submissions:
        group_row = course_rows.get(item.enrollment.group_id)
        if group_row and item.grade is not None:
            grade = float(item.grade)
            if grade < 60:
                group_row['distribution']['0-59'] += 1
            elif grade < 75:
                group_row['distribution']['60-74'] += 1
            elif grade < 90:
                group_row['distribution']['75-89'] += 1
            else:
                group_row['distribution']['90-100'] += 1

        if item.reviewed_by_user_id == user_id and item.reviewed_at and item.submitted_at:
            review_durations.append(
                max((_as_utc(item.reviewed_at) - _as_utc(item.submitted_at)).total_seconds() / 3600, 0)
            )

        if item.status == AssignmentStatus.submitted:
            submitted_at = _as_utc(item.submitted_at)
            queue_rows.append(
                {
                    'assignment_id': item.id,
                    'student_name': item.enrollment.student.full_name,
                    'group_name': item.enrollment.group.name,
                    'lesson_title': item.lesson.title,
                    'submitted_at': submitted_at.isoformat() if submitted_at else None,
                }
            )
    queue_rows.sort(key=lambda row: row['submitted_at'] or '1970-01-01T00:00:00+00:00')

    course_metrics = []
    for row in course_rows.values():
        score_count = int(row['score_count'])
        course_metrics.append(
            {
                'group_id': row['group_id'],
                'group_name': row['group_name'],
                'program_name': row['program_name'],
                'average_score': _round2(_safe_divide(float(row['score_sum']), score_count)),
                'distribution': [{'bucket': key, 'count': value} for key, value in row['distribution'].items()],
            }
        )
    course_metrics.sort(key=lambda item: item['group_name'])

    questions = db.execute(
        select(StudentQuestion)
        .where(StudentQuestion.group_id.in_(group_ids) if group_ids else False)
    ).scalars().all()

    question_lesson_counts: dict[str, int] = defaultdict(int)
    enrollment_by_key = {(item.student_id, item.group_id): item for item in enrollments}
    for question in questions:
        enrollment = enrollment_by_key.get((question.student_id, question.group_id))
        if enrollment is None:
            continue
        current_lesson = metrics_by_enrollment.get(enrollment.id, {}).get('current_lesson') or 'Не определено'
        question_lesson_counts[str(current_lesson)] += 1
    most_questions_lesson = None
    if question_lesson_counts:
        lesson_name, count = max(question_lesson_counts.items(), key=lambda pair: pair[1])
        most_questions_lesson = {'lesson_title': lesson_name, 'questions_count': count}

    average_review_hours = _round2(sum(review_durations) / len(review_durations)) if review_durations else 0.0

    return {
        'courses': course_metrics,
        'most_questions_lesson': most_questions_lesson,
        'average_review_hours': average_review_hours,
        'review_queue': queue_rows,
    }


def customer_dashboard(db: Session, *, student_ids: set[str], window: PeriodWindow) -> dict:
    enrollments = _load_enrollments(db, student_ids=student_ids)
    program_structure = _build_program_structure(db, list({item.group.program_id for item in enrollments}))
    metrics_by_enrollment = {
        enrollment.id: _enrollment_metrics(enrollment, program_structure)
        for enrollment in enrollments
    }
    last_login_map = _student_last_login_map(db, {item.student_id for item in enrollments})

    summary = {'completed': 0, 'in_progress': 0, 'not_started': 0}
    employee_rows = []
    for enrollment in enrollments:
        metrics = metrics_by_enrollment[enrollment.id]
        progress_percent = float(metrics['progress_percent'])
        if enrollment.program_status.value == 'completed' or progress_percent >= 100:
            summary['completed'] += 1
            state = 'completed'
        elif progress_percent <= 0:
            summary['not_started'] += 1
            state = 'not_started'
        else:
            summary['in_progress'] += 1
            state = 'in_progress'

        last_login = last_login_map.get(enrollment.student_id)
        employee_rows.append(
            {
                'student_id': enrollment.student_id,
                'full_name': enrollment.student.full_name,
                'program_name': enrollment.group.program.name,
                'group_name': enrollment.group.name,
                'progress_percent': progress_percent,
                'last_login_at': last_login.isoformat() if last_login else None,
                'status': state,
            }
        )
    employee_rows.sort(key=lambda row: row['full_name'])

    enrollment_ids = [item.id for item in enrollments]
    completions = db.execute(
        select(LessonProgress.completed_at)
        .where(
            LessonProgress.enrollment_id.in_(enrollment_ids) if enrollment_ids else False,
            LessonProgress.status == ProgressStatus.completed,
        )
    ).all()

    weekly_counts: dict[str, int] = defaultdict(int)
    for (completed_at,) in completions:
        if _in_range(completed_at, start=window.start, end=window.end):
            weekly_counts[_week_key(_as_utc(completed_at) or completed_at)] += 1

    total_lessons = sum(int(program_structure.get(item.group.program_id, {}).get('total_lessons', 0)) for item in enrollments)
    if total_lessons <= 0:
        total_lessons = 1
    weekly_progress = [
        {
            'period': week,
            'value': _round2(_safe_divide(count, total_lessons) * 100),
        }
        for week, count in sorted(weekly_counts.items())
    ]

    return {
        'summary': summary,
        'employees': employee_rows,
        'weekly_progress': weekly_progress,
    }
