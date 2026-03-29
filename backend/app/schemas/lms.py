from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.enums import (
    AssignmentStatus,
    LessonType,
    NotificationChannel,
    PaymentStatus,
    ProgressStatus,
    UserRole,
)


class ProgramCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    strict_order: bool = True
    certification_progress_threshold: float = Field(default=100.0, ge=0, le=100)
    certification_min_avg_score: float = Field(default=60.0, ge=0, le=100)
    is_paid: bool = False
    price_amount: float | None = Field(default=None, ge=0)


class ProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    created_at: datetime
    status: Literal['draft', 'active', 'archived'] = 'draft'
    strict_order: bool = True
    certification_progress_threshold: float = 100.0
    certification_min_avg_score: float = 60.0
    is_paid: bool = False
    price_amount: float | None = None


class ModuleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    order_index: int = Field(ge=0)


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    program_id: str
    title: str
    order_index: int


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    type: LessonType
    order_index: int = Field(ge=0)
    video_url: HttpUrl | None = None
    text_body: str | None = None
    questions_json: dict | None = None
    test_pass_score: float = Field(default=60.0, ge=0, le=100)
    test_max_attempts: int = Field(default=3, ge=1, le=50)
    assignment_pass_score: float = Field(default=60.0, ge=0, le=100)
    webinar_start_at: datetime | None = None
    webinar_join_url: HttpUrl | None = None


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    module_id: str
    title: str
    type: LessonType
    order_index: int
    content_json: dict


class LessonTreeOut(BaseModel):
    id: str
    title: str
    type: LessonType
    order_index: int


class ModuleTreeOut(BaseModel):
    id: str
    title: str
    order_index: int
    lessons: list[LessonTreeOut]


class ProgramDetailOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    strict_order: bool = True
    certification_progress_threshold: float = 100.0
    certification_min_avg_score: float = 60.0
    is_paid: bool = False
    price_amount: float | None = None
    modules: list[ModuleTreeOut]


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    program_id: str
    start_date: datetime | None = None
    end_date: datetime | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    program_id: str
    start_date: datetime | None = None
    end_date: datetime | None = None


class StudentIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: str | None = None
    organization: str | None = None


class EnrollmentCreate(BaseModel):
    students: list[StudentIn] = Field(min_length=1)


class EnrollmentOut(BaseModel):
    enrollment_id: str
    student_id: str
    full_name: str
    email: str | None
    organization: str | None = None
    payment_status: PaymentStatus = PaymentStatus.not_required
    payment_link: str | None = None


class StudentLessonOut(BaseModel):
    lesson_id: str
    module_title: str
    lesson_title: str
    lesson_type: LessonType
    module_order: int
    lesson_order: int
    status: ProgressStatus
    is_locked: bool
    attempts_used: int = 0
    attempts_allowed: int = 0


class StudentLessonsResponse(BaseModel):
    total: int
    completed: int
    program_status: Literal['not_started', 'in_progress', 'completed']
    payment_status: PaymentStatus = PaymentStatus.not_required
    payment_required: bool = False
    payment_link: str | None = None
    lessons: list[StudentLessonOut]


class CompleteLessonResponse(BaseModel):
    lesson_id: str
    status: ProgressStatus
    completed_at: datetime | None


class LessonEngagementRequest(BaseModel):
    group_id: str
    opened: bool = False
    watched_to_end: bool = False
    scrolled_to_bottom: bool = False


class TestAttemptRequest(BaseModel):
    group_id: str
    score: float = Field(ge=0, le=100)


class TestAttemptResponse(BaseModel):
    lesson_id: str
    score: float
    attempt_no: int
    attempts_allowed: int
    passed: bool
    status: ProgressStatus


class CertificateOut(BaseModel):
    enrollment_id: str
    certificate_url: str
    issued_at: datetime
    certificate_number: str | None = None


class GroupProgressRow(BaseModel):
    group_id: str
    program_id: str
    student_id: str
    full_name: str
    group_name: str
    program_name: str
    completed_lessons: int
    total_lessons: int
    progress_percent: float
    progress_status: Literal['not_started', 'in_progress', 'completed']
    enrolled_at: datetime
    last_activity: datetime | None
    last_login_at: datetime | None = None
    program_status: Literal['not_started', 'in_progress', 'completed'] = 'not_started'
    certificate_available: bool = False
    organization: str | None = None
    average_score: float = 0.0
    completion_date: datetime | None = None
    certificate_number: str | None = None
    payment_status: PaymentStatus = PaymentStatus.not_required


class GroupProgressResponse(BaseModel):
    group_id: str
    rows: list[GroupProgressRow]


class ProgressTableResponse(BaseModel):
    rows: list[GroupProgressRow]


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)


class UserProfileOut(BaseModel):
    id: str
    email: str
    full_name: str
    blocked: bool
    temp_password_required: bool
    student_id: str | None = None
    telegram_linked: bool = False
    telegram_username: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    roles: list[UserRole]
    require_password_change: bool
    user: UserProfileOut


class MeResponse(BaseModel):
    roles: list[UserRole]
    require_password_change: bool
    user: UserProfileOut


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class MessageOut(BaseModel):
    message: str


class UserCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    roles: list[UserRole] = Field(min_length=1)
    temp_password_required: bool = False
    organization: str | None = None


class UserRoleUpdate(BaseModel):
    roles: list[UserRole] = Field(min_length=1)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    blocked: bool
    temp_password_required: bool
    roles: list[UserRole]
    telegram_linked: bool = False


class GroupUserAssignRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class UserBlockRequest(BaseModel):
    blocked: bool


class CustomerStudentAssignRequest(BaseModel):
    student_ids: list[str] = Field(default_factory=list)


class AssignmentSubmitRequest(BaseModel):
    group_id: str
    lesson_id: str
    submission_text: str = Field(min_length=1)


class AssignmentReviewRequest(BaseModel):
    grade: float | None = None
    teacher_comment: str | None = None
    return_for_revision: bool = False
    override_reason: str | None = None


class AssignmentOut(BaseModel):
    id: str
    student_id: str
    student_name: str
    group_id: str
    group_name: str
    program_name: str
    lesson_id: str
    lesson_title: str
    status: AssignmentStatus
    submission_text: str
    submitted_at: datetime
    grade: float | None
    teacher_comment: str | None
    reviewed_by_user_id: str | None
    reviewed_at: datetime | None
    student_viewed_at: datetime | None
    file_name: str | None = None
    file_mime: str | None = None
    file_size_bytes: int | None = None
    file_download_url: str | None = None


class QuestionCreateRequest(BaseModel):
    group_id: str
    question_text: str = Field(min_length=1)


class QuestionAnswerRequest(BaseModel):
    answer_text: str = Field(min_length=1)


class QuestionOut(BaseModel):
    id: str
    student_id: str
    student_name: str
    group_id: str
    group_name: str
    question_text: str
    answer_text: str | None
    created_at: datetime
    answered_at: datetime | None


class ReminderSendRequest(BaseModel):
    student_id: str
    message: str = Field(min_length=1)


class ReminderOut(BaseModel):
    id: str
    student_id: str
    student_name: str
    curator_user_id: str
    message: str
    sent_at: datetime


class NotificationOut(BaseModel):
    id: str
    channel: NotificationChannel
    subject: str
    body: str
    link_url: str | None
    is_read: bool
    created_at: datetime


class NotificationMarkReadRequest(BaseModel):
    notification_ids: list[str] = Field(default_factory=list)


class AuditEventOut(BaseModel):
    id: str
    actor_user_id: str | None
    event_type: str
    entity_type: str
    entity_id: str
    from_status: str | None
    to_status: str | None
    payload_json: dict | None
    created_at: datetime


class TestAttemptsOverrideRequest(BaseModel):
    enrollment_id: str
    lesson_id: str
    extra_attempts: int = Field(ge=1, le=20)
    reason: str = Field(min_length=3)


class AutomationRunResult(BaseModel):
    generated_notifications: int
    generated_events: int


class TelegramLinkOut(BaseModel):
    invite_url: str
    linked: bool
    telegram_username: str | None = None


class TelegramConfirmRequest(BaseModel):
    token: str
    chat_id: str
    username: str | None = None


class CalendarLinksOut(BaseModel):
    google_url: str
    yandex_url: str
    ics_url: str


class LessonMaterialOut(BaseModel):
    id: str
    lesson_id: str
    file_name: str
    file_mime: str
    file_size_bytes: int
    uploaded_at: datetime
    download_url: str


class PaymentOut(BaseModel):
    enrollment_id: str
    payment_status: PaymentStatus
    payment_link: str | None
    payment_due_at: datetime | None
    payment_confirmed_at: datetime | None


class PaymentWebhookRequest(BaseModel):
    enrollment_id: str
    status: Literal['paid', 'pending', 'canceled']
    external_id: str | None = None


class IntegrationErrorOut(BaseModel):
    id: str
    service: str
    operation: str
    error_text: str
    context_json: dict | None
    user_id: str | None
    created_at: datetime


class GroupFinalReportRow(BaseModel):
    full_name: str
    organization: str | None
    progress_percent: float
    average_score: float
    completion_date: datetime | None
    certificate_number: str | None


class CustomerFinalReportResponse(BaseModel):
    rows: list[GroupFinalReportRow]


class ProgramStatsReportOut(BaseModel):
    program_id: str
    program_name: str
    groups_completed: int
    average_score: float
    average_completion_percent: float
    problem_lessons: list[dict]
