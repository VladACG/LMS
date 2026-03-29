export type Role = 'methodist' | 'admin' | 'student' | 'teacher' | 'curator' | 'customer';

export type LessonType = 'video' | 'text' | 'test' | 'assignment';
export type LessonFilterType = LessonType | 'all';
export type ProgramStatus = 'draft' | 'active' | 'archived';
export type ProgressStatus = 'not_started' | 'in_progress' | 'awaiting_review' | 'completed';
export type ProgramProgressStatus = 'not_started' | 'in_progress' | 'completed';
export type AssignmentStatus = 'submitted' | 'reviewed' | 'returned_for_revision';
export type NotificationChannel = 'in_app' | 'email';

export interface Program {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  status: ProgramStatus;
  strict_order: boolean;
  certification_progress_threshold: number;
  certification_min_avg_score: number;
}

export interface Module {
  id: string;
  program_id: string;
  title: string;
  order_index: number;
}

export interface Lesson {
  id: string;
  module_id: string;
  title: string;
  type: LessonType;
  order_index: number;
  content_json: Record<string, unknown>;
}

export interface ProgramDetail {
  id: string;
  name: string;
  description: string | null;
  strict_order: boolean;
  certification_progress_threshold: number;
  certification_min_avg_score: number;
  modules: Array<{
    id: string;
    title: string;
    order_index: number;
    lessons: Array<{
      id: string;
      title: string;
      type: LessonType;
      order_index: number;
    }>;
  }>;
}

export interface Group {
  id: string;
  name: string;
  program_id: string;
  start_date?: string | null;
  end_date?: string | null;
}

export interface EnrollmentResult {
  enrollment_id: string;
  student_id: string;
  full_name: string;
  email: string | null;
}

export interface ProgressRow {
  group_id: string;
  program_id: string;
  student_id: string;
  full_name: string;
  group_name: string;
  program_name: string;
  completed_lessons: number;
  total_lessons: number;
  progress_percent: number;
  progress_status: ProgressStatus;
  enrolled_at: string;
  last_activity: string | null;
  last_login_at: string | null;
  program_status: ProgramProgressStatus;
  certificate_available: boolean;
}

export interface GroupProgress {
  group_id: string;
  rows: ProgressRow[];
}

export interface ProgressTableResponse {
  rows: ProgressRow[];
}

export interface StudentLesson {
  lesson_id: string;
  module_title: string;
  lesson_title: string;
  lesson_type: LessonType;
  module_order: number;
  lesson_order: number;
  status: ProgressStatus;
  is_locked: boolean;
  attempts_used: number;
  attempts_allowed: number;
}

export interface StudentLessonsResponse {
  total: number;
  completed: number;
  program_status: ProgramProgressStatus;
  lessons: StudentLesson[];
}

export interface StudentInput {
  full_name: string;
  email?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  blocked: boolean;
  temp_password_required: boolean;
  student_id: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  roles: Role[];
  require_password_change: boolean;
  user: UserProfile;
}

export interface MeResponse {
  roles: Role[];
  require_password_change: boolean;
  user: UserProfile;
}

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  blocked: boolean;
  temp_password_required: boolean;
  roles: Role[];
}

export interface AssignmentOut {
  id: string;
  student_id: string;
  student_name: string;
  group_id: string;
  group_name: string;
  program_name: string;
  lesson_id: string;
  lesson_title: string;
  status: AssignmentStatus;
  submission_text: string;
  submitted_at: string;
  grade: number | null;
  teacher_comment: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  student_viewed_at: string | null;
}

export interface QuestionOut {
  id: string;
  student_id: string;
  student_name: string;
  group_id: string;
  group_name: string;
  question_text: string;
  answer_text: string | null;
  created_at: string;
  answered_at: string | null;
}

export interface ReminderOut {
  id: string;
  student_id: string;
  student_name: string;
  curator_user_id: string;
  message: string;
  sent_at: string;
}

export interface NotificationOut {
  id: string;
  channel: NotificationChannel;
  subject: string;
  body: string;
  link_url: string | null;
  is_read: boolean;
  created_at: string;
}
