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
  getMe,
  getProgram,
  getProgressTable,
  getStudentLessons,
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
  AssignmentOut,
  LessonFilterType,
  MeResponse,
  NotificationOut,
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

const lessonTypeLabels: Record<LessonFilterType, string> = {
  all: 'Все типы',
  video: 'Видео',
  text: 'Текст',
  test: 'Тест',
  assignment: 'Задание',
};

const roleCatalog: Role[] = ['admin', 'methodist', 'teacher', 'curator', 'student', 'customer'];

function formatDate(value: string | null): string {
  if (!value) {
    return '—';
  }
  return new Date(value).toLocaleString('ru-RU');
}

function ProgramStatusBadge({ status }: { status: ProgramStatus }) {
  return <span className={`status-pill status-${status}`}>{programStatusLabels[status]}</span>;
}

function ProgressStatusBadge({ status }: { status: ProgressStatus }) {
  return <span className={`status-pill status-${status}`}>{progressStatusLabels[status]}</span>;
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
          Тестовые логины: `admin@lms.local / Admin123!`, `student1@lms.local / Temp123!`, `teacher@lms.local / Teach123!`
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
}: {
  rows: ProgressRow[];
  compact?: boolean;
  includeLastLogin?: boolean;
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

function MethodistView() {
  const queryClient = useQueryClient();
  const [selectedProgramId, setSelectedProgramId] = useState('');
  const [selectedModuleId, setSelectedModuleId] = useState('');

  const [programName, setProgramName] = useState('');
  const [programDescription, setProgramDescription] = useState('');
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
    mutationFn: () => createProgram({ name: programName, description: programDescription }),
    onSuccess: (program) => {
      queryClient.invalidateQueries({ queryKey: ['programs-base'] });
      queryClient.invalidateQueries({ queryKey: ['programs-catalog'] });
      setSelectedProgramId(program.id);
      setProgramName('');
      setProgramDescription('');
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
                  <th>Статус</th>
                  <th>Дата создания</th>
                </tr>
              </thead>
              <tbody>
                {catalogPrograms.map((program) => (
                  <tr key={program.id}>
                    <td>{program.name}</td>
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
    const { utils, writeFile } = await import('xlsx');

    const exportRows = tableRows.map((row) => ({
      'ФИО': row.full_name,
      'Программа': row.program_name,
      'Группа': row.group_name,
      'Прогресс %': row.progress_percent,
      'Дата зачисления': formatDate(row.enrolled_at),
    }));

    const sheet = utils.json_to_sheet(exportRows);
    const workbook = utils.book_new();
    utils.book_append_sheet(workbook, sheet, 'Прогресс');
    writeFile(workbook, `lms_progress_${Date.now()}.xlsx`);
  };

  return (
    <div className="role-grid">
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

        {progressQuery.data ? <StudentsProgressTable rows={tableRows} includeLastLogin /> : null}
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
            <p className="muted">Канал: {item.channel === 'email' ? 'Email' : 'В системе'} • {formatDate(item.created_at)}</p>
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

  return (
    <div className="role-grid">
      <section className="card card-wide">
        <h2>Прогресс сотрудников</h2>
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
            <p className="muted">{item.channel === 'email' ? 'Email' : 'В системе'} • {formatDate(item.created_at)}</p>
            <button type="button" disabled={item.is_read || markReadMutation.isPending} onClick={() => markReadMutation.mutate(item.id)}>
              {item.is_read ? 'Прочитано' : 'Отметить как прочитанное'}
            </button>
          </article>
        ))}
      </section>

      {role === 'methodist' ? <MethodistView /> : null}
      {role === 'admin' ? <AdminView /> : null}
      {role === 'student' ? <StudentView me={meQuery.data} /> : null}
      {role === 'teacher' ? <TeacherView /> : null}
      {role === 'curator' ? <CuratorView /> : null}
      {role === 'customer' ? <CustomerView /> : null}
    </div>
  );
}

export default App;
