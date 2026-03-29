from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Enrollment, Lesson, LessonProgress, Module, TestAttempt
from app.models.enums import LessonType, ProgramProgressStatus, ProgressStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _lesson_order_rows(db: Session, program_id: str) -> list[tuple[Lesson, Module]]:
    stmt = (
        select(Lesson, Module)
        .join(Module, Lesson.module_id == Module.id)
        .where(Module.program_id == program_id)
        .order_by(Module.order_index.asc(), Lesson.order_index.asc())
    )
    return list(db.execute(stmt).all())


def get_next_required_lesson_id(db: Session, enrollment_id: str, program_id: str, strict_order: bool = True) -> str | None:
    if not strict_order:
        return None

    ordered = _lesson_order_rows(db, program_id)
    if not ordered:
        return None

    completed_ids = {
        item.lesson_id
        for item in db.execute(
            select(LessonProgress).where(
                LessonProgress.enrollment_id == enrollment_id,
                LessonProgress.status == ProgressStatus.completed,
            )
        )
        .scalars()
        .all()
    }

    for lesson, _module in ordered:
        if lesson.id not in completed_ids:
            return lesson.id
    return None


def ensure_progress_row(db: Session, enrollment_id: str, lesson_id: str) -> LessonProgress:
    progress = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment_id,
            LessonProgress.lesson_id == lesson_id,
        )
    ).scalar_one_or_none()
    if progress is None:
        progress = LessonProgress(enrollment_id=enrollment_id, lesson_id=lesson_id)
        db.add(progress)
        db.flush()
    return progress


def _assert_lesson_order(db: Session, enrollment: Enrollment, lesson_id: str) -> None:
    next_required = get_next_required_lesson_id(
        db,
        enrollment.id,
        enrollment.group.program_id,
        strict_order=enrollment.group.program.strict_order,
    )
    if next_required is not None and lesson_id != next_required:
        raise HTTPException(status_code=409, detail='Lesson order violation: complete previous lesson first')


def mark_program_started(enrollment: Enrollment) -> tuple[ProgramProgressStatus, ProgramProgressStatus]:
    before = enrollment.program_status
    if enrollment.program_status == ProgramProgressStatus.not_started:
        enrollment.program_status = ProgramProgressStatus.in_progress
    return before, enrollment.program_status


def open_lesson(db: Session, enrollment: Enrollment, lesson: Lesson) -> LessonProgress:
    progress = ensure_progress_row(db, enrollment.id, lesson.id)
    progress.last_opened_at = _utcnow()
    if progress.status == ProgressStatus.not_started:
        progress.status = ProgressStatus.in_progress
    mark_program_started(enrollment)
    return progress


def complete_content_lesson(
    db: Session,
    enrollment: Enrollment,
    lesson: Lesson,
    *,
    watched_to_end: bool,
    scrolled_to_bottom: bool,
) -> LessonProgress:
    if lesson.type not in {LessonType.video, LessonType.text}:
        raise HTTPException(status_code=422, detail='Only video/text lessons can be completed via engagement endpoint')

    if lesson.type == LessonType.video and not watched_to_end:
        raise HTTPException(status_code=422, detail='Video lesson requires watched_to_end=true')
    if lesson.type == LessonType.text and not scrolled_to_bottom:
        raise HTTPException(status_code=422, detail='Text lesson requires scrolled_to_bottom=true')

    progress = ensure_progress_row(db, enrollment.id, lesson.id)
    if progress.status == ProgressStatus.completed:
        mark_program_started(enrollment)
        return progress

    _assert_lesson_order(db, enrollment, lesson.id)

    progress.status = ProgressStatus.completed
    progress.completed_at = _utcnow()

    mark_program_started(enrollment)
    return progress


def register_test_attempt(
    db: Session,
    enrollment: Enrollment,
    lesson: Lesson,
    *,
    score: float,
    actor_user_id: str | None,
) -> tuple[LessonProgress, TestAttempt, bool, int]:
    if lesson.type != LessonType.test:
        raise HTTPException(status_code=422, detail='Lesson is not a test')

    _assert_lesson_order(db, enrollment, lesson.id)

    progress = ensure_progress_row(db, enrollment.id, lesson.id)
    pass_score = float(lesson.content_json.get('pass_score', 60.0))
    max_attempts = int(lesson.content_json.get('max_attempts', 3))
    attempts_allowed = max_attempts + int(progress.extra_attempts_allowed)

    if progress.status == ProgressStatus.completed:
        attempt_no = progress.attempts_used
        attempt = TestAttempt(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            attempt_no=attempt_no,
            score=score,
            passed=True,
            actor_user_id=actor_user_id,
        )
        db.add(attempt)
        db.flush()
        return progress, attempt, True, attempts_allowed

    if progress.attempts_used >= attempts_allowed:
        raise HTTPException(status_code=409, detail='Test attempts limit exceeded; admin override required')

    progress.attempts_used += 1
    progress.last_opened_at = _utcnow()
    passed = score >= pass_score

    attempt = TestAttempt(
        enrollment_id=enrollment.id,
        lesson_id=lesson.id,
        attempt_no=progress.attempts_used,
        score=score,
        passed=passed,
        actor_user_id=actor_user_id,
    )
    db.add(attempt)

    if passed:
        progress.status = ProgressStatus.completed
        progress.score = score
        progress.completed_at = _utcnow()
    else:
        progress.status = ProgressStatus.in_progress

    mark_program_started(enrollment)
    db.flush()
    return progress, attempt, passed, attempts_allowed


def set_assignment_waiting(db: Session, enrollment: Enrollment, lesson: Lesson) -> LessonProgress:
    if lesson.type != LessonType.assignment:
        raise HTTPException(status_code=422, detail='Lesson is not a practical assignment')

    _assert_lesson_order(db, enrollment, lesson.id)
    progress = ensure_progress_row(db, enrollment.id, lesson.id)
    progress.status = ProgressStatus.awaiting_review
    progress.last_opened_at = _utcnow()
    mark_program_started(enrollment)
    return progress


def set_assignment_result(
    db: Session,
    enrollment: Enrollment,
    lesson: Lesson,
    *,
    grade: float | None,
    returned_for_revision: bool,
) -> LessonProgress:
    progress = ensure_progress_row(db, enrollment.id, lesson.id)
    pass_score = float(lesson.content_json.get('assignment_pass_score', 60.0))

    if returned_for_revision or grade is None or grade < pass_score:
        progress.status = ProgressStatus.in_progress
        progress.score = grade
        progress.completed_at = None
    else:
        progress.status = ProgressStatus.completed
        progress.score = grade
        progress.completed_at = _utcnow()

    return progress


def enrollment_metrics(db: Session, enrollment: Enrollment) -> dict[str, float | int]:
    ordered = _lesson_order_rows(db, enrollment.group.program_id)
    total_lessons = len(ordered)

    progress_items = db.execute(
        select(LessonProgress).where(LessonProgress.enrollment_id == enrollment.id)
    ).scalars().all()

    completed = sum(1 for item in progress_items if item.status == ProgressStatus.completed)
    progress_percent = (completed / total_lessons * 100) if total_lessons else 0.0
    scores = [item.score for item in progress_items if item.score is not None]
    avg_score = (sum(scores) / len(scores)) if scores else 0.0

    return {
        'total_lessons': total_lessons,
        'completed_lessons': completed,
        'progress_percent': round(progress_percent, 2),
        'avg_score': round(avg_score, 2),
    }


def update_program_status_and_certificate(db: Session, enrollment: Enrollment) -> bool:
    metrics = enrollment_metrics(db, enrollment)

    threshold_progress = enrollment.group.program.certification_progress_threshold
    threshold_avg = enrollment.group.program.certification_min_avg_score

    if metrics['completed_lessons'] > 0 and enrollment.program_status == ProgramProgressStatus.not_started:
        enrollment.program_status = ProgramProgressStatus.in_progress

    issued_now = False
    if (
        metrics['progress_percent'] >= threshold_progress
        and metrics['avg_score'] >= threshold_avg
    ):
        enrollment.program_status = ProgramProgressStatus.completed
        if enrollment.certification_issued_at is None:
            enrollment.certification_issued_at = _utcnow()
            enrollment.certificate_url = f'/api/certificates/{enrollment.id}/download'
            enrollment.certificate_number = f'CERT-{uuid.uuid4().hex[:10].upper()}'
            issued_now = True
    elif enrollment.program_status != ProgramProgressStatus.not_started:
        enrollment.program_status = ProgramProgressStatus.in_progress

    return issued_now
