from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Engine, inspect, text


def _existing_columns(engine: Engine, table_name: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info('{table_name}')")).all()
    return {row[1] for row in rows}


def _add_missing_columns(engine: Engine, table_name: str, columns: Iterable[tuple[str, str]]) -> None:
    current = _existing_columns(engine, table_name)
    with engine.begin() as conn:
        for name, ddl in columns:
            if name not in current:
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN {ddl}'))


def _add_missing_columns_postgres(engine: Engine, table_name: str, columns: Iterable[tuple[str, str]]) -> None:
    inspector = inspect(engine)
    current = {column['name'] for column in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for name, ddl in columns:
            if name not in current:
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS {ddl}'))


def _ensure_postgres_enum_values(engine: Engine) -> None:
    statements = [
        "ALTER TYPE notificationchannel ADD VALUE IF NOT EXISTS 'telegram'",
        "ALTER TYPE assignmentstatus ADD VALUE IF NOT EXISTS 'returned_for_revision'",
        "ALTER TYPE progressstatus ADD VALUE IF NOT EXISTS 'awaiting_review'",
        "ALTER TYPE lessontype ADD VALUE IF NOT EXISTS 'assignment'",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                # Enum type might not exist in legacy databases; ignore.
                pass


def _create_test_attempts_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS test_attempts (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    enrollment_id VARCHAR(36) NOT NULL,
                    lesson_id VARCHAR(36) NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    score FLOAT NOT NULL,
                    passed BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL,
                    actor_user_id VARCHAR(36),
                    FOREIGN KEY(enrollment_id) REFERENCES enrollments (id) ON DELETE CASCADE,
                    FOREIGN KEY(lesson_id) REFERENCES lessons (id) ON DELETE CASCADE,
                    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
                )
                """
            )
        )


def _create_notifications_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    recipient_user_id VARCHAR(36) NOT NULL,
                    channel VARCHAR(10) NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    body TEXT NOT NULL,
                    link_url VARCHAR(500),
                    is_read BOOLEAN NOT NULL DEFAULT 0,
                    event_key VARCHAR(255) UNIQUE,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(recipient_user_id) REFERENCES users (id) ON DELETE CASCADE
                )
                """
            )
        )


def _create_audit_events_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    actor_user_id VARCHAR(36),
                    event_type VARCHAR(100) NOT NULL,
                    entity_type VARCHAR(100) NOT NULL,
                    entity_id VARCHAR(100) NOT NULL,
                    from_status VARCHAR(100),
                    to_status VARCHAR(100),
                    payload_json JSON,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
                )
                """
            )
        )


def apply_sqlite_compat_migrations(engine: Engine) -> None:
    dialect = engine.dialect.name
    inspector = inspect(engine)

    if dialect == 'postgresql':
        _ensure_postgres_enum_values(engine)

    if inspector.has_table('programs'):
        columns = [
            ('strict_order', 'strict_order BOOLEAN NOT NULL DEFAULT TRUE'),
            (
                'certification_progress_threshold',
                'certification_progress_threshold FLOAT NOT NULL DEFAULT 100.0',
            ),
            (
                'certification_min_avg_score',
                'certification_min_avg_score FLOAT NOT NULL DEFAULT 60.0',
            ),
            ('is_paid', 'is_paid BOOLEAN NOT NULL DEFAULT FALSE'),
            ('price_amount', 'price_amount FLOAT'),
        ]
        if dialect == 'sqlite':
            columns = [
                ('strict_order', 'strict_order BOOLEAN NOT NULL DEFAULT 1'),
                (
                    'certification_progress_threshold',
                    'certification_progress_threshold FLOAT NOT NULL DEFAULT 100.0',
                ),
                (
                    'certification_min_avg_score',
                    'certification_min_avg_score FLOAT NOT NULL DEFAULT 60.0',
                ),
                ('is_paid', 'is_paid BOOLEAN NOT NULL DEFAULT 0'),
                ('price_amount', 'price_amount FLOAT'),
            ]
            _add_missing_columns(engine, 'programs', columns)
        elif dialect == 'postgresql':
            _add_missing_columns_postgres(engine, 'programs', columns)

    if inspector.has_table('groups'):
        columns = [
            ('start_date', 'start_date TIMESTAMPTZ'),
            ('end_date', 'end_date TIMESTAMPTZ'),
        ]
        if dialect == 'sqlite':
            _add_missing_columns(engine, 'groups', [('start_date', 'start_date DATETIME'), ('end_date', 'end_date DATETIME')])
        elif dialect == 'postgresql':
            _add_missing_columns_postgres(engine, 'groups', columns)

    if inspector.has_table('enrollments'):
        columns = [
            ('program_status', "program_status VARCHAR(20) NOT NULL DEFAULT 'not_started'"),
            ('certification_issued_at', 'certification_issued_at TIMESTAMPTZ'),
            ('certificate_url', 'certificate_url VARCHAR(500)'),
            ('certificate_number', 'certificate_number VARCHAR(100)'),
            ('payment_status', "payment_status VARCHAR(20) NOT NULL DEFAULT 'not_required'"),
            ('payment_link', 'payment_link VARCHAR(1000)'),
            ('payment_due_at', 'payment_due_at TIMESTAMPTZ'),
            ('payment_confirmed_at', 'payment_confirmed_at TIMESTAMPTZ'),
            ('payment_provider', 'payment_provider VARCHAR(100)'),
            ('payment_external_id', 'payment_external_id VARCHAR(255)'),
        ]
        if dialect == 'sqlite':
            _add_missing_columns(
                engine,
                'enrollments',
                [
                    ('program_status', "program_status VARCHAR(20) NOT NULL DEFAULT 'not_started'"),
                    ('certification_issued_at', 'certification_issued_at DATETIME'),
                    ('certificate_url', 'certificate_url VARCHAR(500)'),
                    ('certificate_number', 'certificate_number VARCHAR(100)'),
                    ('payment_status', "payment_status VARCHAR(20) NOT NULL DEFAULT 'not_required'"),
                    ('payment_link', 'payment_link VARCHAR(1000)'),
                    ('payment_due_at', 'payment_due_at DATETIME'),
                    ('payment_confirmed_at', 'payment_confirmed_at DATETIME'),
                    ('payment_provider', 'payment_provider VARCHAR(100)'),
                    ('payment_external_id', 'payment_external_id VARCHAR(255)'),
                ],
            )
        elif dialect == 'postgresql':
            _add_missing_columns_postgres(engine, 'enrollments', columns)

    if inspector.has_table('students'):
        if dialect == 'sqlite':
            _add_missing_columns(
                engine,
                'students',
                [
                    ('organization', 'organization VARCHAR(255)'),
                ],
            )
        elif dialect == 'postgresql':
            _add_missing_columns_postgres(
                engine,
                'students',
                [
                    ('organization', 'organization VARCHAR(255)'),
                ],
            )

    if inspector.has_table('users'):
        if dialect == 'sqlite':
            _add_missing_columns(
                engine,
                'users',
                [
                    ('telegram_chat_id', 'telegram_chat_id VARCHAR(64)'),
                    ('telegram_username', 'telegram_username VARCHAR(255)'),
                    ('telegram_link_token', 'telegram_link_token VARCHAR(64)'),
                    ('telegram_linked_at', 'telegram_linked_at DATETIME'),
                ],
            )
            with engine.begin() as conn:
                try:
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_link_token ON users(telegram_link_token)'))
                except Exception:
                    pass
        elif dialect == 'postgresql':
            _add_missing_columns_postgres(
                engine,
                'users',
                [
                    ('telegram_chat_id', 'telegram_chat_id VARCHAR(64)'),
                    ('telegram_username', 'telegram_username VARCHAR(255)'),
                    ('telegram_link_token', 'telegram_link_token VARCHAR(64)'),
                    ('telegram_linked_at', 'telegram_linked_at TIMESTAMPTZ'),
                ],
            )
            with engine.begin() as conn:
                conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_link_token ON users(telegram_link_token)'))

    if inspector.has_table('lesson_progress'):
        columns = [
            ('last_opened_at', 'last_opened_at TIMESTAMPTZ'),
            ('attempts_used', 'attempts_used INTEGER NOT NULL DEFAULT 0'),
            ('extra_attempts_allowed', 'extra_attempts_allowed INTEGER NOT NULL DEFAULT 0'),
        ]
        if dialect == 'sqlite':
            _add_missing_columns(
                engine,
                'lesson_progress',
                [
                    ('last_opened_at', 'last_opened_at DATETIME'),
                    ('attempts_used', 'attempts_used INTEGER NOT NULL DEFAULT 0'),
                    ('extra_attempts_allowed', 'extra_attempts_allowed INTEGER NOT NULL DEFAULT 0'),
                ],
            )
        elif dialect == 'postgresql':
            _add_missing_columns_postgres(engine, 'lesson_progress', columns)

    if inspector.has_table('assignment_submissions'):
        if dialect == 'sqlite':
            _add_missing_columns(
                engine,
                'assignment_submissions',
                [
                    ('student_viewed_at', 'student_viewed_at DATETIME'),
                    ('override_reason', 'override_reason TEXT'),
                    ('file_key', 'file_key VARCHAR(500)'),
                    ('file_name', 'file_name VARCHAR(255)'),
                    ('file_mime', 'file_mime VARCHAR(100)'),
                    ('file_size_bytes', 'file_size_bytes INTEGER'),
                ],
            )
        elif dialect == 'postgresql':
            _add_missing_columns_postgres(
                engine,
                'assignment_submissions',
                [
                    ('student_viewed_at', 'student_viewed_at TIMESTAMPTZ'),
                    ('override_reason', 'override_reason TEXT'),
                    ('file_key', 'file_key VARCHAR(500)'),
                    ('file_name', 'file_name VARCHAR(255)'),
                    ('file_mime', 'file_mime VARCHAR(100)'),
                    ('file_size_bytes', 'file_size_bytes INTEGER'),
                ],
            )

    if dialect == 'sqlite':
        _create_test_attempts_table(engine)
        _create_notifications_table(engine)
        _create_audit_events_table(engine)
