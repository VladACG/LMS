import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AssignmentStatus,
    LessonType,
    NotificationChannel,
    ProgramProgressStatus,
    ProgressStatus,
    UserRole,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Program(Base):
    __tablename__ = 'programs'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    strict_order: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    certification_progress_threshold: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    certification_min_avg_score: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)

    modules: Mapped[list['Module']] = relationship(back_populates='program', cascade='all, delete-orphan')
    groups: Mapped[list['Group']] = relationship(back_populates='program', cascade='all, delete-orphan')


class Module(Base):
    __tablename__ = 'modules'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    program_id: Mapped[str] = mapped_column(ForeignKey('programs.id', ondelete='CASCADE'), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    program: Mapped[Program] = relationship(back_populates='modules')
    lessons: Mapped[list['Lesson']] = relationship(back_populates='module', cascade='all, delete-orphan')


class Lesson(Base):
    __tablename__ = 'lessons'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(ForeignKey('modules.id', ondelete='CASCADE'), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[LessonType] = mapped_column(Enum(LessonType), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    module: Mapped[Module] = relationship(back_populates='lessons')
    assignment_submissions: Mapped[list['AssignmentSubmission']] = relationship(
        back_populates='lesson',
        cascade='all, delete-orphan',
    )


class Group(Base):
    __tablename__ = 'groups'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    program_id: Mapped[str] = mapped_column(ForeignKey('programs.id', ondelete='CASCADE'), nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    program: Mapped[Program] = relationship(back_populates='groups')
    enrollments: Mapped[list['Enrollment']] = relationship(back_populates='group', cascade='all, delete-orphan')
    teacher_links: Mapped[list['TeacherGroupLink']] = relationship(back_populates='group', cascade='all, delete-orphan')
    curator_links: Mapped[list['CuratorGroupLink']] = relationship(back_populates='group', cascade='all, delete-orphan')
    questions: Mapped[list['StudentQuestion']] = relationship(back_populates='group', cascade='all, delete-orphan')


class Student(Base):
    __tablename__ = 'students'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    enrollments: Mapped[list['Enrollment']] = relationship(back_populates='student', cascade='all, delete-orphan')
    user_links: Mapped[list['UserStudentLink']] = relationship(back_populates='student', cascade='all, delete-orphan')
    customer_links: Mapped[list['CustomerStudentLink']] = relationship(back_populates='student', cascade='all, delete-orphan')
    questions: Mapped[list['StudentQuestion']] = relationship(back_populates='student', cascade='all, delete-orphan')
    reminders: Mapped[list['ReminderLog']] = relationship(back_populates='student', cascade='all, delete-orphan')


class Enrollment(Base):
    __tablename__ = 'enrollments'
    __table_args__ = (UniqueConstraint('group_id', 'student_id', name='uq_group_student'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    student_id: Mapped[str] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    program_status: Mapped[ProgramProgressStatus] = mapped_column(
        Enum(ProgramProgressStatus),
        nullable=False,
        default=ProgramProgressStatus.not_started,
    )
    certification_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certificate_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    group: Mapped[Group] = relationship(back_populates='enrollments')
    student: Mapped[Student] = relationship(back_populates='enrollments')
    progress_items: Mapped[list['LessonProgress']] = relationship(back_populates='enrollment', cascade='all, delete-orphan')
    assignment_submissions: Mapped[list['AssignmentSubmission']] = relationship(
        back_populates='enrollment',
        cascade='all, delete-orphan',
    )
    test_attempts: Mapped[list['TestAttempt']] = relationship(back_populates='enrollment', cascade='all, delete-orphan')


class LessonProgress(Base):
    __tablename__ = 'lesson_progress'
    __table_args__ = (UniqueConstraint('enrollment_id', 'lesson_id', name='uq_enrollment_lesson'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey('enrollments.id', ondelete='CASCADE'), nullable=False)
    lesson_id: Mapped[str] = mapped_column(ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False)
    status: Mapped[ProgressStatus] = mapped_column(Enum(ProgressStatus), nullable=False, default=ProgressStatus.not_started)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_attempts_allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    enrollment: Mapped[Enrollment] = relationship(back_populates='progress_items')


class User(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    temp_password_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list['UserRoleLink']] = relationship(back_populates='user', cascade='all, delete-orphan')
    student_link: Mapped['UserStudentLink | None'] = relationship(back_populates='user', uselist=False, cascade='all, delete-orphan')
    teacher_groups: Mapped[list['TeacherGroupLink']] = relationship(back_populates='user', cascade='all, delete-orphan')
    curator_groups: Mapped[list['CuratorGroupLink']] = relationship(back_populates='user', cascade='all, delete-orphan')
    customer_students: Mapped[list['CustomerStudentLink']] = relationship(back_populates='customer', cascade='all, delete-orphan')
    reviewed_submissions: Mapped[list['AssignmentSubmission']] = relationship(back_populates='reviewed_by_user')
    answered_questions: Mapped[list['StudentQuestion']] = relationship(back_populates='answered_by_user')
    sent_reminders: Mapped[list['ReminderLog']] = relationship(back_populates='curator')
    notifications: Mapped[list['Notification']] = relationship(back_populates='recipient', cascade='all, delete-orphan')
    audit_events: Mapped[list['AuditEvent']] = relationship(back_populates='actor')


class UserRoleLink(Base):
    __tablename__ = 'user_roles'
    __table_args__ = (UniqueConstraint('user_id', 'role', name='uq_user_role'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)

    user: Mapped[User] = relationship(back_populates='roles')


class UserStudentLink(Base):
    __tablename__ = 'user_student_links'
    __table_args__ = (
        UniqueConstraint('user_id', name='uq_user_student_link_user'),
        UniqueConstraint('student_id', name='uq_user_student_link_student'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    student_id: Mapped[str] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), nullable=False)

    user: Mapped[User] = relationship(back_populates='student_link')
    student: Mapped[Student] = relationship(back_populates='user_links')


class TeacherGroupLink(Base):
    __tablename__ = 'teacher_group_links'
    __table_args__ = (UniqueConstraint('user_id', 'group_id', name='uq_teacher_group'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)

    user: Mapped[User] = relationship(back_populates='teacher_groups')
    group: Mapped[Group] = relationship(back_populates='teacher_links')


class CuratorGroupLink(Base):
    __tablename__ = 'curator_group_links'
    __table_args__ = (UniqueConstraint('user_id', 'group_id', name='uq_curator_group'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)

    user: Mapped[User] = relationship(back_populates='curator_groups')
    group: Mapped[Group] = relationship(back_populates='curator_links')


class CustomerStudentLink(Base):
    __tablename__ = 'customer_student_links'
    __table_args__ = (UniqueConstraint('customer_user_id', 'student_id', name='uq_customer_student'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    customer_user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    student_id: Mapped[str] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), nullable=False)

    customer: Mapped[User] = relationship(back_populates='customer_students')
    student: Mapped[Student] = relationship(back_populates='customer_links')


class AssignmentSubmission(Base):
    __tablename__ = 'assignment_submissions'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey('enrollments.id', ondelete='CASCADE'), nullable=False)
    lesson_id: Mapped[str] = mapped_column(ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False)
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus), nullable=False, default=AssignmentStatus.submitted)
    submission_text: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    grade: Mapped[float | None] = mapped_column(nullable=True)
    teacher_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    student_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    enrollment: Mapped[Enrollment] = relationship(back_populates='assignment_submissions')
    lesson: Mapped[Lesson] = relationship(back_populates='assignment_submissions')
    reviewed_by_user: Mapped[User | None] = relationship(back_populates='reviewed_submissions')


class TestAttempt(Base):
    __tablename__ = 'test_attempts'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey('enrollments.id', ondelete='CASCADE'), nullable=False)
    lesson_id: Mapped[str] = mapped_column(ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    enrollment: Mapped[Enrollment] = relationship(back_populates='test_attempts')


class Notification(Base):
    __tablename__ = 'notifications'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(Enum(NotificationChannel), nullable=False, default=NotificationChannel.in_app)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    recipient: Mapped[User] = relationship(back_populates='notifications')


class AuditEvent(Base):
    __tablename__ = 'audit_events'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    actor: Mapped[User | None] = relationship(back_populates='audit_events')


class StudentQuestion(Base):
    __tablename__ = 'student_questions'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_by_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    student: Mapped[Student] = relationship(back_populates='questions')
    group: Mapped[Group] = relationship(back_populates='questions')
    answered_by_user: Mapped[User | None] = relationship(back_populates='answered_questions')


class ReminderLog(Base):
    __tablename__ = 'reminder_logs'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    curator_user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    student: Mapped[Student] = relationship(back_populates='reminders')
    curator: Mapped[User] = relationship(back_populates='sent_reminders')
