def test_unauthorized_requests_are_blocked(client):
    response = client.get('/api/programs')
    assert response.status_code == 401


def test_student_first_login_requires_password_change(client):
    login = client.post('/api/auth/login', json={'email': 'student1@lms.local', 'password': 'Temp123!'})
    assert login.status_code == 200
    payload = login.json()
    assert payload['require_password_change'] is True

    token = payload['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    blocked_call = client.get('/api/groups', headers=headers)
    assert blocked_call.status_code == 403

    changed = client.post(
        '/api/auth/change-password',
        headers=headers,
        json={'old_password': 'Temp123!', 'new_password': 'Student123!'},
    )
    assert changed.status_code == 200

    relogin = client.post('/api/auth/login', json={'email': 'student1@lms.local', 'password': 'Student123!'})
    assert relogin.status_code == 200
    assert relogin.json()['require_password_change'] is False


def test_methodist_cannot_view_student_progress(client, methodist_headers):
    response = client.get('/api/progress', headers=methodist_headers)
    assert response.status_code == 403


def test_teacher_can_see_only_assigned_groups(client, teacher_headers, admin_headers):
    demo_groups = client.get('/api/groups', headers=teacher_headers)
    assert demo_groups.status_code == 200
    base_ids = {item['id'] for item in demo_groups.json()}
    assert len(base_ids) >= 1

    program = client.post('/api/programs', headers=admin_headers, json={'name': 'Extra Program', 'description': 'x'}).json()
    new_group = client.post('/api/groups', headers=admin_headers, json={'name': 'Hidden Group', 'program_id': program['id']}).json()

    groups_after = client.get('/api/groups', headers=teacher_headers)
    assert groups_after.status_code == 200
    after_ids = {item['id'] for item in groups_after.json()}
    assert new_group['id'] not in after_ids

    forbidden = client.get(f"/api/groups/{new_group['id']}/progress", headers=teacher_headers)
    assert forbidden.status_code == 403


def test_customer_sees_only_linked_students(client, customer_headers):
    response = client.get('/api/progress', headers=customer_headers)
    assert response.status_code == 200
    rows = response.json()['rows']
    assert len(rows) == 2
    assert {row['full_name'] for row in rows} == {'Слушатель Один', 'Слушатель Два'}


def test_admin_can_create_and_block_user(client, admin_headers):
    created = client.post(
        '/api/users',
        headers=admin_headers,
        json={
            'email': 'new.teacher@lms.local',
            'full_name': 'New Teacher',
            'password': 'StrongPass123!',
            'roles': ['teacher'],
            'temp_password_required': False,
        },
    )
    assert created.status_code == 201
    user_id = created.json()['id']

    blocked = client.post(
        f'/api/users/{user_id}/block',
        headers=admin_headers,
        json={'blocked': True},
    )
    assert blocked.status_code == 200
    assert blocked.json()['blocked'] is True


def test_new_user_gets_welcome_notification(client, admin_headers):
    created = client.post(
        '/api/users',
        headers=admin_headers,
        json={
            'email': 'notify.user@lms.local',
            'full_name': 'Notify User',
            'password': 'StrongPass123!',
            'roles': ['teacher'],
            'temp_password_required': False,
        },
    )
    assert created.status_code == 201

    login = client.post('/api/auth/login', json={'email': 'notify.user@lms.local', 'password': 'StrongPass123!'})
    assert login.status_code == 200
    token = login.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    notifications = client.get('/api/notifications', headers=headers)
    assert notifications.status_code == 200
    subjects = [item['subject'] for item in notifications.json()]
    assert 'Учетная запись создана' in subjects
