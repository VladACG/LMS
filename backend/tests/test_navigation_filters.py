import time


def _create_program_with_one_lesson(client, admin_headers, name: str):
    program = client.post('/api/programs', headers=admin_headers, json={'name': name, 'description': 'desc'}).json()
    module = client.post(
        f"/api/programs/{program['id']}/modules",
        headers=admin_headers,
        json={'title': 'M1', 'order_index': 1},
    ).json()
    lesson = client.post(
        f"/api/modules/{module['id']}/lessons",
        headers=admin_headers,
        json={
            'title': 'L1',
            'type': 'text',
            'order_index': 1,
            'text_body': 'body',
        },
    ).json()
    return program, lesson


def _create_group_and_student(client, admin_headers, program_id: str, group_name: str, full_name: str, email: str):
    group = client.post('/api/groups', headers=admin_headers, json={'name': group_name, 'program_id': program_id}).json()
    enrollment = client.post(
        f"/api/groups/{group['id']}/enrollments",
        headers=admin_headers,
        json={'students': [{'full_name': full_name, 'email': email}]},
    ).json()[0]
    return group, enrollment


def test_program_status_filters_and_sorting(client, admin_headers):
    draft_program = client.post('/api/programs', headers=admin_headers, json={'name': 'Draft Program', 'description': ''}).json()
    assert draft_program['status'] == 'draft'

    active_program, active_lesson = _create_program_with_one_lesson(client, admin_headers, 'Active Program')
    active_group, active_student = _create_group_and_student(
        client,
        admin_headers,
        active_program['id'],
        'Active Group',
        'Анна Активная',
        'active@example.com',
    )
    assert active_lesson['id']
    assert active_group['id']
    assert active_student['student_id']

    archived_program, archived_lesson = _create_program_with_one_lesson(client, admin_headers, 'Archived Program')
    archived_group, archived_student = _create_group_and_student(
        client,
        admin_headers,
        archived_program['id'],
        'Archived Group',
        'Аркадий Архивный',
        'archived@example.com',
    )

    complete = client.post(
        f"/api/students/{archived_student['student_id']}/lessons/{archived_lesson['id']}/complete",
        headers=admin_headers,
        params={'group_id': archived_group['id']},
    )
    assert complete.status_code == 200

    only_archived = client.get('/api/programs', headers=admin_headers, params={'status': 'archived'})
    assert only_archived.status_code == 200
    archived_names = {item['name'] for item in only_archived.json()}
    assert 'Archived Program' in archived_names
    assert 'Active Program' not in archived_names

    only_draft = client.get('/api/programs', headers=admin_headers, params={'status': 'draft'})
    assert only_draft.status_code == 200
    draft_names = {item['name'] for item in only_draft.json()}
    assert 'Draft Program' in draft_names

    searched = client.get('/api/programs', headers=admin_headers, params={'search': 'Active'})
    assert searched.status_code == 200
    assert any(item['name'] == 'Active Program' for item in searched.json())

    sorted_asc = client.get('/api/programs', headers=admin_headers, params={'sort': 'asc'})
    assert sorted_asc.status_code == 200
    dates = [item['created_at'] for item in sorted_asc.json()]
    assert dates == sorted(dates)


def test_global_progress_filters_search_and_sort(client, admin_headers):
    program_1, lesson_1 = _create_program_with_one_lesson(client, admin_headers, 'Progress Program 1')
    group_1, student_1 = _create_group_and_student(
        client,
        admin_headers,
        program_1['id'],
        'Group 1',
        'Иван Иванов',
        'ivan.progress@example.com',
    )
    assert lesson_1['id']
    assert student_1['student_id']

    time.sleep(0.05)

    program_2, lesson_2 = _create_program_with_one_lesson(client, admin_headers, 'Progress Program 2')
    group_2, student_2 = _create_group_and_student(
        client,
        admin_headers,
        program_2['id'],
        'Group 2',
        'Петр Петров',
        'petr.progress@example.com',
    )

    complete = client.post(
        f"/api/students/{student_2['student_id']}/lessons/{lesson_2['id']}/complete",
        headers=admin_headers,
        params={'group_id': group_2['id']},
    )
    assert complete.status_code == 200

    progress_all = client.get('/api/progress', headers=admin_headers)
    assert progress_all.status_code == 200
    rows = progress_all.json()['rows']
    assert len(rows) >= 2

    search_ivan = client.get('/api/progress', headers=admin_headers, params={'search': 'иван'})
    assert search_ivan.status_code == 200
    assert all('иван' in row['full_name'].lower() for row in search_ivan.json()['rows'])

    completed_only = client.get('/api/progress', headers=admin_headers, params={'progress_status': 'completed'})
    assert completed_only.status_code == 200
    assert all(row['progress_status'] == 'completed' for row in completed_only.json()['rows'])

    group_filtered = client.get('/api/progress', headers=admin_headers, params={'group_id': group_1['id']})
    assert group_filtered.status_code == 200
    assert all(row['group_id'] == group_1['id'] for row in group_filtered.json()['rows'])

    sorted_by_progress = client.get(
        '/api/progress',
        headers=admin_headers,
        params={'sort_by': 'progress_percent', 'sort_order': 'desc'},
    )
    assert sorted_by_progress.status_code == 200
    percents = [row['progress_percent'] for row in sorted_by_progress.json()['rows']]
    assert percents == sorted(percents, reverse=True)
