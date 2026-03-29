from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.services.seed import seed_default_data


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / 'test.db'
    engine = create_engine(f'sqlite:///{db_file}', connect_args={'check_same_thread': False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as db:
        seed_default_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    token = response.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'admin@lms.local', 'Admin123!')


@pytest.fixture()
def methodist_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'methodist@lms.local', 'Method123!')


@pytest.fixture()
def executive_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'executive@lms.local', 'Exec123!')


@pytest.fixture()
def teacher_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'teacher@lms.local', 'Teach123!')


@pytest.fixture()
def curator_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'curator@lms.local', 'Curator123!')


@pytest.fixture()
def customer_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'customer@lms.local', 'Customer123!')


@pytest.fixture()
def student_headers(client: TestClient) -> dict[str, str]:
    temp_headers = auth_headers(client, 'student1@lms.local', 'Temp123!')
    change = client.post(
        '/api/auth/change-password',
        headers=temp_headers,
        json={'old_password': 'Temp123!', 'new_password': 'Student123!'},
    )
    assert change.status_code == 200
    return auth_headers(client, 'student1@lms.local', 'Student123!')
