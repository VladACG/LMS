def _seed_program_group_student(client, admin_headers):
    program = client.post('/api/programs', headers=admin_headers, json={'name': 'Data Course', 'description': 'desc'}).json()
    module_1 = client.post(
        f"/api/programs/{program['id']}/modules",
        headers=admin_headers,
        json={'title': 'Part 1', 'order_index': 1},
    ).json()
    module_2 = client.post(
        f"/api/programs/{program['id']}/modules",
        headers=admin_headers,
        json={'title': 'Part 2', 'order_index': 2},
    ).json()

    lesson_1 = client.post(
        f"/api/modules/{module_1['id']}/lessons",
        headers=admin_headers,
        json={
            'title': 'Intro text',
            'type': 'text',
            'order_index': 1,
            'text_body': 'hello',
        },
    ).json()
    lesson_2 = client.post(
        f"/api/modules/{module_2['id']}/lessons",
        headers=admin_headers,
        json={
            'title': 'Final test',
            'type': 'test',
            'order_index': 1,
            'questions_json': {'q': '1+1?'},
        },
    ).json()

    group = client.post('/api/groups', headers=admin_headers, json={'name': 'Group A', 'program_id': program['id']}).json()
    enrollment_result = client.post(
        f"/api/groups/{group['id']}/enrollments",
        headers=admin_headers,
        json={'students': [{'full_name': 'Иван Иванов', 'email': 'ivan@example.com'}]},
    ).json()

    student = enrollment_result[0]
    return {
        'group_id': group['id'],
        'student_id': student['student_id'],
        'lesson_1': lesson_1['id'],
        'lesson_2': lesson_2['id'],
    }


def test_strict_order_and_progress(client, admin_headers):
    seeded = _seed_program_group_student(client, admin_headers)

    skip_attempt = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['lesson_2']}/complete",
        headers=admin_headers,
        params={'group_id': seeded['group_id']},
    )
    assert skip_attempt.status_code == 409

    complete_first = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['lesson_1']}/complete",
        headers=admin_headers,
        params={'group_id': seeded['group_id']},
    )
    assert complete_first.status_code == 200

    lessons = client.get(
        f"/api/students/{seeded['student_id']}/lessons",
        headers=admin_headers,
        params={'group_id': seeded['group_id']},
    )
    assert lessons.status_code == 200
    lessons_data = lessons.json()
    assert lessons_data['completed'] == 1
    assert lessons_data['total'] == 2

    progress = client.get(f"/api/groups/{seeded['group_id']}/progress", headers=admin_headers)
    assert progress.status_code == 200
    row = progress.json()['rows'][0]
    assert row['completed_lessons'] == 1
    assert row['total_lessons'] == 2
    assert row['progress_percent'] == 50.0
    assert row['progress_status'] == 'in_progress'
    assert row['enrolled_at'] is not None


def test_complete_idempotent(client, admin_headers):
    seeded = _seed_program_group_student(client, admin_headers)

    first = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['lesson_1']}/complete",
        headers=admin_headers,
        params={'group_id': seeded['group_id']},
    )
    second = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['lesson_1']}/complete",
        headers=admin_headers,
        params={'group_id': seeded['group_id']},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['status'] == 'completed'
    assert second.json()['status'] == 'completed'
