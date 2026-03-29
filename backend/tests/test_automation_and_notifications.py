def _teacher_user_id(client, admin_headers) -> str:
    users = client.get('/api/users', headers=admin_headers)
    assert users.status_code == 200
    for user in users.json():
        if user['email'] == 'teacher@lms.local':
            return user['id']
    raise AssertionError('teacher user not found')


def _create_program_flow(client, admin_headers):
    program = client.post(
        '/api/programs',
        headers=admin_headers,
        json={
            'name': 'Automation Program',
            'description': 'statuses and notifications',
            'strict_order': True,
            'certification_progress_threshold': 100,
            'certification_min_avg_score': 60,
        },
    )
    assert program.status_code == 201
    program_id = program.json()['id']

    module = client.post(
        f'/api/programs/{program_id}/modules',
        headers=admin_headers,
        json={'title': 'Main module', 'order_index': 1},
    )
    assert module.status_code == 201
    module_id = module.json()['id']

    video = client.post(
        f'/api/modules/{module_id}/lessons',
        headers=admin_headers,
        json={
            'title': 'Video lesson',
            'type': 'video',
            'order_index': 1,
            'video_url': 'https://example.com/video-1',
        },
    )
    assert video.status_code == 201

    test = client.post(
        f'/api/modules/{module_id}/lessons',
        headers=admin_headers,
        json={
            'title': 'Control test',
            'type': 'test',
            'order_index': 2,
            'questions_json': {'q1': '2+2'},
            'test_pass_score': 70,
            'test_max_attempts': 2,
        },
    )
    assert test.status_code == 201

    assignment = client.post(
        f'/api/modules/{module_id}/lessons',
        headers=admin_headers,
        json={
            'title': 'Practice task',
            'type': 'assignment',
            'order_index': 3,
            'assignment_pass_score': 80,
        },
    )
    assert assignment.status_code == 201

    group = client.post(
        '/api/groups',
        headers=admin_headers,
        json={'name': 'Automation Group', 'program_id': program_id},
    )
    assert group.status_code == 201
    group_id = group.json()['id']

    enrolled = client.post(
        f'/api/groups/{group_id}/enrollments',
        headers=admin_headers,
        json={'students': [{'full_name': 'Слушатель Один', 'email': 'student1@lms.local'}]},
    )
    assert enrolled.status_code == 201
    enrolled_row = enrolled.json()[0]

    teacher_id = _teacher_user_id(client, admin_headers)
    assign_teacher = client.post(
        f'/api/groups/{group_id}/teachers',
        headers=admin_headers,
        json={'user_ids': [teacher_id]},
    )
    assert assign_teacher.status_code == 200

    return {
        'group_id': group_id,
        'student_id': enrolled_row['student_id'],
        'enrollment_id': enrolled_row['enrollment_id'],
        'video_id': video.json()['id'],
        'test_id': test.json()['id'],
        'assignment_id': assignment.json()['id'],
    }


def test_status_automation_and_certificate_flow(client, admin_headers, student_headers, teacher_headers):
    seeded = _create_program_flow(client, admin_headers)

    denied_certificate = client.get(
        f"/api/certificates/{seeded['enrollment_id']}/download",
        headers=student_headers,
    )
    assert denied_certificate.status_code == 409

    blocked_skip = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['test_id']}/test-attempt",
        headers=student_headers,
        json={'group_id': seeded['group_id'], 'score': 65},
    )
    assert blocked_skip.status_code == 409

    open_video = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['video_id']}/engagement",
        headers=student_headers,
        json={'group_id': seeded['group_id'], 'opened': True},
    )
    assert open_video.status_code == 200
    assert open_video.json()['status'] == 'in_progress'

    lessons_after_open = client.get(
        f"/api/students/{seeded['student_id']}/lessons",
        headers=student_headers,
        params={'group_id': seeded['group_id']},
    )
    assert lessons_after_open.status_code == 200
    assert lessons_after_open.json()['program_status'] == 'in_progress'

    complete_video = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['video_id']}/engagement",
        headers=student_headers,
        json={'group_id': seeded['group_id'], 'watched_to_end': True},
    )
    assert complete_video.status_code == 200
    assert complete_video.json()['status'] == 'completed'

    test_fail_1 = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['test_id']}/test-attempt",
        headers=student_headers,
        json={'group_id': seeded['group_id'], 'score': 60},
    )
    assert test_fail_1.status_code == 200
    assert test_fail_1.json()['passed'] is False
    assert test_fail_1.json()['attempt_no'] == 1

    test_fail_2 = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['test_id']}/test-attempt",
        headers=student_headers,
        json={'group_id': seeded['group_id'], 'score': 69},
    )
    assert test_fail_2.status_code == 200
    assert test_fail_2.json()['passed'] is False
    assert test_fail_2.json()['attempt_no'] == 2

    test_limit = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['test_id']}/test-attempt",
        headers=student_headers,
        json={'group_id': seeded['group_id'], 'score': 90},
    )
    assert test_limit.status_code == 409

    override = client.post(
        '/api/admin/test-attempts/override',
        headers=admin_headers,
        json={
            'enrollment_id': seeded['enrollment_id'],
            'lesson_id': seeded['test_id'],
            'extra_attempts': 1,
            'reason': 'manual unlock for retake',
        },
    )
    assert override.status_code == 200

    test_pass = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['test_id']}/test-attempt",
        headers=student_headers,
        json={'group_id': seeded['group_id'], 'score': 90},
    )
    assert test_pass.status_code == 200
    assert test_pass.json()['passed'] is True
    assert test_pass.json()['status'] == 'completed'

    submit_assignment = client.post(
        '/api/assignments',
        headers=student_headers,
        json={
            'group_id': seeded['group_id'],
            'lesson_id': seeded['assignment_id'],
            'submission_text': 'first submission',
        },
    )
    assert submit_assignment.status_code == 201
    assignment_id = submit_assignment.json()['id']
    assert submit_assignment.json()['status'] == 'submitted'

    submit_again = client.post(
        '/api/assignments',
        headers=student_headers,
        json={
            'group_id': seeded['group_id'],
            'lesson_id': seeded['assignment_id'],
            'submission_text': 'duplicate submission',
        },
    )
    assert submit_again.status_code == 409

    review_return = client.post(
        f'/api/assignments/{assignment_id}/review',
        headers=teacher_headers,
        json={
            'grade': 50,
            'teacher_comment': 'Нужно доработать расчеты',
        },
    )
    assert review_return.status_code == 200
    assert review_return.json()['status'] == 'returned_for_revision'

    lessons_after_return = client.get(
        f"/api/students/{seeded['student_id']}/lessons",
        headers=student_headers,
        params={'group_id': seeded['group_id']},
    )
    assert lessons_after_return.status_code == 200
    assignment_rows = [item for item in lessons_after_return.json()['lessons'] if item['lesson_id'] == seeded['assignment_id']]
    assert len(assignment_rows) == 1
    assert assignment_rows[0]['status'] == 'in_progress'

    visible_assignments = client.get('/api/assignments/my', headers=student_headers)
    assert visible_assignments.status_code == 200
    viewed = [item for item in visible_assignments.json() if item['id'] == assignment_id]
    assert len(viewed) == 1
    assert viewed[0]['student_viewed_at'] is not None

    teacher_locked = client.post(
        f'/api/assignments/{assignment_id}/review',
        headers=teacher_headers,
        json={'grade': 95, 'teacher_comment': 'second edit'},
    )
    assert teacher_locked.status_code == 409

    admin_override = client.post(
        f'/api/assignments/{assignment_id}/review',
        headers=admin_headers,
        json={
            'grade': 90,
            'teacher_comment': 'approved by admin',
            'override_reason': 'student already viewed, administrative correction',
        },
    )
    assert admin_override.status_code == 200
    assert admin_override.json()['status'] == 'reviewed'

    my_certificates = client.get('/api/certificates/my', headers=student_headers)
    assert my_certificates.status_code == 200
    cert_rows = [item for item in my_certificates.json() if item['enrollment_id'] == seeded['enrollment_id']]
    assert len(cert_rows) == 1

    certificate_download = client.get(
        f"/api/certificates/{seeded['enrollment_id']}/download",
        headers=student_headers,
    )
    assert certificate_download.status_code == 200

    test_attempt_audit = client.get(
        '/api/audit/events',
        headers=admin_headers,
        params={'event_type': 'test_attempt'},
    )
    assert test_attempt_audit.status_code == 200
    assert len(test_attempt_audit.json()) >= 3


def test_notifications_endpoints_and_manual_automation(client, admin_headers, teacher_headers, student_headers):
    seeded = _create_program_flow(client, admin_headers)

    complete_video = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['video_id']}/complete",
        headers=admin_headers,
        params={'group_id': seeded['group_id']},
    )
    assert complete_video.status_code == 200

    complete_test = client.post(
        f"/api/students/{seeded['student_id']}/lessons/{seeded['test_id']}/test-attempt",
        headers=admin_headers,
        json={'group_id': seeded['group_id'], 'score': 95},
    )
    assert complete_test.status_code == 200
    assert complete_test.json()['passed'] is True

    submit_assignment = client.post(
        '/api/assignments',
        headers=student_headers,
        json={
            'group_id': seeded['group_id'],
            'lesson_id': seeded['assignment_id'],
            'submission_text': 'submission to create teacher notification',
        },
    )
    assert submit_assignment.status_code == 201

    create_student = client.post(
        '/api/users',
        headers=admin_headers,
        json={
            'email': 'inactive.student@lms.local',
            'full_name': 'Inactive Student',
            'password': 'TempPass123!',
            'roles': ['student'],
            'temp_password_required': True,
        },
    )
    assert create_student.status_code == 201

    enroll_inactive = client.post(
        f"/api/groups/{seeded['group_id']}/enrollments",
        headers=admin_headers,
        json={'students': [{'full_name': 'Inactive Student', 'email': 'inactive.student@lms.local'}]},
    )
    assert enroll_inactive.status_code == 201

    run_automation = client.post('/api/automation/run', headers=admin_headers)
    assert run_automation.status_code == 200
    assert run_automation.json()['generated_notifications'] >= 1
    assert run_automation.json()['generated_events'] == 1

    teacher_notifications = client.get('/api/notifications', headers=teacher_headers)
    assert teacher_notifications.status_code == 200
    assert any(item['subject'] == 'Новое задание на проверку' for item in teacher_notifications.json())

    if teacher_notifications.json():
        first_id = teacher_notifications.json()[0]['id']
        mark_read = client.post(
            '/api/notifications/mark-read',
            headers=teacher_headers,
            json={'notification_ids': [first_id]},
        )
        assert mark_read.status_code == 200

    unread = client.get('/api/notifications', headers=teacher_headers, params={'unread_only': True})
    assert unread.status_code == 200

    automation_audit = client.get(
        '/api/audit/events',
        headers=admin_headers,
        params={'event_type': 'automation_notifications_run'},
    )
    assert automation_audit.status_code == 200
    assert len(automation_audit.json()) >= 1
