import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  answerQuestion,
  assignGroupCurators,
  assignGroupTeachers,
  blockUser,
  changePassword,
  engageLesson,
  createEnrollments,
  createGroup,
  createLesson,
  createModule,
  createProgram,
  createQuestion,
  createUser,
  downloadAdminDelayedReviews,
  downloadAdminGroups,
  downloadAdminInactiveStudents,
  downloadAdminIntegrationErrors,
  downloadCuratorReminders,
  downloadCuratorStudents,
  downloadCustomerFinalReport,
  downloadCustomerEmployees,
  downloadExecutiveProgramCompletion,
  downloadGroupFinalReport,
  downloadMethodistFunnel,
  downloadMethodistProblemLessons,
  downloadMethodistPrograms,
  downloadTeacherCourses,
  downloadTeacherReviewQueue,
  getCalendarLinks,
  getAdminDashboard,
  getCuratorDashboard,
  getCustomerDashboard,
  getExecutiveDashboard,
  getMethodistDashboard,
  getMe,
  getProgram,
  getProgressTable,
  getStudentPayment,
  getStudentLessons,
  getTeacherDashboard,
  getTelegramLink,
  listIntegrationErrors,
  listAssignmentReviewQueue,
  listGroups,
  listMyAssignments,
  listNotifications,
  listPrograms,
  listQuestions,
  listReminders,
  listUsers,
  login,
  markNotificationsRead,
  logout,
  reviewAssignment,
  sendReminder,
  submitTestAttempt,
  submitAssignment,
  updateUserRoles,
} from './api/lms';
import { ApiError, getAuthToken } from './api/client';
import type {
  AnalyticsPeriodPreset,
  AssignmentOut,
  IntegrationErrorOut,
  LessonFilterType,
  MeResponse,
  NotificationOut,
  PaymentStatus,
  ProgramStatus,
  ProgressRow,
  ProgressStatus,
  QuestionOut,
  ReminderOut,
  Role,
  StudentLesson,
  UserOut,
} from './types/lms';
import { parseStudentsInput } from './utils/parseStudents';
import './App.css';

const roleLabels: Record<Role, string> = {
  executive: 'Руководитель',
  methodist: 'Методист',
  admin: 'Администратор',
  student: 'Слушатель',
  teacher: 'Преподаватель',
  curator: 'Куратор',
  customer: 'Заказчик',
};

const programStatusLabels: Record<ProgramStatus, string> = {
  draft: 'Черновик',
  active: 'Активна',
  archived: 'Архив',
};

const progressStatusLabels: Record<ProgressStatus, string> = {
  not_started: 'Не начал',
  in_progress: 'В процессе',
  awaiting_review: 'Ожидает проверки',
  completed: 'Завершил',
};

const paymentStatusLabels: Record<PaymentStatus, string> = {
  not_required: 'Не требуется',
  pending: 'Ожидает оплаты',
  paid: 'Оплачено',
  overdue: 'Просрочено',
};

const lessonTypeLabels: Record<LessonFilterType, string> = {
  all: 'Все типы',
  video: 'Видео',
  text: 'Текст',
  test: 'Тест',
  assignment: 'Задание',
};

const roleCatalog: Role[] = ['executive', 'admin', 'methodist', 'teacher', 'curator', 'student', 'customer'];

function formatDate(value: string | null): string {
  if (!value) {
    return '—';
  }
  return new Date(value).toLocaleString('ru-RU');
}

function channelLabel(channel: 'in_app' | 'email' | 'telegram'): string {
  if (channel === 'email') return 'Email';
  if (channel === 'telegram') return 'Telegram';
  return 'В системе';
}

function saveBlobAsFile(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function ProgramStatusBadge({ status }: { status: ProgramStatus }) {
  return <span className={`status-pill status-${status}`}>{programStatusLabels[status]}</span>;
}

function ProgressStatusBadge({ status }: { status: ProgressStatus }) {
  return <span className={`status-pill status-${status}`}>{progressStatusLabels[status]}</span>;
}

function useAnalyticsPeriod() {
  const [period, setPeriod] = useState<AnalyticsPeriodPreset>('30d');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const params = useMemo(() => {
    const date_from = period === 'custom' && dateFrom ? new Date(`${dateFrom}T00:00:00Z`).toISOString() : undefined;
    const date_to = period === 'custom' && dateTo ? new Date(`${dateTo}T23:59:59Z`).toISOString() : undefined;
    return {
      period,
      date_from,
      date_to,
    };
  }, [period, dateFrom, dateTo]);

  return {
    period,
    setPeriod,
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    params,
  };
}

function AnalyticsPeriodFilter({
  period,
  setPeriod,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
}: {
  period: AnalyticsPeriodPreset;
  setPeriod: (value: AnalyticsPeriodPreset) => void;
  dateFrom: string;
  setDateFrom: (value: string) => void;
  dateTo: string;
  setDateTo: (value: string) => void;
}) {
  return (
    <div className="toolbar-row">
      <select value={period} onChange={(event) => setPeriod(event.target.value as AnalyticsPeriodPreset)}>
        <option value="7d">Последние 7 дней</option>
        <option value="30d">Последние 30 дней</option>
        <option value="3m">Последние 3 месяца</option>
        <option value="custom">Произвольный диапазон</option>
      </select>
      {period === 'custom' ? (
        <>
          <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </>
      ) : null}
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="kpi-card">
      <p className="muted">{label}</p>
      <h3>{value}</h3>
    </article>
  );
}

function EmptyAnalytics() {
  return <p className="muted">данных пока недостаточно</p>;
}

function SimpleBarChart({ data, valueSuffix = '' }: { data: Array<{ label: string; value: number }>; valueSuffix?: string }) {
  if (data.length === 0) {
    return <EmptyAnalytics />;
  }

  const maxValue = Math.max(...data.map((item) => item.value), 0);
  return (
    <div className="chart-list">
      {data.map((item) => {
        const width = maxValue > 0 ? Math.max((item.value / maxValue) * 100, 2) : 2;
        return (
          <div key={item.label} className="chart-row">
            <div className="chart-meta">
              <span>{item.label}</span>
              <strong>
                {item.value}
                {valueSuffix}
              </strong>
            </div>
            <div className="chart-track">
              <div className="chart-fill" style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function LoginView({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState('admin@lms.local');
  const [password, setPassword] = useState('Admin123!');

  const loginMutation = useMutation({
    mutationFn: () => login({ email, password }),
    onSuccess: () => {
      onLoggedIn();
    },
  });

  const errorText = loginMutation.error instanceof ApiError ? loginMutation.error.message : null;

  return (
    <div className="auth-shell">
      <section className="card auth-card">
        <h1>LMS Login</h1>
        <p className="muted">Войдите по email и паролю. Без входа доступна только эта форма.</p>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            loginMutation.mutate();
          }}
        >
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" />
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Пароль"
          />
          <button type="submit" disabled={loginMutation.isPending}>Войти</button>
          {errorText ? <p className="error">{errorText}</p> : null}
        </form>
        <p className="muted small">
          Тестовые логины: `executive@lms.local / Exec123!`, `admin@lms.local / Admin123!`, `student1@lms.local / Temp123!`, `teacher@lms.local / Teach123!`
        </p>
      </section>
    </div>
  );
}

function ForcePasswordChangeView({ onChanged }: { onChanged: () => void }) {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');

  const mutation = useMutation({
    mutationFn: () => changePassword({ old_password: oldPassword, new_password: newPassword }),
    onSuccess: () => {
      setOldPassword('');
      setNewPassword('');
      onChanged();
    },
  });

  const errorText = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <div className="auth-shell">
      <section className="card auth-card">
        <h1>Смена временного пароля</h1>
        <p className="muted">Перед продолжением обучения задайте постоянный пароль.</p>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <input
            type="password"
            value={oldPassword}
            onChange={(event) => setOldPassword(event.target.value)}
            placeholder="Текущий пароль"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            placeholder="Новый пароль (минимум 8 символов)"
          />
          <button type="submit" disabled={mutation.isPending || newPassword.length < 8}>Сохранить пароль</button>
          {errorText ? <p className="error">{errorText}</p> : null}
        </form>
      </section>
    </div>
  );
}

function StudentsProgressTable({
  rows,
  compact = false,
  includeLastLogin = false,
  includePaymentStatus = false,
}: {
  rows: ProgressRow[];
  compact?: boolean;
  includeLastLogin?: boolean;
  includePaymentStatus?: boolean;
}) {
  if (rows.length === 0) {
    return <p className="muted">По заданным фильтрам данных не найдено.</p>;
  }

  return (
    <div className="table-wrap">
      <table className={compact ? 'compact-table' : ''}>
        <thead>
          <tr>
            <th>ФИО</th>
            <th>Программа</th>
            <th>Группа</th>
            <th>Прогресс (%)</th>
            <th>Статус</th>
            <th>Дата зачисления</th>
            <th>Последняя активность</th>
            {includeLastLogin ? <th>Последний вход</th> : null}
            {includePaymentStatus ? <th>Оплата</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.group_id}-${row.student_id}`}>
              <td>{row.full_name}</td>
              <td>{row.program_name}</td>
              <td>{row.group_name}</td>
              <td>{row.progress_percent}</td>
              <td>
                <ProgressStatusBadge status={row.progress_status} />
              </td>
              <td>{formatDate(row.enrolled_at)}</td>
              <td>{formatDate(row.last_activity)}</td>
              {includeLastLogin ? <td>{formatDate(row.last_login_at)}</td> : null}
              {includePaymentStatus ? <td>{row.payment_status ? paymentStatusLabels[row.payment_status] : '—'}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StudentModules({
  lessons,
  readonly,
  onAction,
  actionPending,
}: {
  lessons: StudentLesson[];
  readonly: boolean;
  onAction: (lesson: StudentLesson) => void;
  actionPending: boolean;
}) {
  if (lessons.length === 0) {
    return <p className="muted">Под выбранный фильтр уроков нет.</p>;
  }

  const modules = new Map<string, { moduleOrder: number; moduleTitle: string; lessons: StudentLesson[] }>();

  for (const lesson of lessons) {
    const key = `${lesson.module_order}-${lesson.module_title}`;
    if (!modules.has(key)) {
      modules.set(key, {
        moduleOrder: lesson.module_order,
        moduleTitle: lesson.module_title,
        lessons: [],
      });
    }
    modules.get(key)?.lessons.push(lesson);
  }

  const moduleList = Array.from(modules.values()).sort((a, b) => a.moduleOrder - b.moduleOrder);

  return (
    <div className="tree">
      {moduleList.map((module) => (
        <div key={`${module.moduleOrder}-${module.moduleTitle}`} className="tree-module">
          <h3>
            Модуль {module.moduleOrder}: {module.moduleTitle}
          </h3>
          <div className="lesson-list">
            {module.lessons
              .sort((a, b) => a.lesson_order - b.lesson_order)
              .map((lesson) => (
                <article key={lesson.lesson_id} className={`lesson-card ${lesson.is_locked ? 'locked' : ''}`}>
                  <h3>
                    {lesson.module_order}.{lesson.lesson_order} {lesson.lesson_title}
                  </h3>
                  <p>
                    Тип: <strong>{lessonTypeLabels[lesson.lesson_type]}</strong>
                  </p>
                  <p>
                    Статус: <ProgressStatusBadge status={lesson.status} />
                  </p>
                  {lesson.lesson_type === 'test' ? (
                    <p className="muted">
                      Попытки: {lesson.attempts_used}/{lesson.attempts_allowed}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    disabled={
                      readonly
                      || lesson.is_locked
                      || actionPending
                      || (
                        lesson.lesson_type !== 'assignment'
                        && lesson.status === 'completed'
                      )
                      || (
                        lesson.lesson_type === 'assignment'
                        && lesson.status === 'awaiting_review'
                      )
                    }
                    onClick={() => onAction(lesson)}
                  >
                    {lesson.lesson_type === 'assignment'
                      ? 'Перейти к заданию'
                      : lesson.lesson_type === 'test'
                        ? 'Отправить результат теста'
                        : lesson.status === 'completed'
                          ? 'Уже завершен'
                          : 'Завершить урок'}
                  </button>
                </article>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ExecutiveView() {
  const filter = useAnalyticsPeriod();
  const analyticsQuery = useQuery({
    queryKey: ['analytics-executive', filter.period, filter.params.date_from, filter.params.date_to],
    queryFn: () => getExecutiveDashboard(filter.params),
    refetchInterval: 15000,
  });

  const exportTable = async () => {
    try {
      const result = await downloadExecutiveProgramCompletion(filter.params);
      saveBlobAsFile(result.blob, result.filename ?? `executive_program_completion_${Date.now()}.xlsx`);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  const payload = analyticsQuery.data;

  return (
    <div className="role-grid">
      <section className="card card-wide">
        <h2>Дашборд руководителя</h2>
        <AnalyticsPeriodFilter
          period={filter.period}
          setPeriod={filter.setPeriod}
          dateFrom={filter.dateFrom}
          setDateFrom={filter.setDateFrom}
          dateTo={filter.dateTo}
          setDateTo={filter.setDateTo}
        />
        {payload ? (
          <>
            <div className="kpi-grid">
              <KpiCard label="Активные слушатели" value={payload.summary.active_learners} />
              <KpiCard label="Программы" value={payload.summary.programs} />
              <KpiCard label="Группы" value={payload.summary.groups} />
              <KpiCard
                label="Средняя завершаемость"
                value={`${payload.completion_trend.current}% ${payload.completion_trend.direction === 'up' ? '↑' : payload.completion_trend.direction === 'down' ? '↓' : '→'}`}
              />
            </div>

            <div className="toolbar-row">
              <button type="button" onClick={exportTable}>Экспорт таблицы программ в Excel</button>
            </div>

            <div className="role-grid">
              <section className="card">
                <h3>Динамика зачислений по месяцам</h3>
                <SimpleBarChart data={payload.enrollments_by_month.map((item) => ({ label: item.period, value: item.value }))} />
              </section>
              <section className="card">
                <h3>Выручка по месяцам</h3>
                <SimpleBarChart data={payload.revenue_by_month.map((item) => ({ label: item.period, value: item.value }))} valueSuffix=" ₽" />
              </section>
            </div>

            <div className="role-grid">
              <section className="card">
                <h3>Топ-5 программ по слушателям</h3>
                <SimpleBarChart data={payload.top_programs_by_students.map((item) => ({ label: item.program_name, value: item.value }))} />
              </section>
              <section className="card">
                <h3>Топ-5 программ по среднему баллу</h3>
                <SimpleBarChart data={payload.top_programs_by_score.map((item) => ({ label: item.program_name, value: item.value }))} />
              </section>
            </div>

            <h3>Завершаемость по программам</h3>
            {payload.program_completion.length === 0 ? <EmptyAnalytics /> : null}
            {payload.program_completion.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Программа</th>
                      <th>Зачислилось</th>
                      <th>Завершило</th>
                      <th>Отчислилось</th>
                      <th>Завершаемость %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payload.program_completion.map((row) => (
                      <tr key={row.program_id}>
                        <td>{row.program_name}</td>
                        <td>{row.enrolled}</td>
                        <td>{row.completed}</td>
                        <td>{row.dropped}</td>
                        <td>{row.completion_percent}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </>
        ) : analyticsQuery.isLoading ? <p className="muted">Загрузка аналитики...</p> : <p className="error">Не удалось загрузить аналитику.</p>}
      </section>
    </div>
  );
}

function AdminAnalyticsSection() {
  const queryClient = useQueryClient();
  const filter = useAnalyticsPeriod();
  const analyticsQuery = useQuery({
    queryKey: ['analytics-admin', filter.period, filter.params.date_from, filter.params.date_to],
    queryFn: () => getAdminDashboard(filter.params),
    refetchInterval: 15000,
  });

  const reminderMutation = useMutation({
    mutationFn: (studentId: string) =>
      sendReminder({
        student_id: studentId,
        message: 'Напоминание: вы не заходили в LMS более 7 дней. Продолжите обучение.',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analytics-admin'] });
    },
  });

  const exportAction = async (loader: () => Promise<{ blob: Blob; filename: string | null }>, fallbackName: string) => {
    try {
      const result = await loader();
      saveBlobAsFile(result.blob, result.filename ?? fallbackName);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  const payload = analyticsQuery.data;
  return (
    <section className="card card-wide">
      <h2>Аналитика администратора</h2>
      <AnalyticsPeriodFilter
        period={filter.period}
        setPeriod={filter.setPeriod}
        dateFrom={filter.dateFrom}
        setDateFrom={filter.setDateFrom}
        dateTo={filter.dateTo}
        setDateTo={filter.setDateTo}
      />
      {payload ? (
        <>
          <div className="kpi-grid">
            <KpiCard label="Активные слушатели" value={payload.executive.summary.active_learners} />
            <KpiCard label="Программы" value={payload.executive.summary.programs} />
            <KpiCard label="Группы" value={payload.executive.summary.groups} />
            <KpiCard label="Средняя завершаемость" value={`${payload.executive.completion_trend.current}%`} />
          </div>

          <div className="toolbar-row">
            <button type="button" onClick={() => exportAction(() => downloadAdminGroups(filter.params), `admin_groups_${Date.now()}.xlsx`)}>
              Экспорт таблицы групп
            </button>
            <button type="button" onClick={() => exportAction(() => downloadAdminInactiveStudents(filter.params), `admin_inactive_${Date.now()}.xlsx`)}>
              Экспорт неактивных слушателей
            </button>
            <button type="button" onClick={() => exportAction(() => downloadAdminDelayedReviews(filter.params), `admin_review_queue_${Date.now()}.xlsx`)}>
              Экспорт очереди проверки
            </button>
            <button type="button" onClick={() => exportAction(() => downloadAdminIntegrationErrors(filter.params), `admin_integration_errors_${Date.now()}.xlsx`)}>
              Экспорт ошибок интеграций
            </button>
          </div>

          <h3>Таблица групп</h3>
          {payload.groups.length === 0 ? <EmptyAnalytics /> : null}
          {payload.groups.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Группа</th>
                    <th>Программа</th>
                    <th>Дата окончания</th>
                    <th>Слушателей</th>
                    <th>Завершение %</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.groups.map((row) => (
                    <tr key={row.group_id}>
                      <td>{row.group_name}</td>
                      <td>{row.program_name}</td>
                      <td>{formatDate(row.end_date)}</td>
                      <td>{row.students_count}</td>
                      <td>{row.completion_percent}</td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <h3>Слушатели без входа более 7 дней</h3>
          {payload.inactive_students.length === 0 ? <EmptyAnalytics /> : null}
          {payload.inactive_students.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ФИО</th>
                    <th>Программа</th>
                    <th>Группа</th>
                    <th>Прогресс %</th>
                    <th>Последний вход</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.inactive_students.map((row) => (
                    <tr key={`${row.student_id}-${row.group_name}`}>
                      <td>{row.full_name}</td>
                      <td>{row.program_name}</td>
                      <td>{row.group_name}</td>
                      <td>{row.progress_percent}</td>
                      <td>{formatDate(row.last_login_at)}</td>
                      <td>
                        <button type="button" onClick={() => reminderMutation.mutate(row.student_id)} disabled={reminderMutation.isPending}>
                          Отправить напоминание
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <h3>Задания на проверке более 2 дней</h3>
          {payload.delayed_reviews.length === 0 ? <EmptyAnalytics /> : null}
          {payload.delayed_reviews.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Слушатель</th>
                    <th>Группа</th>
                    <th>Урок</th>
                    <th>Преподаватель</th>
                    <th>Поступило</th>
                    <th>Ожидает (дней)</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.delayed_reviews.map((row) => (
                    <tr key={row.assignment_id}>
                      <td>{row.student_name}</td>
                      <td>{row.group_name}</td>
                      <td>{row.lesson_title}</td>
                      <td>{row.teacher_name}</td>
                      <td>{formatDate(row.submitted_at)}</td>
                      <td>{row.waiting_days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <h3>Ошибки интеграций за 30 дней</h3>
          {payload.integration_errors.length === 0 ? <EmptyAnalytics /> : null}
          {payload.integration_errors.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Сервис</th>
                    <th>Операция</th>
                    <th>Ошибка</th>
                    <th>Дата</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.integration_errors.map((row) => (
                    <tr key={row.id}>
                      <td>{row.service}</td>
                      <td>{row.operation}</td>
                      <td>{row.error_text}</td>
                      <td>{formatDate(row.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : analyticsQuery.isLoading ? <p className="muted">Загрузка аналитики...</p> : <p className="error">Не удалось загрузить аналитику.</p>}
    </section>
  );
}

function MethodistAnalyticsSection() {
  const filter = useAnalyticsPeriod();
  const analyticsQuery = useQuery({
    queryKey: ['analytics-methodist', filter.period, filter.params.date_from, filter.params.date_to],
    queryFn: () => getMethodistDashboard(filter.params),
    refetchInterval: 15000,
  });

  const exportAction = async (loader: () => Promise<{ blob: Blob; filename: string | null }>, fallbackName: string) => {
    try {
      const result = await loader();
      saveBlobAsFile(result.blob, result.filename ?? fallbackName);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  const payload = analyticsQuery.data;
  return (
    <section className="card card-wide">
      <h2>Аналитика методиста</h2>
      <AnalyticsPeriodFilter
        period={filter.period}
        setPeriod={filter.setPeriod}
        dateFrom={filter.dateFrom}
        setDateFrom={filter.setDateFrom}
        dateTo={filter.dateTo}
        setDateTo={filter.setDateTo}
      />
      {payload ? (
        <>
          <div className="toolbar-row">
            <button type="button" onClick={() => exportAction(() => downloadMethodistPrograms(filter.params), `methodist_programs_${Date.now()}.xlsx`)}>
              Экспорт метрик программ
            </button>
            <button type="button" onClick={() => exportAction(() => downloadMethodistProblemLessons(filter.params), `methodist_problem_lessons_${Date.now()}.xlsx`)}>
              Экспорт проблемных уроков
            </button>
            <button type="button" onClick={() => exportAction(() => downloadMethodistFunnel(filter.params), `methodist_funnel_${Date.now()}.xlsx`)}>
              Экспорт воронки
            </button>
          </div>

          <h3>Метрики по программам</h3>
          {payload.program_metrics.length === 0 ? <EmptyAnalytics /> : null}
          {payload.program_metrics.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Программа</th>
                    <th>Средний балл</th>
                    <th>Средний прогресс %</th>
                    <th>Средняя длительность (дни)</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.program_metrics.map((row) => (
                    <tr key={row.program_id}>
                      <td>{row.program_name}</td>
                      <td>{row.average_score}</td>
                      <td>{row.average_progress_percent}</td>
                      <td>{row.average_duration_days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <div className="role-grid">
            <section className="card">
              <h3>Воронка прохождения</h3>
              <SimpleBarChart data={payload.program_funnel.map((item) => ({ label: `${item.program_name} / ${item.module_title}`, value: item.reached_count }))} />
            </section>
            <section className="card">
              <h3>Сравнение программ</h3>
              {payload.comparison.left && payload.comparison.right ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Метрика</th>
                        <th>{payload.comparison.left.program_name}</th>
                        <th>{payload.comparison.right.program_name}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Средний балл</td>
                        <td>{payload.comparison.left.average_score}</td>
                        <td>{payload.comparison.right.average_score}</td>
                      </tr>
                      <tr>
                        <td>Средний прогресс %</td>
                        <td>{payload.comparison.left.average_progress_percent}</td>
                        <td>{payload.comparison.right.average_progress_percent}</td>
                      </tr>
                      <tr>
                        <td>Средняя длительность, дни</td>
                        <td>{payload.comparison.left.average_duration_days}</td>
                        <td>{payload.comparison.right.average_duration_days}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyAnalytics />
              )}
            </section>
          </div>

          <h3>Проблемные уроки</h3>
          {payload.problem_lessons.length === 0 ? <EmptyAnalytics /> : null}
          {payload.problem_lessons.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Программа</th>
                    <th>Модуль</th>
                    <th>Урок</th>
                    <th>Повторные попытки</th>
                    <th>Незачёты</th>
                    <th>Средняя задержка (дни)</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.problem_lessons.map((row) => (
                    <tr key={row.lesson_id}>
                      <td>{row.program_name}</td>
                      <td>{row.module_title}</td>
                      <td>{row.lesson_title}</td>
                      <td>{row.repeat_attempts}</td>
                      <td>{row.failed_checks}</td>
                      <td>{row.avg_stuck_days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : analyticsQuery.isLoading ? <p className="muted">Загрузка аналитики...</p> : <p className="error">Не удалось загрузить аналитику.</p>}
    </section>
  );
}

function MethodistView() {
  const queryClient = useQueryClient();
  const [selectedProgramId, setSelectedProgramId] = useState('');
  const [selectedModuleId, setSelectedModuleId] = useState('');

  const [programName, setProgramName] = useState('');
  const [programDescription, setProgramDescription] = useState('');
  const [programIsPaid, setProgramIsPaid] = useState(false);
  const [programPrice, setProgramPrice] = useState(0);
  const [moduleTitle, setModuleTitle] = useState('');
  const [moduleOrder, setModuleOrder] = useState(1);
  const [lessonTitle, setLessonTitle] = useState('');
  const [lessonType, setLessonType] = useState<'video' | 'text' | 'test' | 'assignment'>('text');
  const [lessonOrder, setLessonOrder] = useState(1);
  const [videoUrl, setVideoUrl] = useState('');
  const [textBody, setTextBody] = useState('');
  const [questionsJson, setQuestionsJson] = useState('');
  const [testPassScore, setTestPassScore] = useState(60);
  const [testMaxAttempts, setTestMaxAttempts] = useState(3);
  const [assignmentPassScore, setAssignmentPassScore] = useState(60);

  const [programSearch, setProgramSearch] = useState('');
  const [programStatusFilter, setProgramStatusFilter] = useState<'all' | ProgramStatus>('all');
  const [programSort, setProgramSort] = useState<'asc' | 'desc'>('desc');

  const { data: programs = [] } = useQuery({ queryKey: ['programs-base'], queryFn: () => listPrograms() });

  const { data: catalogPrograms = [], isFetching: loadingCatalog } = useQuery({
    queryKey: ['programs-catalog', programSearch, programStatusFilter, programSort],
    queryFn: () =>
      listPrograms({
        search: programSearch.trim() || undefined,
        status: programStatusFilter === 'all' ? undefined : programStatusFilter,
        sort: programSort,
      }),
  });

  useEffect(() => {
    if (!selectedProgramId && programs.length > 0) {
      setSelectedProgramId(programs[0].id);
    }
  }, [programs, selectedProgramId]);

  const { data: programDetail, isFetching: fetchingDetail } = useQuery({
    queryKey: ['program-detail', selectedProgramId],
    queryFn: () => getProgram(selectedProgramId),
    enabled: Boolean(selectedProgramId),
  });

  useEffect(() => {
    if (!selectedModuleId && programDetail?.modules?.length) {
      setSelectedModuleId(programDetail.modules[0].id);
    }
  }, [programDetail, selectedModuleId]);

  const createProgramMutation = useMutation({
    mutationFn: () =>
      createProgram({
        name: programName,
        description: programDescription,
        is_paid: programIsPaid,
        price_amount: programIsPaid ? programPrice : null,
      }),
    onSuccess: (program) => {
      queryClient.invalidateQueries({ queryKey: ['programs-base'] });
      queryClient.invalidateQueries({ queryKey: ['programs-catalog'] });
      setSelectedProgramId(program.id);
      setProgramName('');
      setProgramDescription('');
      setProgramIsPaid(false);
      setProgramPrice(0);
    },
  });

  const createModuleMutation = useMutation({
    mutationFn: () => createModule(selectedProgramId, { title: moduleTitle, order_index: moduleOrder }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['program-detail', selectedProgramId] });
      setModuleTitle('');
      setModuleOrder(1);
    },
  });

  const createLessonMutation = useMutation({
    mutationFn: () => {
      const payload: {
        title: string;
        type: 'video' | 'text' | 'test' | 'assignment';
        order_index: number;
        video_url?: string;
        text_body?: string;
        questions_json?: Record<string, unknown>;
        test_pass_score?: number;
        test_max_attempts?: number;
        assignment_pass_score?: number;
      } = {
        title: lessonTitle,
        type: lessonType,
        order_index: lessonOrder,
      };

      if (lessonType === 'video') {
        payload.video_url = videoUrl;
      }
      if (lessonType === 'text') {
        payload.text_body = textBody;
      }
      if (lessonType === 'test' && questionsJson.trim()) {
        payload.questions_json = JSON.parse(questionsJson);
        payload.test_pass_score = testPassScore;
        payload.test_max_attempts = testMaxAttempts;
      }
      if (lessonType === 'assignment') {
        payload.assignment_pass_score = assignmentPassScore;
      }

      return createLesson(selectedModuleId, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['program-detail', selectedProgramId] });
      setLessonTitle('');
      setLessonOrder(1);
      setVideoUrl('');
      setTextBody('');
      setQuestionsJson('');
      setTestPassScore(60);
      setTestMaxAttempts(3);
      setAssignmentPassScore(60);
    },
  });

  return (
    <div className="role-grid">
      <MethodistAnalyticsSection />

      <section className="card">
        <h2>Создание программы</h2>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            createProgramMutation.mutate();
          }}
        >
          <input placeholder="Название программы" value={programName} onChange={(event) => setProgramName(event.target.value)} />
          <textarea
            placeholder="Описание"
            rows={3}
            value={programDescription}
            onChange={(event) => setProgramDescription(event.target.value)}
          />
          <label className="stack">
            <span>
              <input
                type="checkbox"
                checked={programIsPaid}
                onChange={(event) => setProgramIsPaid(event.target.checked)}
              />
              {' '}Платная программа
            </span>
          </label>
          {programIsPaid ? (
            <input
              type="number"
              min={0}
              step={1}
              value={programPrice}
              onChange={(event) => setProgramPrice(Number(event.target.value) || 0)}
              placeholder="Стоимость (RUB)"
            />
          ) : null}
          <button type="submit" disabled={createProgramMutation.isPending || programName.trim().length < 2}>Создать программу</button>
        </form>
      </section>

      <section className="card">
        <h2>Модули и уроки</h2>
        <label className="stack">
          <span>Активная программа</span>
          <select value={selectedProgramId} onChange={(event) => setSelectedProgramId(event.target.value)}>
            <option value="">Выберите программу</option>
            {programs.map((program) => (
              <option key={program.id} value={program.id}>
                {program.name}
              </option>
            ))}
          </select>
        </label>

        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            createModuleMutation.mutate();
          }}
        >
          <input placeholder="Название модуля" value={moduleTitle} onChange={(event) => setModuleTitle(event.target.value)} />
          <input
            type="number"
            min={0}
            value={moduleOrder}
            onChange={(event) => setModuleOrder(Number(event.target.value) || 0)}
          />
          <button type="submit" disabled={!selectedProgramId || createModuleMutation.isPending || moduleTitle.trim().length < 1}>Добавить модуль</button>
        </form>

        <label className="stack">
          <span>Модуль для урока</span>
          <select value={selectedModuleId} onChange={(event) => setSelectedModuleId(event.target.value)}>
            <option value="">Выберите модуль</option>
            {programDetail?.modules.map((module) => (
              <option key={module.id} value={module.id}>
                {module.order_index}. {module.title}
              </option>
            ))}
          </select>
        </label>

        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            createLessonMutation.mutate();
          }}
        >
          <input placeholder="Название урока" value={lessonTitle} onChange={(event) => setLessonTitle(event.target.value)} />
          <select value={lessonType} onChange={(event) => setLessonType(event.target.value as 'video' | 'text' | 'test' | 'assignment')}>
            <option value="video">Видео</option>
            <option value="text">Текст</option>
            <option value="test">Тест</option>
            <option value="assignment">Задание</option>
          </select>
          <input
            type="number"
            min={0}
            value={lessonOrder}
            onChange={(event) => setLessonOrder(Number(event.target.value) || 0)}
          />
          {lessonType === 'video' ? (
            <input placeholder="https://..." value={videoUrl} onChange={(event) => setVideoUrl(event.target.value)} />
          ) : null}
          {lessonType === 'text' ? (
            <textarea placeholder="Текст урока" rows={3} value={textBody} onChange={(event) => setTextBody(event.target.value)} />
          ) : null}
          {lessonType === 'test' ? (
            <>
              <textarea
                placeholder='JSON вопросов, например {"q1":"2+2?"}'
                rows={3}
                value={questionsJson}
                onChange={(event) => setQuestionsJson(event.target.value)}
              />
              <input
                type="number"
                min={0}
                max={100}
                value={testPassScore}
                onChange={(event) => setTestPassScore(Number(event.target.value) || 0)}
                placeholder="Проходной балл"
              />
              <input
                type="number"
                min={1}
                max={50}
                value={testMaxAttempts}
                onChange={(event) => setTestMaxAttempts(Number(event.target.value) || 1)}
                placeholder="Лимит попыток"
              />
            </>
          ) : null}
          {lessonType === 'assignment' ? (
            <input
              type="number"
              min={0}
              max={100}
              value={assignmentPassScore}
              onChange={(event) => setAssignmentPassScore(Number(event.target.value) || 0)}
              placeholder="Проходной балл задания"
            />
          ) : null}
          <button type="submit" disabled={!selectedModuleId || lessonTitle.trim().length < 1 || createLessonMutation.isPending}>Добавить урок</button>
        </form>
      </section>

      <section className="card card-wide">
        <h2>Структура программы</h2>
        {fetchingDetail ? <p className="muted">Обновление структуры...</p> : null}
        {!programDetail ? <p className="muted">Создайте программу или выберите существующую.</p> : null}
        {programDetail ? (
          <div className="tree">
            {programDetail.modules.length === 0 ? <p className="muted">Модули пока не добавлены.</p> : null}
            {programDetail.modules.map((module) => (
              <div key={module.id} className="tree-module">
                <h3>
                  Модуль {module.order_index}: {module.title}
                </h3>
                <ul>
                  {module.lessons.length === 0 ? <li className="muted">Уроков пока нет</li> : null}
                  {module.lessons
                    .sort((a, b) => a.order_index - b.order_index)
                    .map((lesson) => (
                      <li key={lesson.id}>
                        {lesson.order_index}. {lesson.title} [{lesson.type}]
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <section className="card card-wide">
        <h2>Список программ</h2>
        <div className="filters-grid">
          <input placeholder="Поиск по названию" value={programSearch} onChange={(event) => setProgramSearch(event.target.value)} />
          <select value={programStatusFilter} onChange={(event) => setProgramStatusFilter(event.target.value as 'all' | ProgramStatus)}>
            <option value="all">Все статусы</option>
            <option value="draft">Черновик</option>
            <option value="active">Активна</option>
            <option value="archived">Архив</option>
          </select>
          <select value={programSort} onChange={(event) => setProgramSort(event.target.value as 'asc' | 'desc')}>
            <option value="desc">Сначала новые</option>
            <option value="asc">Сначала старые</option>
          </select>
        </div>

        {loadingCatalog ? <p className="muted">Обновляем список программ...</p> : null}
        {!loadingCatalog && catalogPrograms.length === 0 ? <p className="muted">Программы не найдены.</p> : null}
        {catalogPrograms.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Тип</th>
                  <th>Статус</th>
                  <th>Дата создания</th>
                </tr>
              </thead>
              <tbody>
                {catalogPrograms.map((program) => (
                  <tr key={program.id}>
                    <td>{program.name}</td>
                    <td>{program.is_paid ? `Платная (${program.price_amount ?? 0} RUB)` : 'Бесплатная'}</td>
                    <td>
                      <ProgramStatusBadge status={program.status} />
                    </td>
                    <td>{formatDate(program.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function AdminView() {
  const queryClient = useQueryClient();
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [studentsInput, setStudentsInput] = useState('');
  const [enrollInfo, setEnrollInfo] = useState('');

  const [tableGroupFilter, setTableGroupFilter] = useState('all');
  const [tableProgramFilter, setTableProgramFilter] = useState('all');
  const [tableProgressFilter, setTableProgressFilter] = useState<'all' | ProgressStatus>('all');
  const [tableSearch, setTableSearch] = useState('');
  const [tableSortBy, setTableSortBy] = useState<'progress_percent' | 'enrolled_at'>('progress_percent');
  const [tableSortOrder, setTableSortOrder] = useState<'asc' | 'desc'>('desc');

  const [groupName, setGroupName] = useState('');
  const [groupProgramId, setGroupProgramId] = useState('');

  const [userEmail, setUserEmail] = useState('');
  const [userFullName, setUserFullName] = useState('');
  const [userPassword, setUserPassword] = useState('');
  const [userRoles, setUserRoles] = useState<Role[]>(['student']);

  const [roleEditRole, setRoleEditRole] = useState<Role>('teacher');

  const [selectedTeacherIds, setSelectedTeacherIds] = useState<string[]>([]);
  const [selectedCuratorIds, setSelectedCuratorIds] = useState<string[]>([]);

  const { data: programs = [] } = useQuery({ queryKey: ['programs-base'], queryFn: () => listPrograms() });
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: listGroups });
  const usersQuery = useQuery({ queryKey: ['users'], queryFn: listUsers });
  const integrationErrorsQuery = useQuery({
    queryKey: ['integration-errors'],
    queryFn: () => listIntegrationErrors({ limit: 20 }),
  });

  useEffect(() => {
    if (!selectedGroupId && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const progressQuery = useQuery({
    queryKey: [
      'progress-table',
      tableGroupFilter,
      tableProgramFilter,
      tableProgressFilter,
      tableSearch,
      tableSortBy,
      tableSortOrder,
    ],
    queryFn: () =>
      getProgressTable({
        group_id: tableGroupFilter === 'all' ? undefined : tableGroupFilter,
        program_id: tableProgramFilter === 'all' ? undefined : tableProgramFilter,
        progress_status: tableProgressFilter === 'all' ? undefined : tableProgressFilter,
        search: tableSearch.trim() || undefined,
        sort_by: tableSortBy,
        sort_order: tableSortOrder,
      }),
  });

  const createGroupMutation = useMutation({
    mutationFn: () => createGroup({ name: groupName, program_id: groupProgramId }),
    onSuccess: (group) => {
      queryClient.invalidateQueries({ queryKey: ['groups'] });
      queryClient.invalidateQueries({ queryKey: ['progress-table'] });
      setSelectedGroupId(group.id);
      setGroupName('');
      setGroupProgramId('');
    },
  });

  const enrollMutation = useMutation({
    mutationFn: () => createEnrollments(selectedGroupId, parseStudentsInput(studentsInput)),
    onSuccess: (rows) => {
      setEnrollInfo(`Зачислено: ${rows.length}`);
      setStudentsInput('');
      queryClient.invalidateQueries({ queryKey: ['progress-table'] });
      queryClient.invalidateQueries({ queryKey: ['groups'] });
    },
    onError: (error) => {
      setEnrollInfo(error instanceof ApiError ? error.message : 'Не удалось зачислить слушателей');
    },
  });

  const createUserMutation = useMutation({
    mutationFn: () =>
      createUser({
        email: userEmail,
        full_name: userFullName,
        password: userPassword,
        roles: userRoles,
        temp_password_required: userRoles.includes('student'),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setUserEmail('');
      setUserFullName('');
      setUserPassword('');
      setUserRoles(['student']);
    },
  });

  const toggleBlockMutation = useMutation({
    mutationFn: ({ userId, blocked }: { userId: string; blocked: boolean }) => blockUser(userId, blocked),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  });

  const addRoleMutation = useMutation({
    mutationFn: ({ user, role }: { user: UserOut; role: Role }) => {
      const nextRoles = Array.from(new Set([...user.roles, role]));
      return updateUserRoles(user.id, nextRoles);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  });

  const assignMentorsMutation = useMutation({
    mutationFn: async () => {
      await assignGroupTeachers(selectedGroupId, selectedTeacherIds);
      await assignGroupCurators(selectedGroupId, selectedCuratorIds);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'] });
      setSelectedTeacherIds([]);
      setSelectedCuratorIds([]);
    },
  });

  const tableRows = progressQuery.data?.rows ?? [];

  const users = usersQuery.data ?? [];
  const teachers = users.filter((item) => item.roles.includes('teacher'));
  const curators = users.filter((item) => item.roles.includes('curator'));

  const exportToExcel = async () => {
    if (!selectedGroupId) {
      window.alert('Сначала выберите группу');
      return;
    }
    try {
      const result = await downloadGroupFinalReport(selectedGroupId);
      saveBlobAsFile(result.blob, result.filename ?? `group_${selectedGroupId}_final.xlsx`);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  return (
    <div className="role-grid">
      <AdminAnalyticsSection />

      <section className="card">
        <h2>Создание группы</h2>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            createGroupMutation.mutate();
          }}
        >
          <input placeholder="Название группы" value={groupName} onChange={(event) => setGroupName(event.target.value)} />
          <select value={groupProgramId} onChange={(event) => setGroupProgramId(event.target.value)}>
            <option value="">Выберите программу</option>
            {programs.map((program) => (
              <option key={program.id} value={program.id}>
                {program.name}
              </option>
            ))}
          </select>
          <button type="submit" disabled={createGroupMutation.isPending || !groupName.trim() || !groupProgramId}>Создать группу</button>
        </form>
      </section>

      <section className="card">
        <h2>Зачисление слушателей</h2>
        <label className="stack">
          <span>Группа</span>
          <select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
            <option value="">Выберите группу</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
        <textarea
          rows={6}
          value={studentsInput}
          onChange={(event) => setStudentsInput(event.target.value)}
          placeholder={'Одна строка = один слушатель.\nФормат: ФИО,email\nПример: Иван Иванов,ivan@example.com'}
        />
        <button
          type="button"
          onClick={() => enrollMutation.mutate()}
          disabled={!selectedGroupId || !studentsInput.trim() || enrollMutation.isPending}
        >
          Зачислить
        </button>
        {enrollInfo ? <p className="muted">{enrollInfo}</p> : null}
      </section>

      <section className="card card-wide">
        <h2>Таблица слушателей</h2>
        <div className="filters-grid">
          <select value={tableGroupFilter} onChange={(event) => setTableGroupFilter(event.target.value)}>
            <option value="all">Все группы</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>

          <select value={tableProgramFilter} onChange={(event) => setTableProgramFilter(event.target.value)}>
            <option value="all">Все программы</option>
            {programs.map((program) => (
              <option key={program.id} value={program.id}>
                {program.name}
              </option>
            ))}
          </select>

          <select value={tableProgressFilter} onChange={(event) => setTableProgressFilter(event.target.value as 'all' | ProgressStatus)}>
            <option value="all">Все статусы</option>
            <option value="not_started">Не начал</option>
            <option value="in_progress">В процессе</option>
            <option value="completed">Завершил</option>
          </select>

          <input placeholder="Поиск по ФИО" value={tableSearch} onChange={(event) => setTableSearch(event.target.value)} />

          <select value={tableSortBy} onChange={(event) => setTableSortBy(event.target.value as 'progress_percent' | 'enrolled_at')}>
            <option value="progress_percent">Сортировать по прогрессу</option>
            <option value="enrolled_at">Сортировать по дате зачисления</option>
          </select>

          <select value={tableSortOrder} onChange={(event) => setTableSortOrder(event.target.value as 'asc' | 'desc')}>
            <option value="desc">По убыванию</option>
            <option value="asc">По возрастанию</option>
          </select>
        </div>

        <div className="toolbar-row">
          <button type="button" onClick={exportToExcel} disabled={tableRows.length === 0}>Экспорт в Excel</button>
          <span className="muted">Строк в таблице: {tableRows.length}</span>
        </div>

        {progressQuery.data ? <StudentsProgressTable rows={tableRows} includeLastLogin includePaymentStatus /> : null}
      </section>

      <section className="card card-wide">
        <h2>Ошибки интеграций</h2>
        {(integrationErrorsQuery.data ?? []).length === 0 ? <p className="muted">Ошибок интеграций нет.</p> : null}
        {(integrationErrorsQuery.data ?? []).map((item: IntegrationErrorOut) => (
          <article key={item.id} className="lesson-card">
            <p><strong>{item.service}</strong> / {item.operation}</p>
            <p>{item.error_text}</p>
            <p className="muted">{formatDate(item.created_at)}</p>
          </article>
        ))}
      </section>

      <section className="card card-wide">
        <h2>Управление пользователями</h2>
        <form
          className="filters-grid"
          onSubmit={(event) => {
            event.preventDefault();
            createUserMutation.mutate();
          }}
        >
          <input placeholder="Email" value={userEmail} onChange={(event) => setUserEmail(event.target.value)} />
          <input placeholder="ФИО" value={userFullName} onChange={(event) => setUserFullName(event.target.value)} />
          <input type="password" placeholder="Пароль" value={userPassword} onChange={(event) => setUserPassword(event.target.value)} />
          <select value={userRoles[0]} onChange={(event) => setUserRoles([event.target.value as Role])}>
            {roleCatalog.map((role) => (
              <option key={role} value={role}>
                {roleLabels[role]}
              </option>
            ))}
          </select>
          <button type="submit" disabled={createUserMutation.isPending || !userEmail || !userFullName || userPassword.length < 8}>Создать пользователя</button>
        </form>

        <label className="stack">
          <span>Быстрое добавление роли существующему пользователю</span>
          <select value={roleEditRole} onChange={(event) => setRoleEditRole(event.target.value as Role)}>
            {roleCatalog.map((role) => (
              <option key={role} value={role}>
                {roleLabels[role]}
              </option>
            ))}
          </select>
        </label>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>ФИО</th>
                <th>Роли</th>
                <th>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.email}</td>
                  <td>{user.full_name}</td>
                  <td>{user.roles.map((role) => roleLabels[role]).join(', ')}</td>
                  <td>{user.blocked ? 'Заблокирован' : 'Активен'}</td>
                  <td className="actions-cell">
                    <button type="button" onClick={() => toggleBlockMutation.mutate({ userId: user.id, blocked: !user.blocked })}>
                      {user.blocked ? 'Разблокировать' : 'Заблокировать'}
                    </button>
                    <button type="button" onClick={() => addRoleMutation.mutate({ user, role: roleEditRole })}>Добавить роль</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card card-wide">
        <h2>Назначение преподавателей и кураторов</h2>
        <div className="filters-grid">
          <select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
            <option value="">Выберите группу</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>

          <select
            multiple
            value={selectedTeacherIds}
            onChange={(event) => setSelectedTeacherIds(Array.from(event.target.selectedOptions).map((item) => item.value))}
          >
            {teachers.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name} ({user.email})
              </option>
            ))}
          </select>

          <select
            multiple
            value={selectedCuratorIds}
            onChange={(event) => setSelectedCuratorIds(Array.from(event.target.selectedOptions).map((item) => item.value))}
          >
            {curators.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name} ({user.email})
              </option>
            ))}
          </select>
        </div>
        <button type="button" onClick={() => assignMentorsMutation.mutate()} disabled={!selectedGroupId || assignMentorsMutation.isPending}>
          Сохранить назначения
        </button>
      </section>
    </div>
  );
}

function StudentView({ me }: { me: MeResponse }) {
  const queryClient = useQueryClient();
  const studentId = me.user.student_id;
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [lessonTypeFilter, setLessonTypeFilter] = useState<LessonFilterType>('all');
  const [selectedAssignmentLessonId, setSelectedAssignmentLessonId] = useState('');
  const [assignmentText, setAssignmentText] = useState('');
  const [questionText, setQuestionText] = useState('');

  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: listGroups });

  useEffect(() => {
    if (!selectedGroupId && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const lessonsQuery = useQuery({
    queryKey: ['student-lessons', selectedGroupId, studentId],
    queryFn: () => getStudentLessons(studentId ?? '', selectedGroupId),
    enabled: Boolean(selectedGroupId && studentId),
  });
  const paymentQuery = useQuery({
    queryKey: ['student-payment', selectedGroupId, studentId],
    queryFn: () => getStudentPayment(studentId ?? '', selectedGroupId),
    enabled: Boolean(selectedGroupId && studentId),
  });
  const telegramQuery = useQuery({ queryKey: ['telegram-link'], queryFn: getTelegramLink });
  const calendarQuery = useQuery({
    queryKey: ['student-calendar-links', selectedGroupId, studentId],
    queryFn: () => getCalendarLinks(studentId ?? '', selectedGroupId),
    enabled: Boolean(selectedGroupId && studentId),
  });

  const contentMutation = useMutation({
    mutationFn: (input: { lessonId: string; lessonType: 'video' | 'text' }) =>
      engageLesson(studentId ?? '', input.lessonId, {
        group_id: selectedGroupId,
        opened: true,
        watched_to_end: input.lessonType === 'video',
        scrolled_to_bottom: input.lessonType === 'text',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['student-lessons', selectedGroupId, studentId] });
      queryClient.invalidateQueries({ queryKey: ['progress-table-student'] });
    },
  });

  const testMutation = useMutation({
    mutationFn: (input: { lessonId: string; score: number }) =>
      submitTestAttempt(studentId ?? '', input.lessonId, {
        group_id: selectedGroupId,
        score: input.score,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['student-lessons', selectedGroupId, studentId] });
      queryClient.invalidateQueries({ queryKey: ['progress-table-student'] });
    },
  });

  const assignmentsQuery = useQuery({ queryKey: ['my-assignments'], queryFn: listMyAssignments });
  const questionsQuery = useQuery({ queryKey: ['my-questions'], queryFn: listQuestions });
  const remindersQuery = useQuery({ queryKey: ['my-reminders'], queryFn: listReminders });
  const notificationsQuery = useQuery({ queryKey: ['my-notifications'], queryFn: () => listNotifications() });

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationsRead([notificationId]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-notifications'] });
    },
  });

  const submitAssignmentMutation = useMutation({
    mutationFn: () =>
      submitAssignment({
        group_id: selectedGroupId,
        lesson_id: selectedAssignmentLessonId,
        submission_text: assignmentText,
      }),
    onSuccess: () => {
      setAssignmentText('');
      queryClient.invalidateQueries({ queryKey: ['my-assignments'] });
    },
  });

  const askQuestionMutation = useMutation({
    mutationFn: () => createQuestion({ group_id: selectedGroupId, question_text: questionText }),
    onSuccess: () => {
      setQuestionText('');
      queryClient.invalidateQueries({ queryKey: ['my-questions'] });
    },
  });

  const filteredLessons = useMemo(() => {
    const lessons = lessonsQuery.data?.lessons ?? [];
    if (lessonTypeFilter === 'all') {
      return lessons;
    }
    return lessons.filter((lesson) => lesson.lesson_type === lessonTypeFilter);
  }, [lessonTypeFilter, lessonsQuery.data?.lessons]);

  const assignmentLessons = (lessonsQuery.data?.lessons ?? []).filter((lesson) => lesson.lesson_type === 'assignment');
  const paymentRequired = paymentQuery.data ? paymentQuery.data.payment_status !== 'not_required' : false;

  return (
    <div className="role-grid">
      <section className="card">
        <h2>Мои группы и уроки</h2>
        <label className="stack">
          <span>Группа</span>
          <select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
            <option value="">Выберите группу</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>

        <div className="stack">
          <h3>Telegram</h3>
          <p className="muted">
            Статус: {telegramQuery.data?.linked ? `привязан (@${telegramQuery.data.telegram_username ?? 'unknown'})` : 'не привязан'}
          </p>
          <button
            type="button"
            disabled={!telegramQuery.data?.invite_url}
            onClick={() => window.open(telegramQuery.data?.invite_url ?? '#', '_blank')}
          >
            {telegramQuery.data?.linked ? 'Открыть привязку Telegram' : 'Привязать Telegram'}
          </button>
        </div>

        <div className="stack">
          <h3>Календарь</h3>
          <div className="filters-grid">
            <button type="button" disabled={!calendarQuery.data?.google_url} onClick={() => window.open(calendarQuery.data?.google_url ?? '#', '_blank')}>
              Google Calendar
            </button>
            <button type="button" disabled={!calendarQuery.data?.yandex_url} onClick={() => window.open(calendarQuery.data?.yandex_url ?? '#', '_blank')}>
              Яндекс.Календарь
            </button>
            <button type="button" disabled={!calendarQuery.data?.ics_url} onClick={() => window.open(calendarQuery.data?.ics_url ?? '#', '_blank')}>
              Скачать ICS
            </button>
          </div>
        </div>

        <div className="stack">
          <h3>Оплата</h3>
          <p className="muted">
            Статус: {paymentQuery.data ? paymentStatusLabels[paymentQuery.data.payment_status] : '—'}
          </p>
          {paymentRequired && paymentQuery.data?.payment_status !== 'paid' ? (
            <button type="button" disabled={!paymentQuery.data?.payment_link} onClick={() => window.open(paymentQuery.data?.payment_link ?? '#', '_blank')}>
              Перейти к оплате
            </button>
          ) : null}
        </div>

        <label className="stack">
          <span>Фильтр по типу урока</span>
          <select value={lessonTypeFilter} onChange={(event) => setLessonTypeFilter(event.target.value as LessonFilterType)}>
            <option value="all">Все типы</option>
            <option value="video">Видео</option>
            <option value="text">Текст</option>
            <option value="test">Тест</option>
            <option value="assignment">Задание</option>
          </select>
        </label>
      </section>

      <section className="card card-wide">
        <h2>Уроки</h2>
        {paymentRequired && paymentQuery.data?.payment_status !== 'paid' ? (
          <p className="error">Доступ к урокам откроется после подтверждения оплаты.</p>
        ) : null}
        {lessonsQuery.isError ? <p className="error">Не удалось загрузить уроки: возможно, требуется оплата.</p> : null}
        {lessonsQuery.data ? (
          <>
            <p className="muted">
              Завершено: {lessonsQuery.data.completed} из {lessonsQuery.data.total}
            </p>
            <p className="muted">Статус программы: <ProgressStatusBadge status={lessonsQuery.data.program_status} /></p>
            <StudentModules
              lessons={filteredLessons}
              readonly={false}
              actionPending={contentMutation.isPending || testMutation.isPending}
              onAction={(lesson) => {
                if (lesson.lesson_type === 'assignment') {
                  setSelectedAssignmentLessonId(lesson.lesson_id);
                  return;
                }
                if (lesson.lesson_type === 'test') {
                  const rawScore = window.prompt('Введите результат теста (0-100)');
                  if (rawScore === null) {
                    return;
                  }
                  const score = Number(rawScore);
                  if (Number.isNaN(score) || score < 0 || score > 100) {
                    window.alert('Нужно указать число от 0 до 100');
                    return;
                  }
                  testMutation.mutate({ lessonId: lesson.lesson_id, score });
                  return;
                }
                contentMutation.mutate({ lessonId: lesson.lesson_id, lessonType: lesson.lesson_type });
              }}
            />
          </>
        ) : null}
      </section>

      <section className="card">
        <h2>Мои задания</h2>
        <label className="stack">
          <span>Урок</span>
          <select value={selectedAssignmentLessonId} onChange={(event) => setSelectedAssignmentLessonId(event.target.value)}>
            <option value="">Выберите урок</option>
            {assignmentLessons.map((lesson) => (
              <option key={lesson.lesson_id} value={lesson.lesson_id}>
                {lesson.module_order}.{lesson.lesson_order} {lesson.lesson_title}
              </option>
            ))}
          </select>
        </label>
        <textarea rows={4} value={assignmentText} onChange={(event) => setAssignmentText(event.target.value)} placeholder="Ответ по заданию" />
        <button
          type="button"
          disabled={!selectedGroupId || !selectedAssignmentLessonId || !assignmentText.trim() || submitAssignmentMutation.isPending}
          onClick={() => submitAssignmentMutation.mutate()}
        >
          Отправить на проверку
        </button>

        <div className="stack">
          {(assignmentsQuery.data ?? []).map((item: AssignmentOut) => (
            <article key={item.id} className="lesson-card">
              <h3>{item.lesson_title}</h3>
              <p>
                Статус: {item.status === 'reviewed'
                  ? 'Проверено'
                  : item.status === 'returned_for_revision'
                    ? 'Возвращено на доработку'
                    : 'На проверке'}
              </p>
              <p>Оценка: {item.grade ?? '—'}</p>
              <p>Комментарий преподавателя: {item.teacher_comment ?? '—'}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Уведомления</h2>
        {(notificationsQuery.data ?? []).length === 0 ? <p className="muted">Уведомлений пока нет.</p> : null}
        {(notificationsQuery.data ?? []).slice(0, 8).map((item: NotificationOut) => (
          <article key={item.id} className="lesson-card">
            <p><strong>{item.subject}</strong></p>
            <p>{item.body}</p>
            <p className="muted">Канал: {channelLabel(item.channel)} • {formatDate(item.created_at)}</p>
            <button type="button" disabled={item.is_read || markReadMutation.isPending} onClick={() => markReadMutation.mutate(item.id)}>
              {item.is_read ? 'Прочитано' : 'Отметить как прочитанное'}
            </button>
          </article>
        ))}
      </section>

      <section className="card">
        <h2>Вопросы куратору</h2>
        <textarea rows={3} value={questionText} onChange={(event) => setQuestionText(event.target.value)} placeholder="Ваш вопрос" />
        <button type="button" disabled={!selectedGroupId || !questionText.trim() || askQuestionMutation.isPending} onClick={() => askQuestionMutation.mutate()}>
          Отправить вопрос
        </button>

        <div className="stack">
          {(questionsQuery.data ?? []).map((item: QuestionOut) => (
            <article key={item.id} className="lesson-card">
              <p>{item.question_text}</p>
              <p className="muted">Ответ: {item.answer_text ?? 'Пока нет ответа'}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="card card-wide">
        <h2>Напоминания</h2>
        {(remindersQuery.data ?? []).length === 0 ? <p className="muted">Напоминаний пока нет.</p> : null}
        {(remindersQuery.data ?? []).map((item: ReminderOut) => (
          <article key={item.id} className="lesson-card">
            <p>{item.message}</p>
            <p className="muted">Отправлено: {formatDate(item.sent_at)}</p>
          </article>
        ))}
      </section>
    </div>
  );
}

function TeacherAnalyticsSection() {
  const filter = useAnalyticsPeriod();
  const analyticsQuery = useQuery({
    queryKey: ['analytics-teacher', filter.period, filter.params.date_from, filter.params.date_to],
    queryFn: () => getTeacherDashboard(filter.params),
    refetchInterval: 15000,
  });

  const exportAction = async (loader: () => Promise<{ blob: Blob; filename: string | null }>, fallbackName: string) => {
    try {
      const result = await loader();
      saveBlobAsFile(result.blob, result.filename ?? fallbackName);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  const payload = analyticsQuery.data;
  return (
    <section className="card card-wide">
      <h2>Аналитика преподавателя</h2>
      <AnalyticsPeriodFilter
        period={filter.period}
        setPeriod={filter.setPeriod}
        dateFrom={filter.dateFrom}
        setDateFrom={filter.setDateFrom}
        dateTo={filter.dateTo}
        setDateTo={filter.setDateTo}
      />
      {payload ? (
        <>
          <div className="toolbar-row">
            <button type="button" onClick={() => exportAction(() => downloadTeacherCourses(filter.params), `teacher_courses_${Date.now()}.xlsx`)}>
              Экспорт курсов
            </button>
            <button type="button" onClick={() => exportAction(() => downloadTeacherReviewQueue(filter.params), `teacher_queue_${Date.now()}.xlsx`)}>
              Экспорт очереди проверки
            </button>
          </div>

          <div className="kpi-grid">
            <KpiCard label="Среднее время проверки (часы)" value={payload.average_review_hours} />
            <KpiCard
              label="Урок с наибольшим числом вопросов"
              value={payload.most_questions_lesson ? `${payload.most_questions_lesson.lesson_title} (${payload.most_questions_lesson.questions_count})` : '—'}
            />
          </div>

          <h3>По своим курсам</h3>
          {payload.courses.length === 0 ? <EmptyAnalytics /> : null}
          <div className="role-grid">
            {payload.courses.map((course) => (
              <article key={course.group_id} className="card">
                <h3>{course.program_name}</h3>
                <p className="muted">Группа: {course.group_name}</p>
                <p><strong>Средний балл:</strong> {course.average_score}</p>
                <SimpleBarChart data={course.distribution.map((item) => ({ label: item.bucket, value: item.count }))} />
              </article>
            ))}
          </div>

          <h3>Очередь заданий на проверку</h3>
          {payload.review_queue.length === 0 ? <EmptyAnalytics /> : null}
          {payload.review_queue.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Слушатель</th>
                    <th>Группа</th>
                    <th>Урок</th>
                    <th>Поступило</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.review_queue.map((item) => (
                    <tr key={item.assignment_id}>
                      <td>{item.student_name}</td>
                      <td>{item.group_name}</td>
                      <td>{item.lesson_title}</td>
                      <td>{formatDate(item.submitted_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : analyticsQuery.isLoading ? <p className="muted">Загрузка аналитики...</p> : <p className="error">Не удалось загрузить аналитику.</p>}
    </section>
  );
}

function CuratorAnalyticsSection() {
  const filter = useAnalyticsPeriod();
  const analyticsQuery = useQuery({
    queryKey: ['analytics-curator', filter.period, filter.params.date_from, filter.params.date_to],
    queryFn: () => getCuratorDashboard(filter.params),
    refetchInterval: 15000,
  });

  const exportAction = async (loader: () => Promise<{ blob: Blob; filename: string | null }>, fallbackName: string) => {
    try {
      const result = await loader();
      saveBlobAsFile(result.blob, result.filename ?? fallbackName);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  const payload = analyticsQuery.data;
  return (
    <section className="card card-wide">
      <h2>Аналитика куратора</h2>
      <AnalyticsPeriodFilter
        period={filter.period}
        setPeriod={filter.setPeriod}
        dateFrom={filter.dateFrom}
        setDateFrom={filter.setDateFrom}
        dateTo={filter.dateTo}
        setDateTo={filter.setDateTo}
      />
      {payload ? (
        <>
          <div className="toolbar-row">
            <button type="button" onClick={() => exportAction(() => downloadCuratorStudents(filter.params), `curator_students_${Date.now()}.xlsx`)}>
              Экспорт прогресса слушателей
            </button>
            <button type="button" onClick={() => exportAction(() => downloadCuratorReminders(filter.params), `curator_reminders_${Date.now()}.xlsx`)}>
              Экспорт истории напоминаний
            </button>
          </div>

          <div className="kpi-grid">
            <KpiCard label="Зелёный статус" value={payload.signal_counts.green} />
            <KpiCard label="Жёлтый статус" value={payload.signal_counts.yellow} />
            <KpiCard label="Красный статус" value={payload.signal_counts.red} />
          </div>

          <h3>Прогресс слушателей</h3>
          {payload.students.length === 0 ? <EmptyAnalytics /> : null}
          {payload.students.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ФИО</th>
                    <th>Программа</th>
                    <th>Группа</th>
                    <th>Прогресс %</th>
                    <th>Последний вход</th>
                    <th>Текущий урок</th>
                    <th>Светофор</th>
                    <th>Дней до конца</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.students.map((row) => (
                    <tr key={`${row.student_id}-${row.group_name}`}>
                      <td>{row.full_name}</td>
                      <td>{row.program_name}</td>
                      <td>{row.group_name}</td>
                      <td>{row.progress_percent}</td>
                      <td>{formatDate(row.last_login_at)}</td>
                      <td>{row.current_lesson ?? '—'}</td>
                      <td>
                        <span className={`status-pill status-${row.signal === 'green' ? 'completed' : row.signal === 'yellow' ? 'in_progress' : 'not_started'}`}>
                          {row.signal === 'green' ? 'Зелёный' : row.signal === 'yellow' ? 'Жёлтый' : 'Красный'}
                        </span>
                      </td>
                      <td>{row.days_left ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <h3>История напоминаний</h3>
          {payload.reminders.length === 0 ? <EmptyAnalytics /> : null}
          {payload.reminders.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Слушатель</th>
                    <th>Текст</th>
                    <th>Когда</th>
                    <th>Был эффект</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.reminders.map((row) => (
                    <tr key={row.id}>
                      <td>{row.student_name}</td>
                      <td>{row.message}</td>
                      <td>{formatDate(row.sent_at)}</td>
                      <td>{row.effect ? 'Да' : 'Нет'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : analyticsQuery.isLoading ? <p className="muted">Загрузка аналитики...</p> : <p className="error">Не удалось загрузить аналитику.</p>}
    </section>
  );
}

function CustomerAnalyticsSection() {
  const filter = useAnalyticsPeriod();
  const analyticsQuery = useQuery({
    queryKey: ['analytics-customer', filter.period, filter.params.date_from, filter.params.date_to],
    queryFn: () => getCustomerDashboard(filter.params),
    refetchInterval: 15000,
  });

  const exportEmployees = async () => {
    try {
      const result = await downloadCustomerEmployees(filter.params);
      saveBlobAsFile(result.blob, result.filename ?? `customer_employees_${Date.now()}.xlsx`);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  const payload = analyticsQuery.data;
  return (
    <section className="card card-wide">
      <h2>Аналитика заказчика</h2>
      <AnalyticsPeriodFilter
        period={filter.period}
        setPeriod={filter.setPeriod}
        dateFrom={filter.dateFrom}
        setDateFrom={filter.setDateFrom}
        dateTo={filter.dateTo}
        setDateTo={filter.setDateTo}
      />
      {payload ? (
        <>
          <div className="toolbar-row">
            <button type="button" onClick={exportEmployees}>Экспорт сотрудников в Excel</button>
          </div>

          <div className="kpi-grid">
            <KpiCard label="Завершили" value={payload.summary.completed} />
            <KpiCard label="В процессе" value={payload.summary.in_progress} />
            <KpiCard label="Не начали" value={payload.summary.not_started} />
          </div>

          <h3>Динамика прохождения по неделям</h3>
          <SimpleBarChart data={payload.weekly_progress.map((item) => ({ label: item.period, value: item.value }))} valueSuffix="%" />

          <h3>Сотрудники</h3>
          {payload.employees.length === 0 ? <EmptyAnalytics /> : null}
          {payload.employees.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ФИО</th>
                    <th>Программа</th>
                    <th>Группа</th>
                    <th>Прогресс %</th>
                    <th>Статус</th>
                    <th>Последний вход</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.employees.map((row) => (
                    <tr key={`${row.student_id}-${row.group_name}`}>
                      <td>{row.full_name}</td>
                      <td>{row.program_name}</td>
                      <td>{row.group_name}</td>
                      <td>{row.progress_percent}</td>
                      <td>{row.status}</td>
                      <td>{formatDate(row.last_login_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : analyticsQuery.isLoading ? <p className="muted">Загрузка аналитики...</p> : <p className="error">Не удалось загрузить аналитику.</p>}
    </section>
  );
}

function TeacherView() {
  const queryClient = useQueryClient();
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [selectedStudentId, setSelectedStudentId] = useState('');
  const [lessonTypeFilter, setLessonTypeFilter] = useState<LessonFilterType>('all');
  const [gradeMap, setGradeMap] = useState<Record<string, string>>({});
  const [commentMap, setCommentMap] = useState<Record<string, string>>({});

  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: listGroups });
  useEffect(() => {
    if (!selectedGroupId && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const progressQuery = useQuery({
    queryKey: ['teacher-progress', selectedGroupId],
    queryFn: () => getProgressTable({ group_id: selectedGroupId }),
    enabled: Boolean(selectedGroupId),
  });

  const queueQuery = useQuery({ queryKey: ['review-queue'], queryFn: listAssignmentReviewQueue });

  const reviewMutation = useMutation({
    mutationFn: (input: { assignmentId: string; returnForRevision: boolean }) =>
      reviewAssignment(input.assignmentId, {
        grade: gradeMap[input.assignmentId] ? Number(gradeMap[input.assignmentId]) : undefined,
        teacher_comment: commentMap[input.assignmentId] || undefined,
        return_for_revision: input.returnForRevision,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-queue'] });
    },
  });

  const rows = progressQuery.data?.rows ?? [];
  const queue = (queueQuery.data ?? []).filter((item) => !selectedGroupId || item.group_id === selectedGroupId);
  useEffect(() => {
    if (!selectedStudentId && rows.length > 0) {
      setSelectedStudentId(rows[0].student_id);
    }
  }, [rows, selectedStudentId]);

  const lessonsQuery = useQuery({
    queryKey: ['teacher-student-lessons', selectedGroupId, selectedStudentId],
    queryFn: () => getStudentLessons(selectedStudentId, selectedGroupId),
    enabled: Boolean(selectedGroupId && selectedStudentId),
  });

  const filteredLessons = useMemo(() => {
    const lessons = lessonsQuery.data?.lessons ?? [];
    if (lessonTypeFilter === 'all') {
      return lessons;
    }
    return lessons.filter((lesson) => lesson.lesson_type === lessonTypeFilter);
  }, [lessonTypeFilter, lessonsQuery.data?.lessons]);

  return (
    <div className="role-grid">
      <TeacherAnalyticsSection />

      <section className="card">
        <h2>Мои группы</h2>
        <select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
          <option value="">Выберите группу</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>

        <label className="stack">
          <span>Слушатель</span>
          <select value={selectedStudentId} onChange={(event) => setSelectedStudentId(event.target.value)}>
            <option value="">Выберите слушателя</option>
            {rows.map((row) => (
              <option key={row.student_id} value={row.student_id}>
                {row.full_name}
              </option>
            ))}
          </select>
        </label>

        <label className="stack">
          <span>Тип урока</span>
          <select value={lessonTypeFilter} onChange={(event) => setLessonTypeFilter(event.target.value as LessonFilterType)}>
            <option value="all">Все типы</option>
            <option value="video">Видео</option>
            <option value="text">Текст</option>
            <option value="test">Тест</option>
            <option value="assignment">Задание</option>
          </select>
        </label>
      </section>

      <section className="card card-wide">
        <h2>Прогресс слушателей</h2>
        <StudentsProgressTable rows={rows} includeLastLogin />
      </section>

      <section className="card card-wide">
        <h2>Статусы уроков выбранного слушателя</h2>
        {lessonsQuery.data ? (
          <StudentModules lessons={filteredLessons} readonly actionPending={false} onAction={() => undefined} />
        ) : (
          <p className="muted">Выберите группу и слушателя.</p>
        )}
      </section>

      <section className="card card-wide">
        <h2>Задания на проверку</h2>
        {queue.length === 0 ? <p className="muted">Новых заданий нет.</p> : null}
        {queue.map((item) => (
          <article key={item.id} className="lesson-card">
            <h3>{item.lesson_title}</h3>
            <p>{item.student_name} • {item.group_name}</p>
            <p>{item.submission_text}</p>
            <div className="filters-grid">
              <input
                type="number"
                min={0}
                max={100}
                placeholder="Оценка"
                value={gradeMap[item.id] ?? ''}
                onChange={(event) => setGradeMap((prev) => ({ ...prev, [item.id]: event.target.value }))}
              />
              <input
                placeholder="Комментарий"
                value={commentMap[item.id] ?? ''}
                onChange={(event) => setCommentMap((prev) => ({ ...prev, [item.id]: event.target.value }))}
              />
              <button type="button" onClick={() => reviewMutation.mutate({ assignmentId: item.id, returnForRevision: false })}>
                Проверить
              </button>
              <button type="button" onClick={() => reviewMutation.mutate({ assignmentId: item.id, returnForRevision: true })}>
                Вернуть на доработку
              </button>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function CuratorView() {
  const queryClient = useQueryClient();
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [selectedStudentId, setSelectedStudentId] = useState('');
  const [reminderText, setReminderText] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: listGroups });
  useEffect(() => {
    if (!selectedGroupId && groups.length > 0) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  const progressQuery = useQuery({
    queryKey: ['curator-progress', selectedGroupId],
    queryFn: () => getProgressTable({ group_id: selectedGroupId }),
    enabled: Boolean(selectedGroupId),
  });

  const questionsQuery = useQuery({ queryKey: ['curator-questions'], queryFn: listQuestions });

  const reminderMutation = useMutation({
    mutationFn: () => sendReminder({ student_id: selectedStudentId, message: reminderText }),
    onSuccess: () => {
      setReminderText('');
      queryClient.invalidateQueries({ queryKey: ['reminders'] });
    },
  });

  const answerMutation = useMutation({
    mutationFn: (questionId: string) => answerQuestion(questionId, { answer_text: answers[questionId] ?? '' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['curator-questions'] });
    },
  });

  const rows = progressQuery.data?.rows ?? [];
  const questions = (questionsQuery.data ?? []).filter((item) => !selectedGroupId || item.group_id === selectedGroupId);

  return (
    <div className="role-grid">
      <CuratorAnalyticsSection />

      <section className="card">
        <h2>Мои слушатели</h2>
        <select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
          <option value="">Выберите группу</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>

        <label className="stack">
          <span>Кому отправить напоминание</span>
          <select value={selectedStudentId} onChange={(event) => setSelectedStudentId(event.target.value)}>
            <option value="">Выберите слушателя</option>
            {rows.map((row) => (
              <option key={row.student_id} value={row.student_id}>
                {row.full_name}
              </option>
            ))}
          </select>
        </label>
        <textarea rows={3} value={reminderText} onChange={(event) => setReminderText(event.target.value)} placeholder="Текст напоминания" />
        <button type="button" disabled={!selectedStudentId || !reminderText.trim() || reminderMutation.isPending} onClick={() => reminderMutation.mutate()}>
          Отправить напоминание
        </button>
      </section>

      <section className="card card-wide">
        <h2>Прогресс и даты последнего входа</h2>
        <StudentsProgressTable rows={rows} includeLastLogin />
      </section>

      <section className="card card-wide">
        <h2>Вопросы слушателей</h2>
        {questions.length === 0 ? <p className="muted">Новых вопросов нет.</p> : null}
        {questions.map((item) => (
          <article key={item.id} className="lesson-card">
            <p><strong>{item.student_name}:</strong> {item.question_text}</p>
            <p className="muted">Текущий ответ: {item.answer_text ?? 'не отвечено'}</p>
            <div className="filters-grid">
              <input
                placeholder="Ответ"
                value={answers[item.id] ?? ''}
                onChange={(event) => setAnswers((prev) => ({ ...prev, [item.id]: event.target.value }))}
              />
              <button type="button" onClick={() => answerMutation.mutate(item.id)} disabled={!answers[item.id]?.trim()}>
                Ответить
              </button>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function CustomerView() {
  const progressQuery = useQuery({ queryKey: ['customer-progress'], queryFn: () => getProgressTable() });
  const rows = progressQuery.data?.rows ?? [];

  const exportReport = async () => {
    try {
      const result = await downloadCustomerFinalReport();
      saveBlobAsFile(result.blob, result.filename ?? `customer_final_${Date.now()}.xlsx`);
    } catch (error) {
      if (error instanceof ApiError) {
        window.alert(error.message);
      }
    }
  };

  return (
    <div className="role-grid">
      <CustomerAnalyticsSection />

      <section className="card card-wide">
        <h2>Прогресс сотрудников</h2>
        <button type="button" onClick={exportReport}>Выгрузить итоговый отчёт (Excel)</button>
        {rows.length === 0 ? <p className="muted">Нет данных для отображения.</p> : null}
        {rows.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Сотрудник</th>
                  <th>Прохождение (%)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.student_id}>
                    <td>{row.full_name}</td>
                    <td>{row.progress_percent}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function App() {
  const queryClient = useQueryClient();
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getAuthToken()));
  const [role, setRole] = useState<Role | null>(null);

  const meQuery = useQuery({
    queryKey: ['auth-me', isAuthenticated],
    queryFn: getMe,
    enabled: isAuthenticated,
    retry: false,
  });

  useEffect(() => {
    if (meQuery.isError) {
      logout();
      setIsAuthenticated(false);
      queryClient.clear();
    }
  }, [meQuery.isError, queryClient]);

  useEffect(() => {
    if (meQuery.data && (!role || !meQuery.data.roles.includes(role))) {
      setRole(meQuery.data.roles[0]);
    }
  }, [meQuery.data, role]);

  const notificationsQuery = useQuery({
    queryKey: ['header-notifications', isAuthenticated],
    queryFn: () => listNotifications(),
    enabled: isAuthenticated,
  });

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationsRead([notificationId]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['header-notifications', isAuthenticated] });
      queryClient.invalidateQueries({ queryKey: ['my-notifications'] });
    },
  });

  const handleLogout = () => {
    logout();
    setIsAuthenticated(false);
    setRole(null);
    queryClient.clear();
  };

  if (!isAuthenticated) {
    return <LoginView onLoggedIn={() => setIsAuthenticated(true)} />;
  }

  if (meQuery.isLoading || !meQuery.data) {
    return (
      <div className="auth-shell">
        <section className="card auth-card">
          <p>Загрузка профиля...</p>
        </section>
      </div>
    );
  }

  if (meQuery.data.require_password_change) {
    return <ForcePasswordChangeView onChanged={() => queryClient.invalidateQueries({ queryKey: ['auth-me'] })} />;
  }

  const availableRoles = meQuery.data.roles;
  const headerNotifications = notificationsQuery.data ?? [];
  const unreadCount = headerNotifications.filter((item) => !item.is_read).length;

  return (
    <div className="app-shell">
      <header className="hero">
        <h1>LMS Workspace</h1>
        <p>
          Пользователь: <strong>{meQuery.data.user.full_name}</strong> ({meQuery.data.user.email})
        </p>
        <p>Уведомления: <strong>{unreadCount}</strong> непрочитанных</p>
        <button type="button" className="logout-btn" onClick={handleLogout}>Выйти</button>
      </header>

      <nav className="role-tabs" aria-label="Роли">
        {availableRoles.map((item) => (
          <button key={item} type="button" className={item === role ? 'active' : ''} onClick={() => setRole(item)}>
            {roleLabels[item]}
          </button>
        ))}
      </nav>

      <section className="card card-wide">
        <h2>Центр уведомлений</h2>
        {headerNotifications.length === 0 ? <p className="muted">Уведомлений пока нет.</p> : null}
        {headerNotifications.slice(0, 8).map((item: NotificationOut) => (
          <article key={item.id} className="lesson-card">
            <p><strong>{item.subject}</strong></p>
            <p>{item.body}</p>
            <p className="muted">{channelLabel(item.channel)} • {formatDate(item.created_at)}</p>
            <button type="button" disabled={item.is_read || markReadMutation.isPending} onClick={() => markReadMutation.mutate(item.id)}>
              {item.is_read ? 'Прочитано' : 'Отметить как прочитанное'}
            </button>
          </article>
        ))}
      </section>

      {role === 'methodist' ? <MethodistView /> : null}
      {role === 'admin' ? <AdminView /> : null}
      {role === 'executive' ? <ExecutiveView /> : null}
      {role === 'student' ? <StudentView me={meQuery.data} /> : null}
      {role === 'teacher' ? <TeacherView /> : null}
      {role === 'curator' ? <CuratorView /> : null}
      {role === 'customer' ? <CustomerView /> : null}
    </div>
  );
}

export default App;
