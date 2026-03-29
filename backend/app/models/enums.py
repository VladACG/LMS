from enum import Enum


class LessonType(str, Enum):
    video = 'video'
    text = 'text'
    test = 'test'
    assignment = 'assignment'


class ProgressStatus(str, Enum):
    not_started = 'not_started'
    in_progress = 'in_progress'
    awaiting_review = 'awaiting_review'
    completed = 'completed'


class ProgramProgressStatus(str, Enum):
    not_started = 'not_started'
    in_progress = 'in_progress'
    completed = 'completed'


class UserRole(str, Enum):
    student = 'student'
    teacher = 'teacher'
    curator = 'curator'
    methodist = 'methodist'
    admin = 'admin'
    customer = 'customer'


class AssignmentStatus(str, Enum):
    submitted = 'submitted'
    reviewed = 'reviewed'
    returned_for_revision = 'returned_for_revision'


class NotificationChannel(str, Enum):
    in_app = 'in_app'
    email = 'email'
