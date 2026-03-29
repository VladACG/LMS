import { apiGet, apiGetBlob, apiPost, setAuthToken } from './client';
import type {
  AdminDashboard,
  AnalyticsPeriodPreset,
  AssignmentOut,
  CalendarLinksOut,
  CuratorDashboard,
  CustomerDashboard,
  ExecutiveDashboard,
  EnrollmentResult,
  Group,
  GroupProgress,
  IntegrationErrorOut,
  Lesson,
  LoginResponse,
  MeResponse,
  Module,
  NotificationOut,
  PaymentOut,
  Program,
  ProgramDetail,
  TeacherDashboard,
  MethodistDashboard,
  ProgressStatus,
  ProgressTableResponse,
  QuestionOut,
  ReminderOut,
  Role,
  StudentInput,
  StudentLessonsResponse,
  TelegramLinkOut,
  UserOut,
} from '../types/lms';

function withQuery(path: string, params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      search.set(key, value);
    }
  });

  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

function analyticsPath(
  path: string,
  params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string },
): string {
  return withQuery(path, {
    period: params?.period,
    date_from: params?.date_from,
    date_to: params?.date_to,
  });
}

export async function login(payload: { email: string; password: string }) {
  const result = await apiPost<LoginResponse>('/api/auth/login', payload);
  setAuthToken(result.access_token);
  return result;
}

export function logout() {
  setAuthToken(null);
}

export function getMe() {
  return apiGet<MeResponse>('/api/auth/me');
}

export function changePassword(payload: { old_password: string; new_password: string }) {
  return apiPost<{ message: string }>('/api/auth/change-password', payload);
}

export function listPrograms(params?: {
  search?: string;
  status?: 'draft' | 'active' | 'archived';
  sort?: 'asc' | 'desc';
}) {
  const path = withQuery('/api/programs', {
    search: params?.search,
    status: params?.status,
    sort: params?.sort,
  });
  return apiGet<Program[]>(path);
}

export function getProgram(programId: string) {
  return apiGet<ProgramDetail>(`/api/programs/${programId}`);
}

export function createProgram(payload: {
  name: string;
  description?: string;
  strict_order?: boolean;
  certification_progress_threshold?: number;
  certification_min_avg_score?: number;
  is_paid?: boolean;
  price_amount?: number | null;
}) {
  return apiPost<Program>('/api/programs', payload);
}

export function createModule(programId: string, payload: { title: string; order_index: number }) {
  return apiPost<Module>(`/api/programs/${programId}/modules`, payload);
}

export function createLesson(
  moduleId: string,
  payload: {
    title: string;
    type: 'video' | 'text' | 'test' | 'assignment';
    order_index: number;
    video_url?: string;
    text_body?: string;
    questions_json?: Record<string, unknown>;
    test_pass_score?: number;
    test_max_attempts?: number;
    assignment_pass_score?: number;
  },
) {
  return apiPost<Lesson>(`/api/modules/${moduleId}/lessons`, payload);
}

export function listGroups() {
  return apiGet<Group[]>('/api/groups');
}

export function createGroup(payload: { name: string; program_id: string; start_date?: string; end_date?: string }) {
  return apiPost<Group>('/api/groups', payload);
}

export function createEnrollments(groupId: string, students: StudentInput[]) {
  return apiPost<EnrollmentResult[]>(`/api/groups/${groupId}/enrollments`, { students });
}

export function assignGroupTeachers(groupId: string, userIds: string[]) {
  return apiPost<{ message: string }>(`/api/groups/${groupId}/teachers`, { user_ids: userIds });
}

export function assignGroupCurators(groupId: string, userIds: string[]) {
  return apiPost<{ message: string }>(`/api/groups/${groupId}/curators`, { user_ids: userIds });
}

export function assignCustomerStudents(customerUserId: string, studentIds: string[]) {
  return apiPost<{ message: string }>(`/api/customers/${customerUserId}/students`, { student_ids: studentIds });
}

export function getGroupProgress(groupId: string) {
  return apiGet<GroupProgress>(`/api/groups/${groupId}/progress`);
}

export function getProgressTable(params?: {
  group_id?: string;
  program_id?: string;
  progress_status?: ProgressStatus;
  search?: string;
  sort_by?: 'progress_percent' | 'enrolled_at';
  sort_order?: 'asc' | 'desc';
}) {
  const path = withQuery('/api/progress', {
    group_id: params?.group_id,
    program_id: params?.program_id,
    progress_status: params?.progress_status,
    search: params?.search,
    sort_by: params?.sort_by,
    sort_order: params?.sort_order,
  });
  return apiGet<ProgressTableResponse>(path);
}

export function getStudentLessons(studentId: string, groupId: string) {
  return apiGet<StudentLessonsResponse>(`/api/students/${studentId}/lessons?group_id=${groupId}`);
}

export function getStudentPayment(studentId: string, groupId: string) {
  return apiGet<PaymentOut>(`/api/students/${studentId}/payment?group_id=${groupId}`);
}

export function getCalendarLinks(studentId: string, groupId: string) {
  return apiGet<CalendarLinksOut>(`/api/students/${studentId}/calendar-links?group_id=${groupId}`);
}

export function completeLesson(studentId: string, lessonId: string, groupId: string) {
  return apiPost<{ lesson_id: string; status: string; completed_at: string | null }>(
    `/api/students/${studentId}/lessons/${lessonId}/complete?group_id=${groupId}`,
    {},
  );
}

export function engageLesson(
  studentId: string,
  lessonId: string,
  payload: { group_id: string; opened?: boolean; watched_to_end?: boolean; scrolled_to_bottom?: boolean },
) {
  return apiPost<{ lesson_id: string; status: string; completed_at: string | null }>(
    `/api/students/${studentId}/lessons/${lessonId}/engagement`,
    {
      group_id: payload.group_id,
      opened: payload.opened ?? false,
      watched_to_end: payload.watched_to_end ?? false,
      scrolled_to_bottom: payload.scrolled_to_bottom ?? false,
    },
  );
}

export function submitTestAttempt(studentId: string, lessonId: string, payload: { group_id: string; score: number }) {
  return apiPost<{ lesson_id: string; score: number; attempt_no: number; attempts_allowed: number; passed: boolean; status: string }>(
    `/api/students/${studentId}/lessons/${lessonId}/test-attempt`,
    payload,
  );
}

export function submitAssignment(payload: { group_id: string; lesson_id: string; submission_text: string }) {
  return apiPost<AssignmentOut>('/api/assignments', payload);
}

export function listMyAssignments() {
  return apiGet<AssignmentOut[]>('/api/assignments/my');
}

export function listAssignmentReviewQueue() {
  return apiGet<AssignmentOut[]>('/api/assignments/review-queue');
}

export function reviewAssignment(
  assignmentId: string,
  payload: { grade?: number; teacher_comment?: string; return_for_revision?: boolean; override_reason?: string },
) {
  return apiPost<AssignmentOut>(`/api/assignments/${assignmentId}/review`, payload);
}

export function createQuestion(payload: { group_id: string; question_text: string }) {
  return apiPost<QuestionOut>('/api/questions', payload);
}

export function listQuestions() {
  return apiGet<QuestionOut[]>('/api/questions');
}

export function answerQuestion(questionId: string, payload: { answer_text: string }) {
  return apiPost<QuestionOut>(`/api/questions/${questionId}/answer`, payload);
}

export function sendReminder(payload: { student_id: string; message: string }) {
  return apiPost<ReminderOut>('/api/reminders', payload);
}

export function listReminders() {
  return apiGet<ReminderOut[]>('/api/reminders');
}

export function listNotifications(params?: { unread_only?: boolean }) {
  const path = withQuery('/api/notifications', {
    unread_only: params?.unread_only ? 'true' : undefined,
  });
  return apiGet<NotificationOut[]>(path);
}

export function getTelegramLink() {
  return apiGet<TelegramLinkOut>('/api/telegram/link');
}

export function confirmTelegramLink(payload: { token: string; chat_id: string; username?: string }) {
  return apiPost<{ message: string }>('/api/telegram/confirm', payload);
}

export function markNotificationsRead(notificationIds: string[]) {
  return apiPost<{ message: string }>('/api/notifications/mark-read', { notification_ids: notificationIds });
}

export function listIntegrationErrors(params?: { service?: string; limit?: number }) {
  const path = withQuery('/api/integrations/errors', {
    service: params?.service,
    limit: params?.limit ? String(params.limit) : undefined,
  });
  return apiGet<IntegrationErrorOut[]>(path);
}

export function downloadGroupFinalReport(groupId: string) {
  return apiGetBlob(`/api/reports/groups/${groupId}/final.xlsx`);
}

export function downloadCustomerFinalReport() {
  return apiGetBlob('/api/reports/customers/me/final.xlsx');
}

export function listUsers() {
  return apiGet<UserOut[]>('/api/users');
}

export function createUser(payload: {
  email: string;
  full_name: string;
  password: string;
  roles: Role[];
  temp_password_required?: boolean;
}) {
  return apiPost<UserOut>('/api/users', payload);
}

export function updateUserRoles(userId: string, roles: Role[]) {
  return apiPost<UserOut>(`/api/users/${userId}/roles`, { roles });
}

export function blockUser(userId: string, blocked: boolean) {
  return apiPost<UserOut>(`/api/users/${userId}/block`, { blocked });
}

export function getExecutiveDashboard(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGet<ExecutiveDashboard>(analyticsPath('/api/analytics/executive', params));
}

export function getAdminDashboard(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGet<AdminDashboard>(analyticsPath('/api/analytics/admin', params));
}

export function getMethodistDashboard(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGet<MethodistDashboard>(analyticsPath('/api/analytics/methodist', params));
}

export function getCuratorDashboard(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGet<CuratorDashboard>(analyticsPath('/api/analytics/curator', params));
}

export function getTeacherDashboard(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGet<TeacherDashboard>(analyticsPath('/api/analytics/teacher', params));
}

export function getCustomerDashboard(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGet<CustomerDashboard>(analyticsPath('/api/analytics/customer', params));
}

export function downloadExecutiveProgramCompletion(params?: {
  period?: AnalyticsPeriodPreset;
  date_from?: string;
  date_to?: string;
}) {
  return apiGetBlob(analyticsPath('/api/analytics/executive/program-completion.xlsx', params));
}

export function downloadAdminGroups(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGetBlob(analyticsPath('/api/analytics/admin/groups.xlsx', params));
}

export function downloadAdminInactiveStudents(params?: {
  period?: AnalyticsPeriodPreset;
  date_from?: string;
  date_to?: string;
}) {
  return apiGetBlob(analyticsPath('/api/analytics/admin/inactive-students.xlsx', params));
}

export function downloadAdminDelayedReviews(params?: {
  period?: AnalyticsPeriodPreset;
  date_from?: string;
  date_to?: string;
}) {
  return apiGetBlob(analyticsPath('/api/analytics/admin/delayed-reviews.xlsx', params));
}

export function downloadAdminIntegrationErrors(params?: {
  period?: AnalyticsPeriodPreset;
  date_from?: string;
  date_to?: string;
}) {
  return apiGetBlob(analyticsPath('/api/analytics/admin/integration-errors.xlsx', params));
}

export function downloadMethodistPrograms(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGetBlob(analyticsPath('/api/analytics/methodist/programs.xlsx', params));
}

export function downloadMethodistProblemLessons(params?: {
  period?: AnalyticsPeriodPreset;
  date_from?: string;
  date_to?: string;
}) {
  return apiGetBlob(analyticsPath('/api/analytics/methodist/problem-lessons.xlsx', params));
}

export function downloadMethodistFunnel(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGetBlob(analyticsPath('/api/analytics/methodist/funnel.xlsx', params));
}

export function downloadCuratorStudents(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGetBlob(analyticsPath('/api/analytics/curator/students.xlsx', params));
}

export function downloadCuratorReminders(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGetBlob(analyticsPath('/api/analytics/curator/reminders.xlsx', params));
}

export function downloadTeacherCourses(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGetBlob(analyticsPath('/api/analytics/teacher/courses.xlsx', params));
}

export function downloadTeacherReviewQueue(params?: {
  period?: AnalyticsPeriodPreset;
  date_from?: string;
  date_to?: string;
}) {
  return apiGetBlob(analyticsPath('/api/analytics/teacher/review-queue.xlsx', params));
}

export function downloadCustomerEmployees(params?: { period?: AnalyticsPeriodPreset; date_from?: string; date_to?: string }) {
  return apiGetBlob(analyticsPath('/api/analytics/customer/employees.xlsx', params));
}

