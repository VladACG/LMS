from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.models.entities import Enrollment, Group, Lesson, LessonProgress, Module
from app.models.enums import ProgressStatus


def enrollment_score_stats(db, enrollment_id: str, *, total_lessons: int | None = None) -> tuple[float, float, int]:
    rows = db.execute(
        select(LessonProgress.status, LessonProgress.score).where(LessonProgress.enrollment_id == enrollment_id)
    ).all()
    if not rows:
        return 0.0, 0.0, 0

    completed = sum(1 for status, _score in rows if status == ProgressStatus.completed)
    denominator = total_lessons if total_lessons and total_lessons > 0 else len(rows)
    progress_percent = (completed / denominator * 100) if denominator > 0 else 0.0
    scores = [float(score) for _status, score in rows if score is not None]
    avg_score = (sum(scores) / len(scores)) if scores else 0.0
    return round(progress_percent, 2), round(avg_score, 2), completed


def lesson_problem_stats(db, program_id: str) -> list[dict]:
    lesson_rows = db.execute(
        select(Lesson.id, Lesson.title)
        .join(Module, Module.id == Lesson.module_id)
        .where(Module.program_id == program_id)
    ).all()
    if not lesson_rows:
        return []

    lesson_titles = {lesson_id: title for lesson_id, title in lesson_rows}
    counts: dict[str, int] = defaultdict(int)
    problem_statuses = {
        ProgressStatus.not_started,
        ProgressStatus.in_progress,
        ProgressStatus.awaiting_review,
    }
    progress_rows = db.execute(
        select(LessonProgress.lesson_id)
        .join(Enrollment, Enrollment.id == LessonProgress.enrollment_id)
        .join(Group, Group.id == Enrollment.group_id)
        .where(
            Group.program_id == program_id,
            LessonProgress.lesson_id.in_(lesson_titles.keys()),
            LessonProgress.status.in_(problem_statuses),
        )
    ).all()
    for (lesson_id,) in progress_rows:
        counts[lesson_id] += 1

    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [
        {'lesson_id': lesson_id, 'lesson_title': lesson_titles[lesson_id], 'uncredited_count': count}
        for lesson_id, count in ordered[:10]
    ]

