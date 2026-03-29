export type Role = 'executive' | 'methodist' | 'admin' | 'student' | 'teacher' | 'curator' | 'customer';

export type LessonType = 'video' | 'text' | 'test' | 'assignment';
export type LessonFilterType = LessonType | 'all';
export type ProgramStatus = 'draft' | 'active' | 'archived';
export type ProgressStatus = 'not_started' | 'in_progress' | 'awaiting_review' | 'completed';
export type ProgramProgressStatus = 'not_started' | 'in_progress' | 'completed';
export type AssignmentStatus = 'submitted' | 'reviewed' | 'returned_for_revision';
export type NotificationChannel = 'in_app' | 'email' | 'telegram';
export type PaymentStatus = 'not_required' | 'pending' | 'paid' | 'overdue';

export interface Program {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  status: ProgramStatus;
  strict_order: boolean;
  certification_progress_threshold: number;
  certification_min_avg_score: number;
  is_paid: boolean;
  price_amount: number | null;
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
  is_paid: boolean;
  price_amount: number | null;
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
  organization?: string | null;
  payment_status?: PaymentStatus;
  payment_link?: string | null;
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
  organization?: string | null;
  average_score?: number;
  completion_date?: string | null;
  certificate_number?: string | null;
  payment_status?: PaymentStatus;
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
  payment_status: PaymentStatus;
  payment_required: boolean;
  payment_link: string | null;
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
  telegram_linked: boolean;
  telegram_username: string | null;
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
  telegram_linked: boolean;
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
  file_name?: string | null;
  file_mime?: string | null;
  file_size_bytes?: number | null;
  file_download_url?: string | null;
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

export interface TelegramLinkOut {
  invite_url: string;
  linked: boolean;
  telegram_username: string | null;
}

export interface CalendarLinksOut {
  google_url: string;
  yandex_url: string;
  ics_url: string;
}

export interface PaymentOut {
  enrollment_id: string;
  payment_status: PaymentStatus;
  payment_link: string | null;
  payment_due_at: string | null;
  payment_confirmed_at: string | null;
}

export interface IntegrationErrorOut {
  id: string;
  service: string;
  operation: string;
  error_text: string;
  context_json: Record<string, unknown> | null;
  user_id: string | null;
  created_at: string;
}

export type AnalyticsPeriodPreset = '7d' | '30d' | '3m' | 'custom';

export interface AnalyticsPoint {
  period: string;
  value: number;
}

export interface ExecutiveDashboard {
  summary: {
    active_learners: number;
    programs: number;
    groups: number;
  };
  program_completion: Array<{
    program_id: string;
    program_name: string;
    enrolled: number;
    completed: number;
    dropped: number;
    completion_percent: number;
    average_score: number;
  }>;
  enrollments_by_month: AnalyticsPoint[];
  top_programs_by_students: Array<{ program_id: string; program_name: string; value: number }>;
  top_programs_by_score: Array<{ program_id: string; program_name: string; value: number }>;
  completion_trend: {
    current: number;
    previous: number;
    delta: number;
    direction: 'up' | 'down' | 'flat';
  };
  revenue_by_month: AnalyticsPoint[];
}

export interface AdminDashboard {
  executive: ExecutiveDashboard;
  groups: Array<{
    group_id: string;
    group_name: string;
    program_name: string;
    end_date: string | null;
    students_count: number;
    completion_percent: number;
    status: 'planned' | 'active' | 'completed';
  }>;
  inactive_students: Array<{
    student_id: string;
    full_name: string;
    group_name: string;
    program_name: string;
    last_login_at: string | null;
    progress_percent: number;
  }>;
  delayed_reviews: Array<{
    assignment_id: string;
    student_name: string;
    lesson_title: string;
    teacher_name: string;
    group_name: string;
    submitted_at: string;
    waiting_days: number;
  }>;
  integration_errors: Array<{
    id: string;
    service: string;
    operation: string;
    error_text: string;
    created_at: string;
  }>;
}

export interface MethodistDashboard {
  program_metrics: Array<{
    program_id: string;
    program_name: string;
    groups_count: number;
    enrollments_count: number;
    average_score: number;
    average_progress_percent: number;
    average_duration_days: number;
  }>;
  problem_lessons: Array<{
    lesson_id: string;
    lesson_title: string;
    program_name: string;
    module_title: string;
    repeat_attempts: number;
    failed_checks: number;
    avg_stuck_days: number;
  }>;
  program_funnel: Array<{
    program_id: string;
    program_name: string;
    module_id: string;
    module_title: string;
    module_order: number;
    reached_count: number;
  }>;
  comparison: {
    left: null | {
      program_id: string;
      program_name: string;
      groups_count: number;
      enrollments_count: number;
      average_score: number;
      average_progress_percent: number;
      average_duration_days: number;
    };
    right: null | {
      program_id: string;
      program_name: string;
      groups_count: number;
      enrollments_count: number;
      average_score: number;
      average_progress_percent: number;
      average_duration_days: number;
    };
  };
}

export interface CuratorDashboard {
  students: Array<{
    student_id: string;
    full_name: string;
    group_name: string;
    program_name: string;
    progress_percent: number;
    last_login_at: string | null;
    current_lesson: string | null;
    signal: 'green' | 'yellow' | 'red';
    lag_percent: number;
    days_left: number | null;
  }>;
  signal_counts: {
    green: number;
    yellow: number;
    red: number;
  };
  reminders: Array<{
    id: string;
    student_id: string;
    student_name: string;
    message: string;
    sent_at: string | null;
    effect: boolean;
  }>;
}

export interface TeacherDashboard {
  courses: Array<{
    group_id: string;
    group_name: string;
    program_name: string;
    average_score: number;
    distribution: Array<{
      bucket: '0-59' | '60-74' | '75-89' | '90-100';
      count: number;
    }>;
  }>;
  most_questions_lesson: null | {
    lesson_title: string;
    questions_count: number;
  };
  average_review_hours: number;
  review_queue: Array<{
    assignment_id: string;
    student_name: string;
    group_name: string;
    lesson_title: string;
    submitted_at: string | null;
  }>;
}

export interface CustomerDashboard {
  summary: {
    completed: number;
    in_progress: number;
    not_started: number;
  };
  employees: Array<{
    student_id: string;
    full_name: string;
    program_name: string;
    group_name: string;
    progress_percent: number;
    last_login_at: string | null;
    status: 'completed' | 'in_progress' | 'not_started';
  }>;
  weekly_progress: AnalyticsPoint[];
}
