from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.security import (
    AuthContext,
    create_access_token,
    get_auth_context,
    has_role,
    hash_password,
    require_roles,
    verify_password,
)
from app.db.session import get_db
from app.models.entities import (
    AuditEvent,
    AssignmentSubmission,
    CuratorGroupLink,
    CustomerStudentLink,
    Enrollment,
    Group,
    IntegrationErrorLog,
    Lesson,
    LessonMaterial,
    LessonProgress,
    Module,
    Notification,
    Program,
    ReminderLog,
    Student,
    StudentQuestion,
    TeacherGroupLink,
    TestAttempt,
    User,
    UserRoleLink,
    UserStudentLink,
)
from app.models.enums import AssignmentStatus, NotificationChannel, PaymentStatus, ProgressStatus, UserRole
from app.schemas.lms import (
    AuditEventOut,
    AutomationRunResult,
    AssignmentOut,
    AssignmentReviewRequest,
    AssignmentSubmitRequest,
    CalendarLinksOut,
    CertificateOut,
    ChangePasswordRequest,
    CompleteLessonResponse,
    CustomerFinalReportResponse,
    CustomerStudentAssignRequest,
    EnrollmentCreate,
    EnrollmentOut,
    GroupCreate,
    GroupFinalReportRow,
    GroupOut,
    GroupProgressResponse,
    GroupProgressRow,
    GroupUserAssignRequest,
    IntegrationErrorOut,
    LessonMaterialOut,
    LessonEngagementRequest,
    LessonCreate,
    LessonOut,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MessageOut,
    ModuleCreate,
    ModuleOut,
    NotificationMarkReadRequest,
    NotificationOut,
    PaymentOut,
    PaymentWebhookRequest,
    ProgramCreate,
    ProgramDetailOut,
    ProgramOut,
    ProgramStatsReportOut,
    ProgressTableResponse,
    QuestionAnswerRequest,
    QuestionCreateRequest,
    QuestionOut,
    ReminderOut,
    ReminderSendRequest,
    StudentLessonsResponse,
    StudentLessonOut,
    TelegramConfirmRequest,
    TelegramLinkOut,
    TestAttemptRequest,
    TestAttemptResponse,
    TestAttemptsOverrideRequest,
    UserBlockRequest,
    UserCreate,
    UserOut,
    UserProfileOut,
    UserRoleUpdate,
)
from app.services.audit import log_audit
from app.services.analytics import (
    PeriodPreset,
    admin_dashboard,
    curator_dashboard,
    customer_dashboard,
    executive_dashboard,
    methodist_dashboard,
    resolve_period_window,
    teacher_dashboard,
)
from app.services.calendar import build_google_calendar_link, build_ics_content, build_yandex_calendar_link
from app.services.integration_errors import log_integration_error
from app.services.notifications import create_notification, run_scheduled_notifications
from app.services.payments import (
    apply_paid_program_on_enrollment,
    create_payment_link,
    mark_payment_paid,
    mark_payment_overdue,
)
from app.services.progress import (
    complete_content_lesson,
    enrollment_metrics,
    get_next_required_lesson_id,
    open_lesson,
    register_test_attempt,
    set_assignment_result,
    set_assignment_waiting,
    update_program_status_and_certificate,
)
from app.services.reports import enrollment_score_stats, lesson_problem_stats
from app.services.storage import (
    ASSIGNMENT_MAX_SIZE_BYTES,
    generate_download_url,
    is_assignment_file_allowed,
    local_file_path,
    upload_bytes,
)
from app.services.telegram import link_telegram_account, telegram_invite_url

router = APIRouter(prefix='/api', tags=['lms'])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _lesson_content(payload: LessonCreate) -> dict:
    if payload.type.value == 'video':
        if payload.video_url is None:
            raise HTTPException(status_code=422, detail='video_url is required for video lesson')
        content = {'video_url': str(payload.video_url)}
        if payload.webinar_start_at:
            content['webinar_start_at'] = payload.webinar_start_at.isoformat()
        if payload.webinar_join_url:
            content['webinar_join_url'] = str(payload.webinar_join_url)
        return content
    if payload.type.value == 'text':
        if not payload.text_body:
            raise HTTPException(status_code=422, detail='text_body is required for text lesson')
        content = {'text_body': payload.text_body}
        if payload.webinar_start_at:
            content['webinar_start_at'] = payload.webinar_start_at.isoformat()
        if payload.webinar_join_url:
            content['webinar_join_url'] = str(payload.webinar_join_url)
        return content
    if payload.type.value == 'test':
        if payload.questions_json is None:
            raise HTTPException(status_code=422, detail='questions_json is required for test lesson')
        content = {
            'questions': payload.questions_json,
            'pass_score': payload.test_pass_score,
            'max_attempts': payload.test_max_attempts,
        }
        if payload.webinar_start_at:
            content['webinar_start_at'] = payload.webinar_start_at.isoformat()
        if payload.webinar_join_url:
            content['webinar_join_url'] = str(payload.webinar_join_url)
        return content
    if payload.type.value == 'assignment':
        content = {'assignment_pass_score': payload.assignment_pass_score}
        if payload.webinar_start_at:
            content['webinar_start_at'] = payload.webinar_start_at.isoformat()
        if payload.webinar_join_url:
            content['webinar_join_url'] = str(payload.webinar_join_url)
        return content
    raise HTTPException(status_code=422, detail='Unsupported lesson type')


def _find_or_create_student(db: Session, full_name: str, email: str | None, organization: str | None = None) -> Student:
    student = None
    if email:
        student = db.execute(select(Student).where(Student.email == email)).scalar_one_or_none()

    if student is None:
        if email is None:
            student = db.execute(
                select(Student).where(Student.full_name == full_name, Student.email.is_(None))
            ).scalar_one_or_none()
        else:
            student = db.execute(select(Student).where(Student.full_name == full_name, Student.email == email)).scalar_one_or_none()

    if student is None:
        student = Student(full_name=full_name, email=email, organization=organization)
        db.add(student)
        db.flush()
    elif organization and not student.organization:
        student.organization = organization

    return student


def _progress_status(completed_lessons: int, total_lessons: int) -> Literal['not_started', 'in_progress', 'completed']:
    if completed_lessons <= 0:
        return 'not_started'
    if total_lessons > 0 and completed_lessons >= total_lessons:
        return 'completed'
    return 'in_progress'


def _collect_program_lesson_totals(db: Session, program_ids: list[str]) -> dict[str, int]:
    totals = {program_id: 0 for program_id in program_ids}
    if not program_ids:
        return totals

    lessons_with_program = db.execute(
        select(Module.program_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .where(Module.program_id.in_(program_ids))
    ).all()

    for (program_id,) in lessons_with_program:
        totals[program_id] = totals.get(program_id, 0) + 1

    return totals


def _collect_completed_stats(db: Session, enrollment_ids: list[str]) -> dict[str, dict[str, int | datetime | None]]:
    stats: dict[str, dict[str, int | datetime | None]] = {
        enrollment_id: {'completed_count': 0, 'last_activity': None}
        for enrollment_id in enrollment_ids
    }

    if not enrollment_ids:
        return stats

    rows = db.execute(
        select(LessonProgress.enrollment_id, LessonProgress.completed_at).where(
            LessonProgress.enrollment_id.in_(enrollment_ids),
            LessonProgress.status == ProgressStatus.completed,
        )
    ).all()

    for enrollment_id, completed_at in rows:
        item = stats.setdefault(enrollment_id, {'completed_count': 0, 'last_activity': None})
        item['completed_count'] = int(item['completed_count']) + 1

        previous_last = item['last_activity']
        if completed_at and (previous_last is None or completed_at > previous_last):
            item['last_activity'] = completed_at

    return stats


def _collect_student_last_login(db: Session, student_ids: list[str]) -> dict[str, datetime | None]:
    if not student_ids:
        return {}
    rows = db.execute(
        select(UserStudentLink.student_id, User.last_login_at)
        .join(User, User.id == UserStudentLink.user_id)
        .where(UserStudentLink.student_id.in_(student_ids))
    ).all()
    return {student_id: last_login_at for student_id, last_login_at in rows}


def _build_progress_row(
    enrollment: Enrollment,
    total_lessons: int,
    completed_count: int,
    last_activity: datetime | None,
    last_login_at: datetime | None,
    average_score: float = 0.0,
) -> GroupProgressRow:
    progress_percent = round((completed_count / total_lessons) * 100, 2) if total_lessons else 0.0
    return GroupProgressRow(
        group_id=enrollment.group_id,
        program_id=enrollment.group.program_id,
        student_id=enrollment.student_id,
        full_name=enrollment.student.full_name,
        group_name=enrollment.group.name,
        program_name=enrollment.group.program.name,
        completed_lessons=completed_count,
        total_lessons=total_lessons,
        progress_percent=progress_percent,
        progress_status=_progress_status(completed_count, total_lessons),
        enrolled_at=enrollment.enrolled_at,
        last_activity=last_activity,
        last_login_at=last_login_at,
        program_status=enrollment.program_status.value,
        certificate_available=enrollment.certification_issued_at is not None,
        organization=enrollment.student.organization,
        average_score=average_score,
        completion_date=enrollment.certification_issued_at,
        certificate_number=enrollment.certificate_number,
        payment_status=enrollment.payment_status,
    )


def _program_status(
    program: Program,
    lesson_total: int,
    completed_stats: dict[str, dict[str, int | datetime | None]],
    visible_group_ids: set[str] | None = None,
) -> Literal['draft', 'active', 'archived']:
    groups = program.groups
    if visible_group_ids is not None:
        groups = [group for group in program.groups if group.id in visible_group_ids]

    if not groups:
        return 'draft'

    enrollments = [enrollment for group in groups for enrollment in group.enrollments]
    if not enrollments:
        return 'active'

    if lesson_total <= 0:
        return 'draft'

    all_completed = all(
        int(completed_stats.get(enrollment.id, {'completed_count': 0})['completed_count']) >= lesson_total
        for enrollment in enrollments
    )
    return 'archived' if all_completed else 'active'


def _user_roles(user: User) -> list[UserRole]:
    return sorted((link.role for link in user.roles), key=lambda role: role.value)


def _user_profile(user: User) -> UserProfileOut:
    student_id = user.student_link.student_id if user.student_link else None
    return UserProfileOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        blocked=user.blocked,
        temp_password_required=user.temp_password_required,
        student_id=student_id,
        telegram_linked=bool(user.telegram_chat_id),
        telegram_username=user.telegram_username,
    )


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        blocked=user.blocked,
        temp_password_required=user.temp_password_required,
        roles=_user_roles(user),
        telegram_linked=bool(user.telegram_chat_id),
    )


def _student_id_for_user(ctx: AuthContext) -> str:
    if ctx.user.student_link is None:
        raise HTTPException(status_code=403, detail='Student profile is not linked to the user')
    return ctx.user.student_link.student_id


def _teacher_group_ids(db: Session, user_id: str) -> set[str]:
    rows = db.execute(select(TeacherGroupLink.group_id).where(TeacherGroupLink.user_id == user_id)).all()
    return {group_id for (group_id,) in rows}


def _curator_group_ids(db: Session, user_id: str) -> set[str]:
    rows = db.execute(select(CuratorGroupLink.group_id).where(CuratorGroupLink.user_id == user_id)).all()
    return {group_id for (group_id,) in rows}


def _all_group_ids(db: Session) -> set[str]:
    rows = db.execute(select(Group.id)).all()
    return {group_id for (group_id,) in rows}


def _all_student_ids(db: Session) -> set[str]:
    rows = db.execute(select(Student.id)).all()
    return {student_id for (student_id,) in rows}


def _group_ids_for_student(db: Session, student_id: str) -> set[str]:
    rows = db.execute(select(Enrollment.group_id).where(Enrollment.student_id == student_id)).all()
    return {group_id for (group_id,) in rows}


def _student_ids_for_groups(db: Session, group_ids: set[str]) -> set[str]:
    if not group_ids:
        return set()
    rows = db.execute(select(Enrollment.student_id).where(Enrollment.group_id.in_(group_ids))).all()
    return {student_id for (student_id,) in rows}


def _customer_student_ids(db: Session, user_id: str) -> set[str]:
    rows = db.execute(
        select(CustomerStudentLink.student_id).where(CustomerStudentLink.customer_user_id == user_id)
    ).all()
    return {student_id for (student_id,) in rows}


def _allowed_group_ids(ctx: AuthContext, db: Session) -> set[str]:
    if has_role(ctx, UserRole.admin.value):
        return _all_group_ids(db)

    allowed: set[str] = set()
    if has_role(ctx, UserRole.teacher.value):
        allowed.update(_teacher_group_ids(db, ctx.user.id))
    if has_role(ctx, UserRole.curator.value):
        allowed.update(_curator_group_ids(db, ctx.user.id))
    if has_role(ctx, UserRole.student.value):
        allowed.update(_group_ids_for_student(db, _student_id_for_user(ctx)))
    if has_role(ctx, UserRole.customer.value):
        customer_students = _customer_student_ids(db, ctx.user.id)
        if customer_students:
            rows = db.execute(
                select(Enrollment.group_id).where(Enrollment.student_id.in_(customer_students))
            ).all()
            allowed.update(group_id for (group_id,) in rows)

    return allowed


def _allowed_student_ids(ctx: AuthContext, db: Session) -> set[str]:
    if has_role(ctx, UserRole.admin.value):
        return _all_student_ids(db)

    allowed: set[str] = set()
    if has_role(ctx, UserRole.teacher.value):
        allowed.update(_student_ids_for_groups(db, _teacher_group_ids(db, ctx.user.id)))
    if has_role(ctx, UserRole.curator.value):
        allowed.update(_student_ids_for_groups(db, _curator_group_ids(db, ctx.user.id)))
    if has_role(ctx, UserRole.student.value):
        allowed.add(_student_id_for_user(ctx))
    if has_role(ctx, UserRole.customer.value):
        allowed.update(_customer_student_ids(db, ctx.user.id))

    return allowed


def _allowed_program_ids(ctx: AuthContext, db: Session) -> set[str]:
    if has_role(ctx, UserRole.admin.value) or has_role(ctx, UserRole.methodist.value):
        rows = db.execute(select(Program.id)).all()
        return {program_id for (program_id,) in rows}

    group_ids = _allowed_group_ids(ctx, db)
    if not group_ids:
        return set()

    rows = db.execute(select(Group.program_id).where(Group.id.in_(group_ids))).all()
    return {program_id for (program_id,) in rows}


def _assert_can_view_student_data(ctx: AuthContext) -> None:
    if any(
        has_role(ctx, role)
        for role in (
            UserRole.admin.value,
            UserRole.teacher.value,
            UserRole.curator.value,
            UserRole.student.value,
            UserRole.customer.value,
        )
    ):
        return
    raise HTTPException(status_code=403, detail='Forbidden for current role')


def _assert_enrollment_access(
    ctx: AuthContext,
    db: Session,
    *,
    student_id: str,
    group_id: str,
    write: bool,
) -> Enrollment:
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.group_id == group_id, Enrollment.student_id == student_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')

    if has_role(ctx, UserRole.admin.value):
        return enrollment

    if has_role(ctx, UserRole.student.value) and _student_id_for_user(ctx) == student_id:
        if enrollment.group.program.is_paid and enrollment.payment_status != PaymentStatus.paid:
            raise HTTPException(
                status_code=402,
                detail='Payment is required before access to course materials',
            )
        return enrollment

    if not write and has_role(ctx, UserRole.teacher.value) and group_id in _teacher_group_ids(db, ctx.user.id):
        return enrollment

    if not write and has_role(ctx, UserRole.curator.value) and group_id in _curator_group_ids(db, ctx.user.id):
        return enrollment

    raise HTTPException(status_code=403, detail='Forbidden for current role')


def _assignment_out(item: AssignmentSubmission) -> AssignmentOut:
    download_url = generate_download_url(item.file_key) if item.file_key else None
    return AssignmentOut(
        id=item.id,
        student_id=item.enrollment.student_id,
        student_name=item.enrollment.student.full_name,
        group_id=item.enrollment.group_id,
        group_name=item.enrollment.group.name,
        program_name=item.enrollment.group.program.name,
        lesson_id=item.lesson_id,
        lesson_title=item.lesson.title,
        status=item.status,
        submission_text=item.submission_text,
        submitted_at=item.submitted_at,
        grade=item.grade,
        teacher_comment=item.teacher_comment,
        reviewed_by_user_id=item.reviewed_by_user_id,
        reviewed_at=item.reviewed_at,
        student_viewed_at=item.student_viewed_at,
        file_name=item.file_name,
        file_mime=item.file_mime,
        file_size_bytes=item.file_size_bytes,
        file_download_url=download_url,
    )


def _question_out(item: StudentQuestion) -> QuestionOut:
    return QuestionOut(
        id=item.id,
        student_id=item.student_id,
        student_name=item.student.full_name,
        group_id=item.group_id,
        group_name=item.group.name,
        question_text=item.question_text,
        answer_text=item.answer_text,
        created_at=item.created_at,
        answered_at=item.answered_at,
    )


def _notification_out(item: Notification) -> NotificationOut:
    return NotificationOut(
        id=item.id,
        channel=item.channel,
        subject=item.subject,
        body=item.body,
        link_url=item.link_url,
        is_read=item.is_read,
        created_at=item.created_at,
    )


def _audit_out(item: AuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=item.id,
        actor_user_id=item.actor_user_id,
        event_type=item.event_type,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        from_status=item.from_status,
        to_status=item.to_status,
        payload_json=item.payload_json,
        created_at=item.created_at,
    )


def _material_out(item: LessonMaterial) -> LessonMaterialOut:
    return LessonMaterialOut(
        id=item.id,
        lesson_id=item.lesson_id,
        file_name=item.file_name,
        file_mime=item.file_mime,
        file_size_bytes=item.file_size_bytes,
        uploaded_at=item.uploaded_at,
        download_url=generate_download_url(item.file_key),
    )


def _payment_out(enrollment: Enrollment) -> PaymentOut:
    return PaymentOut(
        enrollment_id=enrollment.id,
        payment_status=enrollment.payment_status,
        payment_link=enrollment.payment_link,
        payment_due_at=enrollment.payment_due_at,
        payment_confirmed_at=enrollment.payment_confirmed_at,
    )


def _build_excel_bytes(*, sheet_title: str, headers: list[str], rows: list[list[object | None]]) -> bytes:
    try:
        from openpyxl import Workbook
    except Exception as exc:  # pragma: no cover - dependency import path
        raise HTTPException(
            status_code=500,
            detail='openpyxl is not installed on server',
        ) from exc

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    for row in rows:
        ws.append(row)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _analytics_window(
    *,
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    try:
        return resolve_period_window(period=period, date_from=date_from, date_to=date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _xlsx_response(content: bytes, file_name: str) -> Response:
    return Response(
        content=content,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={file_name}'},
    )


def _notify_payment_confirmed(db: Session, enrollment: Enrollment) -> None:
    student_user = db.execute(
        select(User)
        .join(UserStudentLink, UserStudentLink.user_id == User.id)
        .where(UserStudentLink.student_id == enrollment.student_id)
    ).scalar_one_or_none()
    if student_user:
        create_notification(
            db,
            recipient_user_id=student_user.id,
            subject='Оплата подтверждена',
            body='Платёж получен. Доступ к урокам открыт.',
            link_url=f'/groups/{enrollment.group_id}',
            event_key=f'payment-confirmed-{enrollment.id}',
        )


@router.post('/auth/login', response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(
        select(User)
        .where(User.email == _normalize_email(payload.email))
        .options(selectinload(User.roles), selectinload(User.student_link))
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid email or password')
    if user.blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User is blocked')

    user.last_login_at = _utcnow()
    db.commit()
    db.refresh(user)

    roles = _user_roles(user)
    return LoginResponse(
        access_token=create_access_token(user.id),
        roles=roles,
        require_password_change=user.temp_password_required and UserRole.student in roles,
        user=_user_profile(user),
    )


@router.get('/auth/me', response_model=MeResponse)
def me(ctx: AuthContext = Depends(get_auth_context)):
    roles = _user_roles(ctx.user)
    return MeResponse(
        roles=roles,
        require_password_change=ctx.must_change_password,
        user=_user_profile(ctx.user),
    )


@router.post('/auth/change-password', response_model=MessageOut)
def change_password(
    payload: ChangePasswordRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, ctx.user.password_hash):
        raise HTTPException(status_code=400, detail='Old password is incorrect')

    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail='New password must be different from old password')

    ctx.user.password_hash = hash_password(payload.new_password)
    ctx.user.temp_password_required = False
    db.commit()
    return MessageOut(message='Password changed successfully')


@router.get('/telegram/link', response_model=TelegramLinkOut)
def get_telegram_link(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    db.refresh(ctx.user)
    invite_url = telegram_invite_url(ctx.user)
    db.commit()
    return TelegramLinkOut(
        invite_url=invite_url,
        linked=bool(ctx.user.telegram_chat_id),
        telegram_username=ctx.user.telegram_username,
    )


@router.post('/telegram/confirm', response_model=MessageOut)
def confirm_telegram_link(payload: TelegramConfirmRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.telegram_link_token == payload.token)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail='Telegram link token is invalid or expired')

    link_telegram_account(user=user, chat_id=payload.chat_id, username=payload.username)
    log_audit(
        db,
        actor_user_id=user.id,
        event_type='telegram_linked',
        entity_type='user',
        entity_id=user.id,
        payload={'telegram_username': payload.username, 'chat_id': payload.chat_id},
    )
    db.commit()
    return MessageOut(message='Telegram account linked')


@router.get('/users', response_model=list[UserOut])
def list_users(_ctx: AuthContext = Depends(require_roles(UserRole.admin.value)), db: Session = Depends(get_db)):
    users = db.execute(select(User).options(selectinload(User.roles), selectinload(User.student_link))).scalars().all()
    users.sort(key=lambda item: item.created_at, reverse=True)
    return [_user_out(item) for item in users]


@router.post('/users', response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    email = _normalize_email(payload.email)
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail='User with this email already exists')

    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        temp_password_required=payload.temp_password_required,
    )
    db.add(user)
    db.flush()

    roles = set(payload.roles)
    for role in sorted(roles, key=lambda item: item.value):
        db.add(UserRoleLink(user_id=user.id, role=role))

    if UserRole.student in roles:
        student = db.execute(select(Student).where(Student.email == email)).scalar_one_or_none()
        if student is None:
            student = Student(full_name=payload.full_name, email=email, organization=payload.organization)
            db.add(student)
            db.flush()
        elif payload.organization and not student.organization:
            student.organization = payload.organization
        db.add(UserStudentLink(user_id=user.id, student_id=student.id))

    create_notification(
        db,
        recipient_user_id=user.id,
        subject='Учетная запись создана',
        body=(
            'Ваш аккаунт в LMS создан администратором. '
            'Войдите по выданным учетным данным. '
            'Если это временный пароль, поменяйте его после входа.'
        ),
        link_url='/',
        event_key=f'user-created-{user.id}',
        channels=(NotificationChannel.in_app, NotificationChannel.email),
    )
    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='user_created',
        entity_type='user',
        entity_id=user.id,
        payload={'email': user.email, 'roles': [item.value for item in roles]},
    )

    db.commit()
    db.refresh(user)
    db.refresh(user, attribute_names=['roles', 'student_link'])
    return _user_out(user)


@router.post('/users/{user_id}/roles', response_model=UserOut)
def update_user_roles(
    user_id: str,
    payload: UserRoleUpdate,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    user = db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    target_roles = set(payload.roles)
    current_roles = {item.role for item in user.roles}

    for role in current_roles - target_roles:
        db.execute(
            delete(UserRoleLink).where(UserRoleLink.user_id == user.id, UserRoleLink.role == role)
        )

    for role in target_roles - current_roles:
        db.add(UserRoleLink(user_id=user.id, role=role))

    if UserRole.student in target_roles:
        existing_link = db.execute(
            select(UserStudentLink).where(UserStudentLink.user_id == user.id)
        ).scalar_one_or_none()
        if existing_link is None:
            student = db.execute(select(Student).where(Student.email == user.email)).scalar_one_or_none()
            if student is None:
                student = Student(full_name=user.full_name, email=user.email)
                db.add(student)
                db.flush()
            db.add(UserStudentLink(user_id=user.id, student_id=student.id))

    db.commit()
    user = db.execute(
        select(User).where(User.id == user.id).options(selectinload(User.roles), selectinload(User.student_link))
    ).scalar_one()
    return _user_out(user)


@router.post('/users/{user_id}/block', response_model=UserOut)
def block_user(
    user_id: str,
    payload: UserBlockRequest,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    user = db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.roles), selectinload(User.student_link))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    user.blocked = payload.blocked
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post('/programs', response_model=ProgramOut, status_code=201)
def create_program(
    payload: ProgramCreate,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    obj = Program(
        name=payload.name,
        description=payload.description,
        strict_order=payload.strict_order,
        certification_progress_threshold=payload.certification_progress_threshold,
        certification_min_avg_score=payload.certification_min_avg_score,
        is_paid=payload.is_paid,
        price_amount=payload.price_amount,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return ProgramOut(
        id=obj.id,
        name=obj.name,
        description=obj.description,
        created_at=obj.created_at,
        status='draft',
        strict_order=obj.strict_order,
        certification_progress_threshold=obj.certification_progress_threshold,
        certification_min_avg_score=obj.certification_min_avg_score,
        is_paid=obj.is_paid,
        price_amount=obj.price_amount,
    )


@router.get('/programs', response_model=list[ProgramOut])
def list_programs(
    search: str | None = None,
    status: Literal['draft', 'active', 'archived'] | None = None,
    sort: Literal['asc', 'desc'] = 'desc',
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    programs = db.execute(
        select(Program)
        .options(selectinload(Program.groups).selectinload(Group.enrollments))
    ).scalars().all()

    visible_group_ids: set[str] | None = None
    if not has_role(ctx, UserRole.admin.value) and not has_role(ctx, UserRole.methodist.value):
        allowed_program_ids = _allowed_program_ids(ctx, db)
        programs = [program for program in programs if program.id in allowed_program_ids]
        visible_group_ids = _allowed_group_ids(ctx, db)

    program_ids = [program.id for program in programs]
    lesson_totals = _collect_program_lesson_totals(db, program_ids)
    enrollment_ids = [enrollment.id for program in programs for group in program.groups for enrollment in group.enrollments]
    completed_stats = _collect_completed_stats(db, enrollment_ids)

    rows: list[ProgramOut] = []
    for program in programs:
        program_status = _program_status(program, lesson_totals.get(program.id, 0), completed_stats, visible_group_ids)
        row = ProgramOut(
            id=program.id,
            name=program.name,
            description=program.description,
            created_at=program.created_at,
            status=program_status,
            strict_order=program.strict_order,
            certification_progress_threshold=program.certification_progress_threshold,
            certification_min_avg_score=program.certification_min_avg_score,
            is_paid=program.is_paid,
            price_amount=program.price_amount,
        )
        rows.append(row)

    if search:
        search_normalized = search.strip().lower()
        rows = [row for row in rows if search_normalized in row.name.lower()]

    if status:
        rows = [row for row in rows if row.status == status]

    rows.sort(key=lambda item: item.created_at, reverse=(sort == 'desc'))
    return rows


@router.get('/programs/{program_id}', response_model=ProgramDetailOut)
def get_program(program_id: str, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    allowed_program_ids = _allowed_program_ids(ctx, db)
    if (
        not has_role(ctx, UserRole.admin.value)
        and not has_role(ctx, UserRole.methodist.value)
        and program_id not in allowed_program_ids
    ):
        raise HTTPException(status_code=403, detail='Forbidden for current role')

    program = db.execute(
        select(Program)
        .where(Program.id == program_id)
        .options(selectinload(Program.modules).selectinload(Module.lessons))
    ).scalar_one_or_none()
    if not program:
        raise HTTPException(status_code=404, detail='Program not found')

    modules_out = []
    for module in sorted(program.modules, key=lambda module_item: module_item.order_index):
        lessons_out = [
            {'id': lesson.id, 'title': lesson.title, 'type': lesson.type, 'order_index': lesson.order_index}
            for lesson in sorted(module.lessons, key=lambda lesson_item: lesson_item.order_index)
        ]
        modules_out.append(
            {
                'id': module.id,
                'title': module.title,
                'order_index': module.order_index,
                'lessons': lessons_out,
            }
        )

    return {
        'id': program.id,
        'name': program.name,
        'description': program.description,
        'strict_order': program.strict_order,
        'certification_progress_threshold': program.certification_progress_threshold,
        'certification_min_avg_score': program.certification_min_avg_score,
        'is_paid': program.is_paid,
        'price_amount': program.price_amount,
        'modules': modules_out,
    }


@router.post('/programs/{program_id}/modules', response_model=ModuleOut, status_code=201)
def create_module(
    program_id: str,
    payload: ModuleCreate,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    program = db.get(Program, program_id)
    if not program:
        raise HTTPException(status_code=404, detail='Program not found')

    obj = Module(program_id=program.id, title=payload.title, order_index=payload.order_index)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post('/modules/{module_id}/lessons', response_model=LessonOut, status_code=201)
def create_lesson(
    module_id: str,
    payload: LessonCreate,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    module = db.get(Module, module_id)
    if not module:
        raise HTTPException(status_code=404, detail='Module not found')

    lesson = Lesson(
        module_id=module.id,
        title=payload.title,
        type=payload.type,
        order_index=payload.order_index,
        content_json=_lesson_content(payload),
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.post('/lessons/{lesson_id}/materials/upload', response_model=LessonMaterialOut, status_code=201)
async def upload_lesson_material(
    lesson_id: str,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    lesson = db.execute(
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(selectinload(Lesson.module).selectinload(Module.program))
    ).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail='Lesson not found')

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail='File is empty')

    try:
        stored = upload_bytes(
            key_prefix=f'materials/{lesson_id}',
            file_name=file.filename or 'material.bin',
            data=file_bytes,
            content_type=file.content_type or 'application/octet-stream',
        )
    except Exception as exc:
        log_integration_error(
            db,
            service='storage',
            operation='upload_lesson_material',
            error_text=str(exc),
            context={'lesson_id': lesson_id, 'file_name': file.filename},
            user_id=ctx.user.id,
        )
        raise HTTPException(status_code=503, detail='Material storage is temporarily unavailable') from exc

    material = LessonMaterial(
        lesson_id=lesson.id,
        file_name=str(stored['file_name']),
        file_key=str(stored['key']),
        file_mime=str(stored['content_type']),
        file_size_bytes=int(stored['size_bytes']),
        uploaded_by_user_id=ctx.user.id,
    )
    db.add(material)
    db.flush()
    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='lesson_material_uploaded',
        entity_type='lesson_material',
        entity_id=material.id,
        payload={'lesson_id': lesson.id, 'file_name': material.file_name, 'file_size_bytes': material.file_size_bytes},
    )
    db.commit()
    db.refresh(material)
    return _material_out(material)


@router.get('/lessons/{lesson_id}/materials', response_model=list[LessonMaterialOut])
def list_lesson_materials(
    lesson_id: str,
    group_id: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    lesson = db.execute(
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(selectinload(Lesson.module).selectinload(Module.program))
    ).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail='Lesson not found')

    if not has_role(ctx, UserRole.admin.value) and not has_role(ctx, UserRole.methodist.value):
        allowed_programs = _allowed_program_ids(ctx, db)
        if lesson.module.program_id not in allowed_programs:
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    if has_role(ctx, UserRole.student.value) and not has_role(ctx, UserRole.admin.value):
        if not group_id:
            raise HTTPException(status_code=422, detail='group_id is required for student material access')
        enrollment = _assert_enrollment_access(
            ctx,
            db,
            student_id=_student_id_for_user(ctx),
            group_id=group_id,
            write=False,
        )
        if enrollment.group.program_id != lesson.module.program_id:
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    rows = db.execute(
        select(LessonMaterial).where(LessonMaterial.lesson_id == lesson.id)
    ).scalars().all()
    rows.sort(key=lambda item: item.uploaded_at, reverse=True)
    return [_material_out(item) for item in rows]


@router.get('/storage/local/{key:path}')
def download_local_storage_file(
    key: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if settings.storage_backend.lower() != 'local':
        raise HTTPException(status_code=404, detail='Local storage endpoint is disabled')

    assignment = db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.file_key == key)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.group).selectinload(Group.program),
        )
    ).scalar_one_or_none()
    if assignment:
        if not has_role(ctx, UserRole.admin.value):
            allowed = False
            if has_role(ctx, UserRole.student.value) and ctx.user.student_link:
                allowed = assignment.enrollment.student_id == ctx.user.student_link.student_id
            if has_role(ctx, UserRole.teacher.value) and assignment.enrollment.group_id in _teacher_group_ids(db, ctx.user.id):
                allowed = True
            if has_role(ctx, UserRole.curator.value) and assignment.enrollment.group_id in _curator_group_ids(db, ctx.user.id):
                allowed = True
            if not allowed:
                raise HTTPException(status_code=403, detail='Forbidden for current role')
    else:
        material = db.execute(
            select(LessonMaterial)
            .where(LessonMaterial.file_key == key)
            .join(Lesson, Lesson.id == LessonMaterial.lesson_id)
            .join(Module, Module.id == Lesson.module_id)
            .join(Program, Program.id == Module.program_id)
        ).scalar_one_or_none()
        if not material:
            raise HTTPException(status_code=404, detail='File not found')

        if not has_role(ctx, UserRole.admin.value) and not has_role(ctx, UserRole.methodist.value):
            allowed_programs = _allowed_program_ids(ctx, db)
            lesson_program_id = db.execute(
                select(Module.program_id).join(Lesson, Lesson.module_id == Module.id).where(Lesson.id == material.lesson_id)
            ).scalar_one()
            if lesson_program_id not in allowed_programs:
                raise HTTPException(status_code=403, detail='Forbidden for current role')

            if has_role(ctx, UserRole.student.value) and ctx.user.student_link:
                enrollment = db.execute(
                    select(Enrollment)
                    .join(Group, Group.id == Enrollment.group_id)
                    .where(
                        Enrollment.student_id == ctx.user.student_link.student_id,
                        Group.program_id == lesson_program_id,
                    )
                    .options(selectinload(Enrollment.group).selectinload(Group.program))
                ).scalars().first()
                if not enrollment:
                    raise HTTPException(status_code=403, detail='Forbidden for current role')
                if enrollment.group.program.is_paid and enrollment.payment_status != PaymentStatus.paid:
                    raise HTTPException(status_code=402, detail='Payment is required before access to course materials')

    try:
        file_path = local_file_path(key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail='File not found') from exc
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return FileResponse(path=file_path)


@router.post('/groups', response_model=GroupOut, status_code=201)
def create_group(
    payload: GroupCreate,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    program = db.get(Program, payload.program_id)
    if not program:
        raise HTTPException(status_code=404, detail='Program not found')

    group = Group(
        name=payload.name,
        program_id=payload.program_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get('/groups', response_model=list[GroupOut])
def list_groups(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    if has_role(ctx, UserRole.admin.value):
        groups = db.execute(select(Group).order_by(Group.name.asc())).scalars().all()
        return groups

    allowed_group_ids = _allowed_group_ids(ctx, db)
    if not allowed_group_ids:
        return []

    groups = db.execute(select(Group).where(Group.id.in_(allowed_group_ids)).order_by(Group.name.asc())).scalars().all()
    return groups

@router.post('/groups/{group_id}/enrollments', response_model=list[EnrollmentOut], status_code=201)
def create_enrollments(
    group_id: str,
    payload: EnrollmentCreate,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    group = db.execute(
        select(Group).where(Group.id == group_id).options(selectinload(Group.program))
    ).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail='Group not found')

    created: list[EnrollmentOut] = []
    for student_payload in payload.students:
        normalized_email = _normalize_email(student_payload.email) if student_payload.email else None
        student = _find_or_create_student(
            db,
            student_payload.full_name,
            normalized_email,
            student_payload.organization,
        )

        exists = db.execute(
            select(Enrollment).where(Enrollment.group_id == group.id, Enrollment.student_id == student.id)
        ).scalar_one_or_none()
        if exists:
            continue

        enrollment = Enrollment(group_id=group.id, student_id=student.id)
        db.add(enrollment)
        db.flush()
        apply_paid_program_on_enrollment(db, enrollment=enrollment, actor_user_id=ctx.user.id)

        student_user = db.execute(
            select(User).join(UserStudentLink, UserStudentLink.user_id == User.id).where(UserStudentLink.student_id == student.id)
        ).scalar_one_or_none()
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='enrollment_created',
            entity_type='enrollment',
            entity_id=enrollment.id,
            payload={
                'group_id': group.id,
                'student_id': student.id,
                'payment_status': enrollment.payment_status.value,
                'is_paid_program': group.program.is_paid,
            },
        )
        if student_user:
            curator_names = db.execute(
                select(User.full_name)
                .join(CuratorGroupLink, CuratorGroupLink.user_id == User.id)
                .where(CuratorGroupLink.group_id == group.id)
            ).all()
            curator_name = ', '.join(name for (name,) in curator_names) if curator_names else 'не назначен'
            create_notification(
                db,
                recipient_user_id=student_user.id,
                subject='Вы зачислены в группу',
                body=(
                    f'Программа: {group.program.name}. '
                    f'Дата начала: {group.start_date.date().isoformat() if group.start_date else "не указана"}. '
                    f'Куратор: {curator_name}.'
                    + (
                        f' Ссылка на оплату: {enrollment.payment_link}.'
                        if enrollment.payment_status == PaymentStatus.pending and enrollment.payment_link
                        else ''
                    )
                ),
                link_url=f'/groups/{group.id}',
                event_key=f'enroll-{group.id}-{student.id}',
            )

        created.append(
            EnrollmentOut(
                enrollment_id=enrollment.id,
                student_id=student.id,
                full_name=student.full_name,
                email=student.email,
                organization=student.organization,
                payment_status=enrollment.payment_status,
                payment_link=enrollment.payment_link,
            )
        )

    db.commit()
    return created


@router.get('/payments/{enrollment_id}', response_model=PaymentOut)
def get_payment_status(
    enrollment_id: str,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.student.value)),
    db: Session = Depends(get_db),
):
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.id == enrollment_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')

    if has_role(ctx, UserRole.student.value) and not has_role(ctx, UserRole.admin.value):
        if _student_id_for_user(ctx) != enrollment.student_id:
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    return _payment_out(enrollment)


@router.post('/payments/{enrollment_id}/refresh-link', response_model=PaymentOut)
def refresh_payment_link(
    enrollment_id: str,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.id == enrollment_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')
    if not enrollment.group.program.is_paid:
        raise HTTPException(status_code=422, detail='Program is not paid')
    if enrollment.payment_status == PaymentStatus.paid:
        raise HTTPException(status_code=409, detail='Payment is already confirmed')

    price = enrollment.group.program.price_amount or 0.0
    enrollment.payment_status = PaymentStatus.pending
    enrollment.payment_link = create_payment_link(
        db,
        enrollment_id=enrollment.id,
        amount=price,
        description=f'Оплата курса {enrollment.group.program.name}',
        user_id=ctx.user.id,
    )
    enrollment.payment_due_at = _utcnow() + timedelta(days=3)
    enrollment.payment_confirmed_at = None
    enrollment.payment_provider = 'yookassa'

    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='payment_link_refreshed',
        entity_type='enrollment',
        entity_id=enrollment.id,
        payload={'payment_link': enrollment.payment_link},
    )
    db.commit()
    db.refresh(enrollment)
    return _payment_out(enrollment)


@router.post('/payments/webhook', response_model=MessageOut)
def payment_webhook(payload: PaymentWebhookRequest, db: Session = Depends(get_db)):
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.id == payload.enrollment_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')

    previous = enrollment.payment_status
    if payload.status == 'paid':
        mark_payment_paid(enrollment=enrollment, external_id=payload.external_id)
        _notify_payment_confirmed(db, enrollment)
    elif payload.status == 'pending':
        enrollment.payment_status = PaymentStatus.pending
        enrollment.payment_confirmed_at = None
        if enrollment.payment_due_at is None:
            enrollment.payment_due_at = _utcnow() + timedelta(days=3)
    else:
        mark_payment_overdue(enrollment=enrollment)

    log_audit(
        db,
        actor_user_id=None,
        event_type='payment_status_changed',
        entity_type='enrollment',
        entity_id=enrollment.id,
        from_status=previous.value,
        to_status=enrollment.payment_status.value,
        payload={'external_id': payload.external_id, 'provider_status': payload.status},
    )
    db.commit()
    return MessageOut(message='Payment webhook accepted')


@router.get('/payments/mock/{enrollment_id}')
def mock_payment_page(enrollment_id: str, confirm: bool = False, db: Session = Depends(get_db)):
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.id == enrollment_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')

    previous = enrollment.payment_status
    if confirm and enrollment.payment_status != PaymentStatus.paid:
        mark_payment_paid(enrollment=enrollment, external_id='mock')
        _notify_payment_confirmed(db, enrollment)
        log_audit(
            db,
            actor_user_id=None,
            event_type='payment_status_changed',
            entity_type='enrollment',
            entity_id=enrollment.id,
            from_status=previous.value,
            to_status=PaymentStatus.paid.value,
            payload={'provider': 'mock'},
        )
        db.commit()

    link = f'{settings.app_base_url}/api/payments/mock/{enrollment.id}?confirm=true'
    html = (
        '<html><body style="font-family:Arial,sans-serif;padding:20px">'
        f'<h2>Оплата курса: {enrollment.group.program.name}</h2>'
        f'<p>Статус оплаты: <strong>{enrollment.payment_status.value}</strong></p>'
        f'<p><a href="{link}">Подтвердить оплату (mock)</a></p>'
        '</body></html>'
    )
    return Response(content=html, media_type='text/html; charset=utf-8')


@router.post('/groups/{group_id}/teachers', response_model=MessageOut)
def assign_group_teachers(
    group_id: str,
    payload: GroupUserAssignRequest,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Group not found')

    requested_ids = set(payload.user_ids)
    if requested_ids:
        users = db.execute(
            select(User).where(User.id.in_(requested_ids)).options(selectinload(User.roles))
        ).scalars().all()
        if len(users) != len(requested_ids):
            raise HTTPException(status_code=404, detail='Some users were not found')
        invalid = [user.email for user in users if UserRole.teacher not in {role.role for role in user.roles}]
        if invalid:
            raise HTTPException(status_code=422, detail='All assigned users must have teacher role')

    db.execute(delete(TeacherGroupLink).where(TeacherGroupLink.group_id == group_id))
    for user_id in sorted(requested_ids):
        db.add(TeacherGroupLink(user_id=user_id, group_id=group_id))
    db.commit()
    return MessageOut(message='Teachers assigned')


@router.post('/groups/{group_id}/curators', response_model=MessageOut)
def assign_group_curators(
    group_id: str,
    payload: GroupUserAssignRequest,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail='Group not found')

    requested_ids = set(payload.user_ids)
    if requested_ids:
        users = db.execute(
            select(User).where(User.id.in_(requested_ids)).options(selectinload(User.roles))
        ).scalars().all()
        if len(users) != len(requested_ids):
            raise HTTPException(status_code=404, detail='Some users were not found')
        invalid = [user.email for user in users if UserRole.curator not in {role.role for role in user.roles}]
        if invalid:
            raise HTTPException(status_code=422, detail='All assigned users must have curator role')

    db.execute(delete(CuratorGroupLink).where(CuratorGroupLink.group_id == group_id))
    for user_id in sorted(requested_ids):
        db.add(CuratorGroupLink(user_id=user_id, group_id=group_id))
    db.commit()
    return MessageOut(message='Curators assigned')


@router.post('/customers/{customer_user_id}/students', response_model=MessageOut)
def assign_customer_students(
    customer_user_id: str,
    payload: CustomerStudentAssignRequest,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    customer = db.execute(
        select(User).where(User.id == customer_user_id).options(selectinload(User.roles))
    ).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail='Customer user not found')
    if UserRole.customer not in {role.role for role in customer.roles}:
        raise HTTPException(status_code=422, detail='Target user does not have customer role')

    requested_ids = set(payload.student_ids)
    if requested_ids:
        student_count = db.execute(select(Student.id).where(Student.id.in_(requested_ids))).all()
        if len(student_count) != len(requested_ids):
            raise HTTPException(status_code=404, detail='Some students were not found')

    db.execute(delete(CustomerStudentLink).where(CustomerStudentLink.customer_user_id == customer_user_id))
    for student_id in sorted(requested_ids):
        db.add(CustomerStudentLink(customer_user_id=customer_user_id, student_id=student_id))
    db.commit()
    return MessageOut(message='Customer students assigned')


@router.get('/students/{student_id}/lessons', response_model=StudentLessonsResponse)
def get_student_lessons(
    student_id: str,
    group_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    enrollment = _assert_enrollment_access(ctx, db, student_id=student_id, group_id=group_id, write=False)

    ordered = db.execute(
        select(Lesson, Module)
        .join(Module, Lesson.module_id == Module.id)
        .where(Module.program_id == enrollment.group.program_id)
        .order_by(Module.order_index.asc(), Lesson.order_index.asc())
    ).all()

    progress_rows = db.execute(
        select(LessonProgress).where(LessonProgress.enrollment_id == enrollment.id)
    ).scalars().all()
    progress_map = {item.lesson_id: item.status for item in progress_rows}

    next_required = get_next_required_lesson_id(
        db,
        enrollment.id,
        enrollment.group.program_id,
        strict_order=enrollment.group.program.strict_order,
    )
    completed_count = sum(1 for status_item in progress_map.values() if status_item == ProgressStatus.completed)
    program_strict = enrollment.group.program.strict_order
    progress_by_lesson = {item.lesson_id: item for item in progress_rows}

    lessons_out: list[StudentLessonOut] = []
    for lesson, module in ordered:
        status_value = progress_map.get(lesson.id, ProgressStatus.not_started)
        is_locked = (
            program_strict
            and next_required is not None
            and lesson.id != next_required
            and status_value != ProgressStatus.completed
        )
        progress_item = progress_by_lesson.get(lesson.id)
        max_attempts = int(lesson.content_json.get('max_attempts', 3)) if lesson.type.value == 'test' else 0
        attempts_used = progress_item.attempts_used if progress_item else 0
        attempts_allowed = max_attempts + (progress_item.extra_attempts_allowed if progress_item else 0)
        lessons_out.append(
            StudentLessonOut(
                lesson_id=lesson.id,
                module_title=module.title,
                lesson_title=lesson.title,
                lesson_type=lesson.type,
                module_order=module.order_index,
                lesson_order=lesson.order_index,
                status=status_value,
                is_locked=is_locked,
                attempts_used=attempts_used,
                attempts_allowed=attempts_allowed,
            )
        )

    return StudentLessonsResponse(
        total=len(lessons_out),
        completed=completed_count,
        program_status=enrollment.program_status.value,
        payment_status=enrollment.payment_status,
        payment_required=enrollment.group.program.is_paid,
        payment_link=enrollment.payment_link,
        lessons=lessons_out,
    )


@router.get('/students/{student_id}/calendar-links', response_model=CalendarLinksOut)
def get_calendar_links(
    student_id: str,
    group_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    enrollment = _assert_enrollment_access(ctx, db, student_id=student_id, group_id=group_id, write=False)
    lessons = db.execute(
        select(Lesson)
        .join(Module, Module.id == Lesson.module_id)
        .where(Module.program_id == enrollment.group.program_id)
        .order_by(Module.order_index.asc(), Lesson.order_index.asc())
    ).scalars().all()

    google_url = build_google_calendar_link(group=enrollment.group, lessons=lessons)
    yandex_url = build_yandex_calendar_link(group=enrollment.group, lessons=lessons)
    ics_url = f'{settings.app_base_url}/api/students/{student_id}/calendar.ics?group_id={group_id}'
    return CalendarLinksOut(google_url=google_url, yandex_url=yandex_url, ics_url=ics_url)


@router.get('/students/{student_id}/payment', response_model=PaymentOut)
def get_student_group_payment(
    student_id: str,
    group_id: str,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.student.value)),
    db: Session = Depends(get_db),
):
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.group_id == group_id, Enrollment.student_id == student_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')

    if has_role(ctx, UserRole.student.value) and not has_role(ctx, UserRole.admin.value):
        if _student_id_for_user(ctx) != student_id:
            raise HTTPException(status_code=403, detail='Forbidden for current role')
    return _payment_out(enrollment)


@router.get('/students/{student_id}/calendar.ics')
def download_calendar_ics(
    student_id: str,
    group_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    enrollment = _assert_enrollment_access(ctx, db, student_id=student_id, group_id=group_id, write=False)
    lessons = db.execute(
        select(Lesson)
        .join(Module, Module.id == Lesson.module_id)
        .where(Module.program_id == enrollment.group.program_id)
        .order_by(Module.order_index.asc(), Lesson.order_index.asc())
    ).scalars().all()
    content = build_ics_content(group=enrollment.group, lessons=lessons)
    file_name = f'course-{enrollment.group.id}.ics'
    return Response(
        content=content,
        media_type='text/calendar; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={file_name}'},
    )


@router.post('/students/{student_id}/lessons/{lesson_id}/complete', response_model=CompleteLessonResponse)
def complete_lesson(
    student_id: str,
    lesson_id: str,
    group_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    enrollment = _assert_enrollment_access(ctx, db, student_id=student_id, group_id=group_id, write=True)

    lesson_with_module = db.execute(
        select(Lesson, Module)
        .join(Module, Lesson.module_id == Module.id)
        .where(Lesson.id == lesson_id)
    ).first()
    if not lesson_with_module:
        raise HTTPException(status_code=404, detail='Lesson not found')

    lesson, module = lesson_with_module
    if module.program_id != enrollment.group.program_id:
        raise HTTPException(status_code=422, detail='Lesson is not part of enrollment program')

    progress_before = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == lesson.id,
        )
    ).scalar_one_or_none()
    before_status = progress_before.status.value if progress_before else ProgressStatus.not_started.value

    if lesson.type.value in {'video', 'text'}:
        progress = complete_content_lesson(
            db,
            enrollment,
            lesson,
            watched_to_end=True,
            scrolled_to_bottom=True,
        )
    elif lesson.type.value == 'test':
        raise HTTPException(status_code=409, detail='Use test attempt endpoint for test lessons')
    elif lesson.type.value == 'assignment':
        raise HTTPException(status_code=409, detail='Use assignment submission endpoint for practical assignments')
    else:
        raise HTTPException(status_code=422, detail='Unsupported lesson type')

    issued_now = update_program_status_and_certificate(db, enrollment)
    if issued_now:
        student_user = db.execute(
            select(User).join(UserStudentLink, UserStudentLink.user_id == User.id).where(UserStudentLink.student_id == enrollment.student_id)
        ).scalar_one_or_none()
        if student_user:
            create_notification(
                db,
                recipient_user_id=student_user.id,
                subject='Сертификат доступен',
                body='Условия сертификации выполнены. Сертификат готов к скачиванию.',
                link_url=enrollment.certificate_url,
                event_key=f'certificate-issued-{enrollment.id}',
            )
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='certificate_issued',
            entity_type='enrollment',
            entity_id=enrollment.id,
            payload={'certificate_url': enrollment.certificate_url},
        )

    if progress.status.value != before_status:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='lesson_status_changed',
            entity_type='lesson_progress',
            entity_id=progress.id,
            from_status=before_status,
            to_status=progress.status.value,
            payload={'lesson_id': lesson.id, 'enrollment_id': enrollment.id},
        )

    db.commit()
    db.refresh(progress)
    return CompleteLessonResponse(lesson_id=lesson.id, status=progress.status, completed_at=progress.completed_at)


@router.post('/students/{student_id}/lessons/{lesson_id}/engagement', response_model=CompleteLessonResponse)
def lesson_engagement(
    student_id: str,
    lesson_id: str,
    payload: LessonEngagementRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    enrollment = _assert_enrollment_access(ctx, db, student_id=student_id, group_id=payload.group_id, write=True)
    lesson_with_module = db.execute(
        select(Lesson, Module)
        .join(Module, Lesson.module_id == Module.id)
        .where(Lesson.id == lesson_id)
    ).first()
    if not lesson_with_module:
        raise HTTPException(status_code=404, detail='Lesson not found')
    lesson, module = lesson_with_module
    if module.program_id != enrollment.group.program_id:
        raise HTTPException(status_code=422, detail='Lesson is not part of enrollment program')

    progress_before = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == lesson.id,
        )
    ).scalar_one_or_none()
    before_status = progress_before.status.value if progress_before else ProgressStatus.not_started.value

    progress = open_lesson(db, enrollment, lesson)
    if payload.watched_to_end or payload.scrolled_to_bottom:
        progress = complete_content_lesson(
            db,
            enrollment,
            lesson,
            watched_to_end=payload.watched_to_end,
            scrolled_to_bottom=payload.scrolled_to_bottom,
        )

    issued_now = update_program_status_and_certificate(db, enrollment)
    if issued_now:
        student_user = db.execute(
            select(User).join(UserStudentLink, UserStudentLink.user_id == User.id).where(UserStudentLink.student_id == enrollment.student_id)
        ).scalar_one_or_none()
        if student_user:
            create_notification(
                db,
                recipient_user_id=student_user.id,
                subject='Сертификат доступен',
                body='Условия сертификации выполнены. Сертификат готов к скачиванию.',
                link_url=enrollment.certificate_url,
                event_key=f'certificate-issued-{enrollment.id}',
            )
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='certificate_issued',
            entity_type='enrollment',
            entity_id=enrollment.id,
            payload={'certificate_url': enrollment.certificate_url},
        )

    if progress.status.value != before_status:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='lesson_status_changed',
            entity_type='lesson_progress',
            entity_id=progress.id,
            from_status=before_status,
            to_status=progress.status.value,
            payload={'lesson_id': lesson.id, 'enrollment_id': enrollment.id},
        )

    db.commit()
    db.refresh(progress)
    return CompleteLessonResponse(lesson_id=lesson.id, status=progress.status, completed_at=progress.completed_at)


@router.post('/students/{student_id}/lessons/{lesson_id}/test-attempt', response_model=TestAttemptResponse)
def submit_test_attempt(
    student_id: str,
    lesson_id: str,
    payload: TestAttemptRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    enrollment = _assert_enrollment_access(ctx, db, student_id=student_id, group_id=payload.group_id, write=True)
    lesson_with_module = db.execute(
        select(Lesson, Module)
        .join(Module, Lesson.module_id == Module.id)
        .where(Lesson.id == lesson_id)
    ).first()
    if not lesson_with_module:
        raise HTTPException(status_code=404, detail='Lesson not found')
    lesson, module = lesson_with_module
    if module.program_id != enrollment.group.program_id:
        raise HTTPException(status_code=422, detail='Lesson is not part of enrollment program')

    before_row = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == lesson.id,
        )
    ).scalar_one_or_none()
    before_status = before_row.status.value if before_row else ProgressStatus.not_started.value

    progress, attempt, passed, attempts_allowed = register_test_attempt(
        db,
        enrollment,
        lesson,
        score=payload.score,
        actor_user_id=ctx.user.id,
    )
    issued_now = update_program_status_and_certificate(db, enrollment)

    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='test_attempt',
        entity_type='test_attempt',
        entity_id=attempt.id,
        payload={
            'lesson_id': lesson.id,
            'enrollment_id': enrollment.id,
            'attempt_no': attempt.attempt_no,
            'score': payload.score,
            'passed': passed,
        },
    )
    if progress.status.value != before_status:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='lesson_status_changed',
            entity_type='lesson_progress',
            entity_id=progress.id,
            from_status=before_status,
            to_status=progress.status.value,
            payload={'lesson_id': lesson.id, 'enrollment_id': enrollment.id},
        )
    if issued_now:
        student_user = db.execute(
            select(User).join(UserStudentLink, UserStudentLink.user_id == User.id).where(UserStudentLink.student_id == enrollment.student_id)
        ).scalar_one_or_none()
        if student_user:
            create_notification(
                db,
                recipient_user_id=student_user.id,
                subject='Сертификат доступен',
                body='Условия сертификации выполнены. Сертификат готов к скачиванию.',
                link_url=enrollment.certificate_url,
                event_key=f'certificate-issued-{enrollment.id}',
            )
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='certificate_issued',
            entity_type='enrollment',
            entity_id=enrollment.id,
            payload={'certificate_url': enrollment.certificate_url},
        )

    db.commit()
    db.refresh(progress)
    return TestAttemptResponse(
        lesson_id=lesson.id,
        score=payload.score,
        attempt_no=attempt.attempt_no,
        attempts_allowed=attempts_allowed,
        passed=passed,
        status=progress.status,
    )


@router.post('/admin/test-attempts/override', response_model=MessageOut)
def admin_override_test_attempts(
    payload: TestAttemptsOverrideRequest,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    progress = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == payload.enrollment_id,
            LessonProgress.lesson_id == payload.lesson_id,
        )
    ).scalar_one_or_none()
    if not progress:
        raise HTTPException(status_code=404, detail='Lesson progress not found')

    progress.extra_attempts_allowed += payload.extra_attempts
    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='test_attempts_override',
        entity_type='lesson_progress',
        entity_id=progress.id,
        payload={'extra_attempts': payload.extra_attempts, 'reason': payload.reason},
    )
    db.commit()
    return MessageOut(message='Test attempts override applied')


@router.get('/certificates/my', response_model=list[CertificateOut])
def my_certificates(
    ctx: AuthContext = Depends(require_roles(UserRole.student.value)),
    db: Session = Depends(get_db),
):
    student_id = _student_id_for_user(ctx)
    enrollments = db.execute(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.certification_issued_at.is_not(None),
        )
    ).scalars().all()
    return [
        CertificateOut(
            enrollment_id=item.id,
            certificate_url=item.certificate_url or f'/api/certificates/{item.id}/download',
            issued_at=item.certification_issued_at,
            certificate_number=item.certificate_number,
        )
        for item in enrollments
        if item.certification_issued_at is not None
    ]


@router.get('/certificates/{enrollment_id}/download', response_model=CertificateOut)
def download_certificate(
    enrollment_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    enrollment = db.get(Enrollment, enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')

    if not has_role(ctx, UserRole.admin.value):
        if not has_role(ctx, UserRole.student.value) or _student_id_for_user(ctx) != enrollment.student_id:
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    if enrollment.certification_issued_at is None or not enrollment.certificate_url:
        raise HTTPException(status_code=409, detail='Certificate is not available yet')

    return CertificateOut(
        enrollment_id=enrollment.id,
        certificate_url=enrollment.certificate_url,
        issued_at=enrollment.certification_issued_at,
        certificate_number=enrollment.certificate_number,
    )


@router.get('/groups/{group_id}/progress', response_model=GroupProgressResponse)
def group_progress(
    group_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _assert_can_view_student_data(ctx)
    allowed_group_ids = _allowed_group_ids(ctx, db)
    if not has_role(ctx, UserRole.admin.value) and group_id not in allowed_group_ids:
        raise HTTPException(status_code=403, detail='Forbidden for current role')

    group = db.execute(
        select(Group)
        .where(Group.id == group_id)
        .options(selectinload(Group.program), selectinload(Group.enrollments).selectinload(Enrollment.student))
    ).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail='Group not found')

    allowed_student_ids = _allowed_student_ids(ctx, db)
    enrollments = group.enrollments
    if not has_role(ctx, UserRole.admin.value):
        enrollments = [item for item in enrollments if item.student_id in allowed_student_ids]

    lesson_totals = _collect_program_lesson_totals(db, [group.program_id])
    enrollment_ids = [enrollment.id for enrollment in enrollments]
    completed_stats = _collect_completed_stats(db, enrollment_ids)
    last_login_map = _collect_student_last_login(db, [enrollment.student_id for enrollment in enrollments])

    rows: list[GroupProgressRow] = []
    for enrollment in enrollments:
        stat = completed_stats.get(enrollment.id, {'completed_count': 0, 'last_activity': None})
        metrics = enrollment_metrics(db, enrollment)
        rows.append(
            _build_progress_row(
                enrollment=enrollment,
                total_lessons=lesson_totals.get(group.program_id, 0),
                completed_count=int(stat['completed_count']),
                last_activity=stat['last_activity'] if isinstance(stat['last_activity'], datetime) else None,
                last_login_at=last_login_map.get(enrollment.student_id),
                average_score=float(metrics['avg_score']),
            )
        )

    rows.sort(key=lambda row: row.full_name)
    return GroupProgressResponse(group_id=group.id, rows=rows)


@router.get('/progress', response_model=ProgressTableResponse)
def list_progress(
    group_id: str | None = None,
    program_id: str | None = None,
    progress_status: Literal['not_started', 'in_progress', 'completed'] | None = None,
    search: str | None = None,
    sort_by: Literal['progress_percent', 'enrolled_at'] = 'progress_percent',
    sort_order: Literal['asc', 'desc'] = 'desc',
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _assert_can_view_student_data(ctx)
    allowed_group_ids = _allowed_group_ids(ctx, db)
    allowed_student_ids = _allowed_student_ids(ctx, db)

    if group_id and not has_role(ctx, UserRole.admin.value) and group_id not in allowed_group_ids:
        raise HTTPException(status_code=403, detail='Forbidden for current role')

    if program_id and not has_role(ctx, UserRole.admin.value):
        allowed_program_ids = _allowed_program_ids(ctx, db)
        if program_id not in allowed_program_ids:
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    enrollments = db.execute(
        select(Enrollment)
        .options(
            selectinload(Enrollment.student),
            selectinload(Enrollment.group).selectinload(Group.program),
        )
    ).scalars().all()

    if not has_role(ctx, UserRole.admin.value):
        enrollments = [enrollment for enrollment in enrollments if enrollment.group_id in allowed_group_ids]
        enrollments = [enrollment for enrollment in enrollments if enrollment.student_id in allowed_student_ids]

    if group_id:
        enrollments = [enrollment for enrollment in enrollments if enrollment.group_id == group_id]

    if program_id:
        enrollments = [enrollment for enrollment in enrollments if enrollment.group.program_id == program_id]

    program_ids = list({enrollment.group.program_id for enrollment in enrollments})
    lesson_totals = _collect_program_lesson_totals(db, program_ids)
    enrollment_ids = [enrollment.id for enrollment in enrollments]
    completed_stats = _collect_completed_stats(db, enrollment_ids)
    last_login_map = _collect_student_last_login(db, [enrollment.student_id for enrollment in enrollments])

    rows: list[GroupProgressRow] = []
    for enrollment in enrollments:
        stat = completed_stats.get(enrollment.id, {'completed_count': 0, 'last_activity': None})
        metrics = enrollment_metrics(db, enrollment)
        row = _build_progress_row(
            enrollment=enrollment,
            total_lessons=lesson_totals.get(enrollment.group.program_id, 0),
            completed_count=int(stat['completed_count']),
            last_activity=stat['last_activity'] if isinstance(stat['last_activity'], datetime) else None,
            last_login_at=last_login_map.get(enrollment.student_id),
            average_score=float(metrics['avg_score']),
        )
        rows.append(row)

    if progress_status:
        rows = [row for row in rows if row.progress_status == progress_status]

    if search:
        search_normalized = search.strip().lower()
        rows = [row for row in rows if search_normalized in row.full_name.lower()]

    if sort_by == 'enrolled_at':
        rows.sort(key=lambda row: row.enrolled_at, reverse=(sort_order == 'desc'))
    else:
        rows.sort(key=lambda row: row.progress_percent, reverse=(sort_order == 'desc'))

    return ProgressTableResponse(rows=rows)


@router.get('/analytics/executive')
def get_executive_dashboard(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.executive.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    return executive_dashboard(db, window)


@router.get('/analytics/admin')
def get_admin_dashboard(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    return admin_dashboard(db, window)


@router.get('/analytics/methodist')
def get_methodist_dashboard(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    return methodist_dashboard(db, window)


@router.get('/analytics/curator')
def get_curator_dashboard(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.curator.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    group_ids = _curator_group_ids(db, ctx.user.id)
    return curator_dashboard(db, user_id=ctx.user.id, group_ids=group_ids, window=window)


@router.get('/analytics/teacher')
def get_teacher_dashboard(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.teacher.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    group_ids = _teacher_group_ids(db, ctx.user.id)
    return teacher_dashboard(db, user_id=ctx.user.id, group_ids=group_ids, window=window)


@router.get('/analytics/customer')
def get_customer_dashboard(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.customer.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    student_ids = _customer_student_ids(db, ctx.user.id)
    return customer_dashboard(db, student_ids=student_ids, window=window)


@router.get('/analytics/executive/program-completion.xlsx')
def export_executive_program_completion(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.executive.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = executive_dashboard(db, window)
    rows = [
        [
            item['program_name'],
            item['enrolled'],
            item['completed'],
            item['dropped'],
            item['completion_percent'],
            item['average_score'],
        ]
        for item in payload.get('program_completion', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Executive completion',
        headers=['Программа', 'Зачислено', 'Завершило', 'Отчислилось', 'Завершаемость %', 'Средний балл'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'executive-program-completion.xlsx')


@router.get('/analytics/admin/groups.xlsx')
def export_admin_groups(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = admin_dashboard(db, window)
    rows = [
        [
            item['group_name'],
            item['program_name'],
            item['end_date'],
            item['students_count'],
            item['completion_percent'],
            item['status'],
        ]
        for item in payload.get('groups', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Admin groups',
        headers=['Группа', 'Программа', 'Дата окончания', 'Слушателей', 'Завершение %', 'Статус'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'admin-groups.xlsx')


@router.get('/analytics/admin/inactive-students.xlsx')
def export_admin_inactive_students(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = admin_dashboard(db, window)
    rows = [
        [
            item['full_name'],
            item['program_name'],
            item['group_name'],
            item['progress_percent'],
            item['last_login_at'],
        ]
        for item in payload.get('inactive_students', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Inactive students',
        headers=['ФИО', 'Программа', 'Группа', 'Прогресс %', 'Последний вход'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'admin-inactive-students.xlsx')


@router.get('/analytics/admin/delayed-reviews.xlsx')
def export_admin_delayed_reviews(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = admin_dashboard(db, window)
    rows = [
        [
            item['student_name'],
            item['group_name'],
            item['lesson_title'],
            item['teacher_name'],
            item['submitted_at'],
            item['waiting_days'],
        ]
        for item in payload.get('delayed_reviews', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Delayed reviews',
        headers=['Слушатель', 'Группа', 'Урок', 'Преподаватель', 'Поступило', 'Ожидает дней'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'admin-delayed-reviews.xlsx')


@router.get('/analytics/admin/integration-errors.xlsx')
def export_admin_integration_errors(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = admin_dashboard(db, window)
    rows = [
        [
            item['service'],
            item['operation'],
            item['error_text'],
            item['created_at'],
        ]
        for item in payload.get('integration_errors', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Integration errors',
        headers=['Сервис', 'Операция', 'Ошибка', 'Дата'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'admin-integration-errors.xlsx')


@router.get('/analytics/methodist/programs.xlsx')
def export_methodist_programs(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = methodist_dashboard(db, window)
    rows = [
        [
            item['program_name'],
            item['groups_count'],
            item['enrollments_count'],
            item['average_score'],
            item['average_progress_percent'],
            item['average_duration_days'],
        ]
        for item in payload.get('program_metrics', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Program metrics',
        headers=['Программа', 'Групп', 'Слушателей', 'Средний балл', 'Средний прогресс %', 'Средняя длительность, дни'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'methodist-programs.xlsx')


@router.get('/analytics/methodist/problem-lessons.xlsx')
def export_methodist_problem_lessons(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = methodist_dashboard(db, window)
    rows = [
        [
            item['program_name'],
            item['module_title'],
            item['lesson_title'],
            item['repeat_attempts'],
            item['failed_checks'],
            item['avg_stuck_days'],
        ]
        for item in payload.get('problem_lessons', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Problem lessons',
        headers=['Программа', 'Модуль', 'Урок', 'Повторных попыток', 'Незачётов', 'Средняя задержка, дни'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'methodist-problem-lessons.xlsx')


@router.get('/analytics/methodist/funnel.xlsx')
def export_methodist_funnel(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _ctx: AuthContext = Depends(require_roles(UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = methodist_dashboard(db, window)
    rows = [
        [
            item['program_name'],
            item['module_title'],
            item['reached_count'],
        ]
        for item in payload.get('program_funnel', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Program funnel',
        headers=['Программа', 'Модуль', 'Дошли до модуля'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'methodist-funnel.xlsx')


@router.get('/analytics/curator/students.xlsx')
def export_curator_students(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.curator.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = curator_dashboard(db, user_id=ctx.user.id, group_ids=_curator_group_ids(db, ctx.user.id), window=window)
    rows = [
        [
            item['full_name'],
            item['program_name'],
            item['group_name'],
            item['progress_percent'],
            item['last_login_at'],
            item['current_lesson'],
            item['signal'],
            item['days_left'],
        ]
        for item in payload.get('students', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Curator students',
        headers=['ФИО', 'Программа', 'Группа', 'Прогресс %', 'Последний вход', 'Текущий урок', 'Светофор', 'Дней до конца'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'curator-students.xlsx')


@router.get('/analytics/curator/reminders.xlsx')
def export_curator_reminders(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.curator.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = curator_dashboard(db, user_id=ctx.user.id, group_ids=_curator_group_ids(db, ctx.user.id), window=window)
    rows = [
        [
            item['student_name'],
            item['message'],
            item['sent_at'],
            'Да' if item['effect'] else 'Нет',
        ]
        for item in payload.get('reminders', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Curator reminders',
        headers=['Слушатель', 'Напоминание', 'Отправлено', 'Был эффект'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'curator-reminders.xlsx')


@router.get('/analytics/teacher/courses.xlsx')
def export_teacher_courses(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.teacher.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = teacher_dashboard(db, user_id=ctx.user.id, group_ids=_teacher_group_ids(db, ctx.user.id), window=window)
    rows = [
        [
            item['program_name'],
            item['group_name'],
            item['average_score'],
        ]
        for item in payload.get('courses', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Teacher courses',
        headers=['Программа', 'Группа', 'Средний балл'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'teacher-courses.xlsx')


@router.get('/analytics/teacher/review-queue.xlsx')
def export_teacher_review_queue(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.teacher.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = teacher_dashboard(db, user_id=ctx.user.id, group_ids=_teacher_group_ids(db, ctx.user.id), window=window)
    rows = [
        [
            item['student_name'],
            item['group_name'],
            item['lesson_title'],
            item['submitted_at'],
        ]
        for item in payload.get('review_queue', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Review queue',
        headers=['Слушатель', 'Группа', 'Урок', 'Поступило'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'teacher-review-queue.xlsx')


@router.get('/analytics/customer/employees.xlsx')
def export_customer_employees(
    period: PeriodPreset = '30d',
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ctx: AuthContext = Depends(require_roles(UserRole.customer.value)),
    db: Session = Depends(get_db),
):
    window = _analytics_window(period=period, date_from=date_from, date_to=date_to)
    payload = customer_dashboard(db, student_ids=_customer_student_ids(db, ctx.user.id), window=window)
    rows = [
        [
            item['full_name'],
            item['program_name'],
            item['group_name'],
            item['progress_percent'],
            item['status'],
            item['last_login_at'],
        ]
        for item in payload.get('employees', [])
    ]
    xlsx = _build_excel_bytes(
        sheet_title='Customer employees',
        headers=['ФИО', 'Программа', 'Группа', 'Прогресс %', 'Статус', 'Последний вход'],
        rows=rows,
    )
    return _xlsx_response(xlsx, 'customer-employees.xlsx')


@router.get('/reports/groups/{group_id}/final.xlsx')
def export_group_final_report(
    group_id: str,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    group = db.execute(
        select(Group)
        .where(Group.id == group_id)
        .options(
            selectinload(Group.program),
            selectinload(Group.enrollments).selectinload(Enrollment.student),
        )
    ).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail='Group not found')

    total_lessons = _collect_program_lesson_totals(db, [group.program_id]).get(group.program_id, 0)
    excel_rows: list[list[object | None]] = []
    for enrollment in sorted(group.enrollments, key=lambda item: item.student.full_name):
        progress_percent, avg_score, _completed = enrollment_score_stats(
            db,
            enrollment.id,
            total_lessons=total_lessons,
        )
        excel_rows.append(
            [
                enrollment.student.full_name,
                enrollment.student.organization,
                progress_percent,
                avg_score,
                enrollment.certification_issued_at.isoformat() if enrollment.certification_issued_at else None,
                enrollment.certificate_number,
            ]
        )

    xlsx = _build_excel_bytes(
        sheet_title='Group report',
        headers=[
            'ФИО слушателя',
            'Организация',
            'Прогресс %',
            'Средний балл',
            'Дата завершения',
            'Номер сертификата',
        ],
        rows=excel_rows,
    )
    file_name = f'group-{group.id}-final-report.xlsx'
    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='report_exported',
        entity_type='group',
        entity_id=group.id,
        payload={'report': 'final_xlsx'},
    )
    db.commit()
    return Response(
        content=xlsx,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={file_name}'},
    )


@router.get('/reports/customers/me/final.xlsx')
def export_customer_final_report(
    ctx: AuthContext = Depends(require_roles(UserRole.customer.value)),
    db: Session = Depends(get_db),
):
    student_ids = _customer_student_ids(db, ctx.user.id)
    if not student_ids:
        xlsx = _build_excel_bytes(
            sheet_title='Customer report',
            headers=[
                'ФИО слушателя',
                'Организация',
                'Прогресс %',
                'Средний балл',
                'Дата завершения',
                'Номер сертификата',
            ],
            rows=[],
        )
        return Response(
            content=xlsx,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename=customer-final-report.xlsx'},
        )

    enrollments = db.execute(
        select(Enrollment)
        .where(Enrollment.student_id.in_(student_ids))
        .options(
            selectinload(Enrollment.student),
            selectinload(Enrollment.group).selectinload(Group.program),
        )
    ).scalars().all()

    lesson_totals = _collect_program_lesson_totals(db, list({item.group.program_id for item in enrollments}))
    report_rows: list[GroupFinalReportRow] = []
    for enrollment in enrollments:
        progress_percent, avg_score, _completed = enrollment_score_stats(
            db,
            enrollment.id,
            total_lessons=lesson_totals.get(enrollment.group.program_id, 0),
        )
        report_rows.append(
            GroupFinalReportRow(
                full_name=enrollment.student.full_name,
                organization=enrollment.student.organization,
                progress_percent=progress_percent,
                average_score=avg_score,
                completion_date=enrollment.certification_issued_at,
                certificate_number=enrollment.certificate_number,
            )
        )
    report_rows.sort(key=lambda item: item.full_name)

    xlsx = _build_excel_bytes(
        sheet_title='Customer report',
        headers=[
            'ФИО слушателя',
            'Организация',
            'Прогресс %',
            'Средний балл',
            'Дата завершения',
            'Номер сертификата',
        ],
        rows=[
            [
                item.full_name,
                item.organization,
                item.progress_percent,
                item.average_score,
                item.completion_date.isoformat() if item.completion_date else None,
                item.certificate_number,
            ]
            for item in report_rows
        ],
    )
    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='report_exported',
        entity_type='customer',
        entity_id=ctx.user.id,
        payload={'report': 'customer_final_xlsx', 'rows': len(report_rows)},
    )
    db.commit()
    return Response(
        content=xlsx,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=customer-final-report.xlsx'},
    )


@router.get('/reports/customers/me/final', response_model=CustomerFinalReportResponse)
def get_customer_final_report(
    ctx: AuthContext = Depends(require_roles(UserRole.customer.value)),
    db: Session = Depends(get_db),
):
    student_ids = _customer_student_ids(db, ctx.user.id)
    if not student_ids:
        return CustomerFinalReportResponse(rows=[])

    enrollments = db.execute(
        select(Enrollment)
        .where(Enrollment.student_id.in_(student_ids))
        .options(
            selectinload(Enrollment.student),
            selectinload(Enrollment.group).selectinload(Group.program),
        )
    ).scalars().all()

    lesson_totals = _collect_program_lesson_totals(db, list({item.group.program_id for item in enrollments}))
    rows: list[GroupFinalReportRow] = []
    for enrollment in enrollments:
        progress_percent, avg_score, _completed = enrollment_score_stats(
            db,
            enrollment.id,
            total_lessons=lesson_totals.get(enrollment.group.program_id, 0),
        )
        rows.append(
            GroupFinalReportRow(
                full_name=enrollment.student.full_name,
                organization=enrollment.student.organization,
                progress_percent=progress_percent,
                average_score=avg_score,
                completion_date=enrollment.certification_issued_at,
                certificate_number=enrollment.certificate_number,
            )
        )
    rows.sort(key=lambda item: item.full_name)
    return CustomerFinalReportResponse(rows=rows)


@router.get('/reports/programs/{program_id}/stats', response_model=ProgramStatsReportOut)
def get_program_stats_report(
    program_id: str,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.methodist.value)),
    db: Session = Depends(get_db),
):
    program = db.execute(
        select(Program)
        .where(Program.id == program_id)
        .options(selectinload(Program.groups).selectinload(Group.enrollments))
    ).scalar_one_or_none()
    if not program:
        raise HTTPException(status_code=404, detail='Program not found')

    lesson_total = _collect_program_lesson_totals(db, [program.id]).get(program.id, 0)
    enrollments = [enrollment for group in program.groups for enrollment in group.enrollments]
    completion_values: list[float] = []
    score_values: list[float] = []
    for enrollment in enrollments:
        progress_percent, avg_score, _completed = enrollment_score_stats(
            db,
            enrollment.id,
            total_lessons=lesson_total,
        )
        completion_values.append(progress_percent)
        score_values.append(avg_score)

    groups_completed = 0
    for group in program.groups:
        if group.enrollments and all(item.program_status.value == 'completed' for item in group.enrollments):
            groups_completed += 1

    problem_lessons = lesson_problem_stats(db, program.id)
    return ProgramStatsReportOut(
        program_id=program.id,
        program_name=program.name,
        groups_completed=groups_completed,
        average_score=round(sum(score_values) / len(score_values), 2) if score_values else 0.0,
        average_completion_percent=round(sum(completion_values) / len(completion_values), 2)
        if completion_values
        else 0.0,
        problem_lessons=problem_lessons,
    )


@router.post('/assignments', response_model=AssignmentOut, status_code=201)
def submit_assignment(
    payload: AssignmentSubmitRequest,
    ctx: AuthContext = Depends(require_roles(UserRole.student.value)),
    db: Session = Depends(get_db),
):
    student_id = _student_id_for_user(ctx)
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.group_id == payload.group_id, Enrollment.student_id == student_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program), selectinload(Enrollment.student))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')
    if enrollment.group.program.is_paid and enrollment.payment_status != PaymentStatus.paid:
        raise HTTPException(status_code=402, detail='Payment is required before assignment submission')

    lesson_with_module = db.execute(
        select(Lesson, Module)
        .join(Module, Module.id == Lesson.module_id)
        .where(Lesson.id == payload.lesson_id)
    ).first()
    if not lesson_with_module:
        raise HTTPException(status_code=404, detail='Lesson not found')

    lesson, module = lesson_with_module
    if module.program_id != enrollment.group.program_id:
        raise HTTPException(status_code=422, detail='Lesson is not part of enrollment program')
    if lesson.type.value != 'assignment':
        raise HTTPException(status_code=422, detail='Assignment submission is allowed only for practical assignment lessons')

    pending = db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.enrollment_id == enrollment.id,
            AssignmentSubmission.lesson_id == lesson.id,
            AssignmentSubmission.status == AssignmentStatus.submitted,
        )
    ).scalar_one_or_none()
    if pending:
        raise HTTPException(status_code=409, detail='Previous submission is still awaiting review')

    before_progress = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == lesson.id,
        )
    ).scalar_one_or_none()
    before_status = before_progress.status.value if before_progress else ProgressStatus.not_started.value
    progress = set_assignment_waiting(db, enrollment, lesson)
    text_payload = payload.submission_text.encode('utf-8')
    try:
        stored = upload_bytes(
            key_prefix=f'assignments/{enrollment.id}/{lesson.id}',
            file_name='submission.txt',
            data=text_payload,
            content_type='text/plain',
        )
    except Exception as exc:
        log_integration_error(
            db,
            service='storage',
            operation='upload_assignment_text',
            error_text=str(exc),
            context={'enrollment_id': enrollment.id, 'lesson_id': lesson.id},
            user_id=ctx.user.id,
        )
        raise HTTPException(status_code=503, detail='Assignment storage is temporarily unavailable') from exc

    submission = AssignmentSubmission(
        enrollment_id=enrollment.id,
        lesson_id=lesson.id,
        submission_text=payload.submission_text,
        status=AssignmentStatus.submitted,
        file_key=str(stored['key']),
        file_name=str(stored['file_name']),
        file_mime=str(stored['content_type']),
        file_size_bytes=int(stored['size_bytes']),
    )
    db.add(submission)
    db.flush()
    update_program_status_and_certificate(db, enrollment)

    teacher_ids = db.execute(
        select(TeacherGroupLink.user_id).where(TeacherGroupLink.group_id == enrollment.group_id)
    ).all()
    for (teacher_id,) in teacher_ids:
        create_notification(
            db,
            recipient_user_id=teacher_id,
            subject='Новое задание на проверку',
            body=f'{enrollment.student.full_name}: урок "{lesson.title}".',
            link_url=f'/assignments/{submission.id}',
            event_key=f'new-assignment-{submission.id}-{teacher_id}',
            channels=(NotificationChannel.in_app, NotificationChannel.email),
        )

    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='assignment_submitted',
        entity_type='assignment_submission',
        entity_id=submission.id,
        payload={'lesson_id': lesson.id, 'enrollment_id': enrollment.id},
    )
    if progress.status.value != before_status:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='lesson_status_changed',
            entity_type='lesson_progress',
            entity_id=progress.id,
            from_status=before_status,
            to_status=progress.status.value,
            payload={'lesson_id': lesson.id, 'enrollment_id': enrollment.id},
        )

    db.commit()

    submission = db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.id == submission.id)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.student),
            selectinload(AssignmentSubmission.enrollment)
            .selectinload(Enrollment.group)
            .selectinload(Group.program),
            selectinload(AssignmentSubmission.lesson),
        )
    ).scalar_one()
    return _assignment_out(submission)


@router.post('/assignments/upload', response_model=AssignmentOut, status_code=201)
async def submit_assignment_file(
    group_id: str = Form(...),
    lesson_id: str = Form(...),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_roles(UserRole.student.value)),
    db: Session = Depends(get_db),
):
    student_id = _student_id_for_user(ctx)
    enrollment = db.execute(
        select(Enrollment)
        .where(Enrollment.group_id == group_id, Enrollment.student_id == student_id)
        .options(selectinload(Enrollment.group).selectinload(Group.program), selectinload(Enrollment.student))
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')
    if enrollment.group.program.is_paid and enrollment.payment_status != PaymentStatus.paid:
        raise HTTPException(status_code=402, detail='Payment is required before assignment submission')

    lesson_with_module = db.execute(
        select(Lesson, Module)
        .join(Module, Module.id == Lesson.module_id)
        .where(Lesson.id == lesson_id)
    ).first()
    if not lesson_with_module:
        raise HTTPException(status_code=404, detail='Lesson not found')
    lesson, module = lesson_with_module
    if module.program_id != enrollment.group.program_id:
        raise HTTPException(status_code=422, detail='Lesson is not part of enrollment program')
    if lesson.type.value != 'assignment':
        raise HTTPException(status_code=422, detail='Assignment submission is allowed only for practical assignment lessons')

    pending = db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.enrollment_id == enrollment.id,
            AssignmentSubmission.lesson_id == lesson.id,
            AssignmentSubmission.status == AssignmentStatus.submitted,
        )
    ).scalar_one_or_none()
    if pending:
        raise HTTPException(status_code=409, detail='Previous submission is still awaiting review')

    file_bytes = await file.read()
    if len(file_bytes) > ASSIGNMENT_MAX_SIZE_BYTES:
        raise HTTPException(status_code=422, detail='File is too large (max 50 MB)')
    allowed, reason = is_assignment_file_allowed(file.filename or 'file', file.content_type or '', len(file_bytes))
    if not allowed:
        raise HTTPException(status_code=422, detail=reason)

    before_progress = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == lesson.id,
        )
    ).scalar_one_or_none()
    before_status = before_progress.status.value if before_progress else ProgressStatus.not_started.value
    progress = set_assignment_waiting(db, enrollment, lesson)

    try:
        stored = upload_bytes(
            key_prefix=f'assignments/{enrollment.id}/{lesson.id}',
            file_name=file.filename or 'submission.bin',
            data=file_bytes,
            content_type=file.content_type or 'application/octet-stream',
        )
    except Exception as exc:
        log_integration_error(
            db,
            service='storage',
            operation='upload_assignment_file',
            error_text=str(exc),
            context={'enrollment_id': enrollment.id, 'lesson_id': lesson.id, 'file_name': file.filename},
            user_id=ctx.user.id,
        )
        raise HTTPException(status_code=503, detail='Assignment storage is temporarily unavailable') from exc

    submission = AssignmentSubmission(
        enrollment_id=enrollment.id,
        lesson_id=lesson.id,
        submission_text=note or 'Файл загружен',
        status=AssignmentStatus.submitted,
        file_key=str(stored['key']),
        file_name=str(stored['file_name']),
        file_mime=str(stored['content_type']),
        file_size_bytes=int(stored['size_bytes']),
    )
    db.add(submission)
    db.flush()
    update_program_status_and_certificate(db, enrollment)

    teacher_ids = db.execute(
        select(TeacherGroupLink.user_id).where(TeacherGroupLink.group_id == enrollment.group_id)
    ).all()
    for (teacher_id,) in teacher_ids:
        create_notification(
            db,
            recipient_user_id=teacher_id,
            subject='Новое задание на проверку',
            body=f'{enrollment.student.full_name}: урок "{lesson.title}".',
            link_url=f'/assignments/{submission.id}',
            event_key=f'new-assignment-{submission.id}-{teacher_id}',
            channels=(NotificationChannel.in_app, NotificationChannel.email),
        )

    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='assignment_submitted',
        entity_type='assignment_submission',
        entity_id=submission.id,
        payload={'lesson_id': lesson.id, 'enrollment_id': enrollment.id, 'file_name': file.filename},
    )
    if progress.status.value != before_status:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='lesson_status_changed',
            entity_type='lesson_progress',
            entity_id=progress.id,
            from_status=before_status,
            to_status=progress.status.value,
            payload={'lesson_id': lesson.id, 'enrollment_id': enrollment.id},
        )

    db.commit()
    submission = db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.id == submission.id)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.student),
            selectinload(AssignmentSubmission.enrollment)
            .selectinload(Enrollment.group)
            .selectinload(Group.program),
            selectinload(AssignmentSubmission.lesson),
        )
    ).scalar_one()
    return _assignment_out(submission)


@router.get('/assignments/my', response_model=list[AssignmentOut])
def list_my_assignments(
    ctx: AuthContext = Depends(require_roles(UserRole.student.value)),
    db: Session = Depends(get_db),
):
    student_id = _student_id_for_user(ctx)
    rows = db.execute(
        select(AssignmentSubmission)
        .join(Enrollment, Enrollment.id == AssignmentSubmission.enrollment_id)
        .where(Enrollment.student_id == student_id)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.student),
            selectinload(AssignmentSubmission.enrollment)
            .selectinload(Enrollment.group)
            .selectinload(Group.program),
            selectinload(AssignmentSubmission.lesson),
        )
    ).scalars().all()

    changed = False
    for item in rows:
        if item.status in {AssignmentStatus.reviewed, AssignmentStatus.returned_for_revision} and item.student_viewed_at is None:
            item.student_viewed_at = _utcnow()
            changed = True
    if changed:
        db.commit()

    rows.sort(key=lambda item: item.submitted_at, reverse=True)
    return [_assignment_out(item) for item in rows]


@router.get('/assignments/review-queue', response_model=list[AssignmentOut])
def list_review_queue(
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.teacher.value)),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.status == AssignmentStatus.submitted)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.student),
            selectinload(AssignmentSubmission.enrollment)
            .selectinload(Enrollment.group)
            .selectinload(Group.program),
            selectinload(AssignmentSubmission.lesson),
        )
    ).scalars().all()

    if has_role(ctx, UserRole.teacher.value) and not has_role(ctx, UserRole.admin.value):
        teacher_groups = _teacher_group_ids(db, ctx.user.id)
        rows = [item for item in rows if item.enrollment.group_id in teacher_groups]

    rows.sort(key=lambda item: item.submitted_at, reverse=False)
    return [_assignment_out(item) for item in rows]


@router.post('/assignments/{assignment_id}/review', response_model=AssignmentOut)
def review_assignment(
    assignment_id: str,
    payload: AssignmentReviewRequest,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.teacher.value)),
    db: Session = Depends(get_db),
):
    item = db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.id == assignment_id)
        .options(
            selectinload(AssignmentSubmission.enrollment).selectinload(Enrollment.student),
            selectinload(AssignmentSubmission.enrollment)
            .selectinload(Enrollment.group)
            .selectinload(Group.program),
            selectinload(AssignmentSubmission.lesson),
        )
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail='Assignment not found')

    if has_role(ctx, UserRole.teacher.value) and not has_role(ctx, UserRole.admin.value):
        teacher_groups = _teacher_group_ids(db, ctx.user.id)
        if item.enrollment.group_id not in teacher_groups:
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    if item.student_viewed_at is not None and not has_role(ctx, UserRole.admin.value):
        raise HTTPException(status_code=409, detail='Teacher cannot change grade after student has seen it')
    if item.student_viewed_at is not None and has_role(ctx, UserRole.admin.value) and not payload.override_reason:
        raise HTTPException(status_code=422, detail='Admin override requires reason')

    progress_before = db.execute(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == item.enrollment_id,
            LessonProgress.lesson_id == item.lesson_id,
        )
    ).scalar_one_or_none()
    before_status = progress_before.status.value if progress_before else ProgressStatus.not_started.value
    assignment_before = item.status.value

    returned_for_revision = payload.return_for_revision or payload.grade is None
    if payload.grade is not None:
        pass_score = float(item.lesson.content_json.get('assignment_pass_score', 60.0))
        if payload.grade < pass_score:
            returned_for_revision = True

    item.grade = payload.grade
    item.teacher_comment = payload.teacher_comment
    item.status = AssignmentStatus.returned_for_revision if returned_for_revision else AssignmentStatus.reviewed
    item.reviewed_by_user_id = ctx.user.id
    item.reviewed_at = _utcnow()
    item.override_reason = payload.override_reason

    progress = set_assignment_result(
        db,
        item.enrollment,
        item.lesson,
        grade=payload.grade,
        returned_for_revision=returned_for_revision,
    )
    issued_now = update_program_status_and_certificate(db, item.enrollment)

    student_user = db.execute(
        select(User).join(UserStudentLink, UserStudentLink.user_id == User.id).where(UserStudentLink.student_id == item.enrollment.student_id)
    ).scalar_one_or_none()
    if student_user:
        if returned_for_revision:
            create_notification(
                db,
                recipient_user_id=student_user.id,
                subject='Задание возвращено на доработку',
                body=f'Комментарий преподавателя: {payload.teacher_comment or "требуются доработки"}',
                link_url=f'/assignments/{item.id}',
                event_key=f'assignment-returned-{item.id}-{item.reviewed_at.date().isoformat()}',
            )
        else:
            create_notification(
                db,
                recipient_user_id=student_user.id,
                subject='Задание проверено',
                body=f'Оценка: {payload.grade}. Комментарий: {payload.teacher_comment or "без комментария"}',
                link_url=f'/assignments/{item.id}',
                event_key=f'assignment-reviewed-{item.id}-{item.reviewed_at.date().isoformat()}',
            )

    if issued_now and student_user:
        create_notification(
            db,
            recipient_user_id=student_user.id,
            subject='Сертификат доступен',
            body='Условия сертификации выполнены. Сертификат готов к скачиванию.',
            link_url=item.enrollment.certificate_url,
            event_key=f'certificate-issued-{item.enrollment.id}',
        )
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='certificate_issued',
            entity_type='enrollment',
            entity_id=item.enrollment.id,
            payload={'certificate_url': item.enrollment.certificate_url},
        )

    if assignment_before != item.status.value:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='assignment_status_changed',
            entity_type='assignment_submission',
            entity_id=item.id,
            from_status=assignment_before,
            to_status=item.status.value,
            payload={'grade': payload.grade, 'comment': payload.teacher_comment},
        )
    if progress.status.value != before_status:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='lesson_status_changed',
            entity_type='lesson_progress',
            entity_id=progress.id,
            from_status=before_status,
            to_status=progress.status.value,
            payload={'lesson_id': item.lesson_id, 'enrollment_id': item.enrollment_id},
        )
    if item.student_viewed_at is not None and payload.override_reason:
        log_audit(
            db,
            actor_user_id=ctx.user.id,
            event_type='grade_override_by_admin',
            entity_type='assignment_submission',
            entity_id=item.id,
            payload={'reason': payload.override_reason},
        )

    db.commit()
    db.refresh(item)
    return _assignment_out(item)


@router.post('/questions', response_model=QuestionOut, status_code=201)
def create_question(
    payload: QuestionCreateRequest,
    ctx: AuthContext = Depends(require_roles(UserRole.student.value)),
    db: Session = Depends(get_db),
):
    student_id = _student_id_for_user(ctx)
    enrollment = db.execute(
        select(Enrollment).where(Enrollment.group_id == payload.group_id, Enrollment.student_id == student_id)
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail='Enrollment not found')

    question = StudentQuestion(student_id=student_id, group_id=payload.group_id, question_text=payload.question_text)
    db.add(question)
    db.commit()

    question = db.execute(
        select(StudentQuestion)
        .where(StudentQuestion.id == question.id)
        .options(selectinload(StudentQuestion.student), selectinload(StudentQuestion.group))
    ).scalar_one()
    return _question_out(question)


@router.get('/questions', response_model=list[QuestionOut])
def list_questions(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    if not any(
        has_role(ctx, role)
        for role in (UserRole.admin.value, UserRole.curator.value, UserRole.student.value)
    ):
        raise HTTPException(status_code=403, detail='Forbidden for current role')

    rows = db.execute(
        select(StudentQuestion)
        .options(selectinload(StudentQuestion.student), selectinload(StudentQuestion.group))
    ).scalars().all()

    if has_role(ctx, UserRole.student.value) and not has_role(ctx, UserRole.admin.value):
        rows = [item for item in rows if item.student_id == _student_id_for_user(ctx)]
    elif has_role(ctx, UserRole.curator.value) and not has_role(ctx, UserRole.admin.value):
        curator_groups = _curator_group_ids(db, ctx.user.id)
        rows = [item for item in rows if item.group_id in curator_groups]

    rows.sort(key=lambda item: item.created_at, reverse=True)
    return [_question_out(item) for item in rows]


@router.post('/questions/{question_id}/answer', response_model=QuestionOut)
def answer_question(
    question_id: str,
    payload: QuestionAnswerRequest,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.curator.value)),
    db: Session = Depends(get_db),
):
    question = db.execute(
        select(StudentQuestion)
        .where(StudentQuestion.id == question_id)
        .options(selectinload(StudentQuestion.student), selectinload(StudentQuestion.group))
    ).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail='Question not found')

    if has_role(ctx, UserRole.curator.value) and not has_role(ctx, UserRole.admin.value):
        curator_groups = _curator_group_ids(db, ctx.user.id)
        if question.group_id not in curator_groups:
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    question.answer_text = payload.answer_text
    question.answered_at = _utcnow()
    question.answered_by_user_id = ctx.user.id
    db.commit()
    db.refresh(question)
    return _question_out(question)


@router.post('/reminders', response_model=ReminderOut, status_code=201)
def send_reminder(
    payload: ReminderSendRequest,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value, UserRole.curator.value)),
    db: Session = Depends(get_db),
):
    student = db.get(Student, payload.student_id)
    if not student:
        raise HTTPException(status_code=404, detail='Student not found')

    if has_role(ctx, UserRole.curator.value) and not has_role(ctx, UserRole.admin.value):
        curator_groups = _curator_group_ids(db, ctx.user.id)
        student_groups = _group_ids_for_student(db, student.id)
        if not curator_groups.intersection(student_groups):
            raise HTTPException(status_code=403, detail='Forbidden for current role')

    item = ReminderLog(student_id=student.id, curator_user_id=ctx.user.id, message=payload.message)
    db.add(item)
    db.commit()
    db.refresh(item)
    return ReminderOut(
        id=item.id,
        student_id=student.id,
        student_name=student.full_name,
        curator_user_id=item.curator_user_id,
        message=item.message,
        sent_at=item.sent_at,
    )


@router.get('/reminders', response_model=list[ReminderOut])
def list_reminders(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    if not any(
        has_role(ctx, role)
        for role in (UserRole.admin.value, UserRole.curator.value, UserRole.student.value)
    ):
        raise HTTPException(status_code=403, detail='Forbidden for current role')

    rows = db.execute(
        select(ReminderLog).options(selectinload(ReminderLog.student))
    ).scalars().all()

    if has_role(ctx, UserRole.student.value) and not has_role(ctx, UserRole.admin.value):
        rows = [item for item in rows if item.student_id == _student_id_for_user(ctx)]
    elif has_role(ctx, UserRole.curator.value) and not has_role(ctx, UserRole.admin.value):
        rows = [item for item in rows if item.curator_user_id == ctx.user.id]

    rows.sort(key=lambda item: item.sent_at, reverse=True)
    return [
        ReminderOut(
            id=item.id,
            student_id=item.student_id,
            student_name=item.student.full_name,
            curator_user_id=item.curator_user_id,
            message=item.message,
            sent_at=item.sent_at,
        )
        for item in rows
    ]


@router.get('/notifications', response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    channel: NotificationChannel | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    query = select(Notification).where(Notification.recipient_user_id == ctx.user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    if channel is not None:
        query = query.where(Notification.channel == channel)

    rows = db.execute(query).scalars().all()
    rows.sort(key=lambda item: item.created_at, reverse=True)
    return [_notification_out(item) for item in rows]


@router.post('/notifications/mark-read', response_model=MessageOut)
def mark_notifications_read(
    payload: NotificationMarkReadRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    query = select(Notification).where(Notification.recipient_user_id == ctx.user.id)
    if payload.notification_ids:
        query = query.where(Notification.id.in_(payload.notification_ids))

    rows = db.execute(query).scalars().all()
    for item in rows:
        item.is_read = True
    db.commit()
    return MessageOut(message=f'Marked {len(rows)} notifications as read')


@router.get('/integrations/errors', response_model=list[IntegrationErrorOut])
def list_integration_errors(
    service: str | None = None,
    limit: int = 200,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    safe_limit = min(max(limit, 1), 500)
    query = select(IntegrationErrorLog)
    if service:
        query = query.where(IntegrationErrorLog.service == service)
    rows = db.execute(query).scalars().all()
    rows.sort(key=lambda item: item.created_at, reverse=True)
    return [
        IntegrationErrorOut(
            id=item.id,
            service=item.service,
            operation=item.operation,
            error_text=item.error_text,
            context_json=item.context_json,
            user_id=item.user_id,
            created_at=item.created_at,
        )
        for item in rows[:safe_limit]
    ]


@router.get('/audit/events', response_model=list[AuditEventOut])
def list_audit_events(
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 200,
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    safe_limit = min(max(limit, 1), 500)
    query = select(AuditEvent)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)

    rows = db.execute(query).scalars().all()
    rows.sort(key=lambda item: item.created_at, reverse=True)
    return [_audit_out(item) for item in rows[:safe_limit]]


@router.post('/automation/run', response_model=AutomationRunResult)
def run_automation(
    ctx: AuthContext = Depends(require_roles(UserRole.admin.value)),
    db: Session = Depends(get_db),
):
    generated_notifications = run_scheduled_notifications(db)
    log_audit(
        db,
        actor_user_id=ctx.user.id,
        event_type='automation_notifications_run',
        entity_type='notifications',
        entity_id='scheduler',
        payload={'generated_notifications': generated_notifications},
    )
    db.commit()
    return AutomationRunResult(generated_notifications=generated_notifications, generated_events=1)
