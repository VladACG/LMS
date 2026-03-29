from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.entities import (
    CuratorGroupLink,
    CustomerStudentLink,
    Enrollment,
    Group,
    Lesson,
    Module,
    Program,
    Student,
    TeacherGroupLink,
    User,
    UserRoleLink,
    UserStudentLink,
)
from app.models.enums import LessonType, UserRole


def _ensure_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    roles: list[UserRole],
    temp_password_required: bool = False,
) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            temp_password_required=temp_password_required,
        )
        db.add(user)
        db.flush()
    else:
        user.full_name = full_name
        if temp_password_required and not user.temp_password_required:
            user.temp_password_required = True

    current_roles = {item.role for item in user.roles}
    for role in roles:
        if role not in current_roles:
            db.add(UserRoleLink(user_id=user.id, role=role))

    db.flush()
    return user


def _ensure_demo_program(db: Session) -> Program:
    program = db.execute(select(Program).order_by(Program.created_at.asc())).scalars().first()
    if program:
        return program

    program = Program(name='Demo LMS Program', description='Seed program for role-based flows')
    db.add(program)
    db.flush()

    module = Module(program_id=program.id, title='Вводный модуль', order_index=1)
    db.add(module)
    db.flush()

    lessons = [
        Lesson(
            module_id=module.id,
            title='Видеоурок: знакомство',
            type=LessonType.video,
            order_index=1,
            content_json={'video_url': 'https://example.com/intro-video'},
        ),
        Lesson(
            module_id=module.id,
            title='Текстовый урок: правила',
            type=LessonType.text,
            order_index=2,
            content_json={'text_body': 'Добро пожаловать в LMS'},
        ),
        Lesson(
            module_id=module.id,
            title='Тестовый урок: проверка',
            type=LessonType.test,
            order_index=3,
            content_json={'questions': {'q1': 'Что такое LMS?'}},
        ),
    ]
    db.add_all(lessons)
    db.flush()
    return program


def _ensure_group(db: Session, program: Program) -> Group:
    group = db.execute(select(Group).where(Group.program_id == program.id).order_by(Group.name.asc())).scalars().first()
    if group:
        return group

    group = Group(name='Demo Group A', program_id=program.id)
    db.add(group)
    db.flush()
    return group


def _ensure_student_and_link(db: Session, *, full_name: str, email: str, user: User, group: Group) -> Student:
    student = db.execute(select(Student).where(Student.email == email)).scalar_one_or_none()
    if student is None:
        student = Student(full_name=full_name, email=email, organization='Demo Org')
        db.add(student)
        db.flush()

    link = db.execute(select(UserStudentLink).where(UserStudentLink.user_id == user.id)).scalar_one_or_none()
    if link is None:
        db.add(UserStudentLink(user_id=user.id, student_id=student.id))

    enrollment = db.execute(
        select(Enrollment).where(Enrollment.group_id == group.id, Enrollment.student_id == student.id)
    ).scalar_one_or_none()
    if enrollment is None:
        db.add(Enrollment(group_id=group.id, student_id=student.id))

    db.flush()
    return student


def seed_default_data(db: Session) -> None:
    program = _ensure_demo_program(db)
    group = _ensure_group(db, program)

    admin_user = _ensure_user(
        db,
        email='admin@lms.local',
        full_name='System Admin',
        password='Admin123!',
        roles=[UserRole.admin],
    )
    _ensure_user(
        db,
        email='methodist@lms.local',
        full_name='Lead Methodist',
        password='Method123!',
        roles=[UserRole.methodist],
    )
    _ensure_user(
        db,
        email='executive@lms.local',
        full_name='Org Executive',
        password='Exec123!',
        roles=[UserRole.executive],
    )
    teacher_user = _ensure_user(
        db,
        email='teacher@lms.local',
        full_name='Main Teacher',
        password='Teach123!',
        roles=[UserRole.teacher],
    )
    curator_user = _ensure_user(
        db,
        email='curator@lms.local',
        full_name='Main Curator',
        password='Curator123!',
        roles=[UserRole.curator],
    )
    customer_user = _ensure_user(
        db,
        email='customer@lms.local',
        full_name='Customer Manager',
        password='Customer123!',
        roles=[UserRole.customer],
    )

    # Demonstrates a single user owning multiple roles simultaneously.
    _ensure_user(
        db,
        email='multirole@lms.local',
        full_name='Multi Role User',
        password='Multi123!',
        roles=[UserRole.teacher, UserRole.curator],
    )

    student_user_1 = _ensure_user(
        db,
        email='student1@lms.local',
        full_name='Student One',
        password='Temp123!',
        roles=[UserRole.student],
        temp_password_required=True,
    )
    student_user_2 = _ensure_user(
        db,
        email='student2@lms.local',
        full_name='Student Two',
        password='Temp123!',
        roles=[UserRole.student],
        temp_password_required=True,
    )

    student_1 = _ensure_student_and_link(
        db,
        full_name='Слушатель Один',
        email='student1@lms.local',
        user=student_user_1,
        group=group,
    )
    student_2 = _ensure_student_and_link(
        db,
        full_name='Слушатель Два',
        email='student2@lms.local',
        user=student_user_2,
        group=group,
    )

    teacher_link = db.execute(
        select(TeacherGroupLink).where(TeacherGroupLink.user_id == teacher_user.id, TeacherGroupLink.group_id == group.id)
    ).scalar_one_or_none()
    if teacher_link is None:
        db.add(TeacherGroupLink(user_id=teacher_user.id, group_id=group.id))

    curator_link = db.execute(
        select(CuratorGroupLink).where(CuratorGroupLink.user_id == curator_user.id, CuratorGroupLink.group_id == group.id)
    ).scalar_one_or_none()
    if curator_link is None:
        db.add(CuratorGroupLink(user_id=curator_user.id, group_id=group.id))

    for student in [student_1, student_2]:
        customer_link = db.execute(
            select(CustomerStudentLink).where(
                CustomerStudentLink.customer_user_id == customer_user.id,
                CustomerStudentLink.student_id == student.id,
            )
        ).scalar_one_or_none()
        if customer_link is None:
            db.add(CustomerStudentLink(customer_user_id=customer_user.id, student_id=student.id))

    # Admin can also operate as methodist.
    admin_methodist_role = db.execute(
        select(UserRoleLink).where(UserRoleLink.user_id == admin_user.id, UserRoleLink.role == UserRole.methodist)
    ).scalar_one_or_none()
    if admin_methodist_role is None:
        db.add(UserRoleLink(user_id=admin_user.id, role=UserRole.methodist))

    db.commit()
