def _create_program_group_and_enrollment(
    client,
    admin_headers,
    *,
    program_name: str,
    lesson_type: str = 'text',
    paid: bool = False,
):
    program_payload = {
        'name': program_name,
        'description': 'integration flow',
        'is_paid': paid,
        'price_amount': 1990 if paid else None,
    }
    program = client.post('/api/programs', headers=admin_headers, json=program_payload)
    assert program.status_code == 201
    program_id = program.json()['id']

    module = client.post(
        f'/api/programs/{program_id}/modules',
        headers=admin_headers,
        json={'title': 'Module 1', 'order_index': 1},
    )
    assert module.status_code == 201
    module_id = module.json()['id']

    if lesson_type == 'video':
        lesson_payload = {
            'title': 'Webinar lesson',
            'type': 'video',
            'order_index': 1,
            'video_url': 'https://example.com/video',
            'webinar_start_at': '2026-05-01T10:00:00Z',
            'webinar_join_url': 'https://webinar.example.com/room-1',
        }
    elif lesson_type == 'assignment':
        lesson_payload = {
            'title': 'Practice',
            'type': 'assignment',
            'order_index': 1,
            'assignment_pass_score': 60,
        }
    else:
        lesson_payload = {
            'title': 'Text lesson',
            'type': 'text',
            'order_index': 1,
            'text_body': 'hello',
        }
    lesson = client.post(
        f'/api/modules/{module_id}/lessons',
        headers=admin_headers,
        json=lesson_payload,
    )
    assert lesson.status_code == 201
    lesson_id = lesson.json()['id']

    group = client.post(
        '/api/groups',
        headers=admin_headers,
        json={'name': f'{program_name} Group', 'program_id': program_id},
    )
    assert group.status_code == 201
    group_id = group.json()['id']

    enrollment = client.post(
        f'/api/groups/{group_id}/enrollments',
        headers=admin_headers,
        json={'students': [{'full_name': 'Слушатель Один', 'email': 'student1@lms.local'}]},
    )
    assert enrollment.status_code == 201
    row = enrollment.json()[0]

    return {
        'program_id': program_id,
        'group_id': group_id,
        'lesson_id': lesson_id,
        'student_id': row['student_id'],
        'enrollment_id': row['enrollment_id'],
    }


def test_paid_course_requires_payment_and_unlocks_after_webhook(client, admin_headers, student_headers):
    seeded = _create_program_group_and_enrollment(
        client,
        admin_headers,
        program_name='Paid Program',
        lesson_type='text',
        paid=True,
    )

    blocked_lessons = client.get(
        f"/api/students/{seeded['student_id']}/lessons",
        headers=student_headers,
        params={'group_id': seeded['group_id']},
    )
    assert blocked_lessons.status_code == 402

    payment_status_before = client.get(f"/api/payments/{seeded['enrollment_id']}", headers=student_headers)
    assert payment_status_before.status_code == 200
    assert payment_status_before.json()['payment_status'] == 'pending'

    webhook = client.post(
        '/api/payments/webhook',
        json={'enrollment_id': seeded['enrollment_id'], 'status': 'paid', 'external_id': 'ext-1'},
    )
    assert webhook.status_code == 200

    lessons = client.get(
        f"/api/students/{seeded['student_id']}/lessons",
        headers=student_headers,
        params={'group_id': seeded['group_id']},
    )
    assert lessons.status_code == 200

    payment_status_after = client.get(f"/api/payments/{seeded['enrollment_id']}", headers=student_headers)
    assert payment_status_after.status_code == 200
    assert payment_status_after.json()['payment_status'] == 'paid'


def test_telegram_link_flow(client, student_headers):
    link_resp = client.get('/api/telegram/link', headers=student_headers)
    assert link_resp.status_code == 200
    invite_url = link_resp.json()['invite_url']
    assert 'start=' in invite_url
    token = invite_url.split('start=', 1)[1]

    confirm = client.post(
        '/api/telegram/confirm',
        json={'token': token, 'chat_id': '123456', 'username': 'student_one'},
    )
    assert confirm.status_code == 200

    linked = client.get('/api/telegram/link', headers=student_headers)
    assert linked.status_code == 200
    assert linked.json()['linked'] is True
    assert linked.json()['telegram_username'] == 'student_one'


def test_calendar_links_and_ics(client, admin_headers, student_headers):
    seeded = _create_program_group_and_enrollment(
        client,
        admin_headers,
        program_name='Calendar Program',
        lesson_type='video',
        paid=False,
    )

    links = client.get(
        f"/api/students/{seeded['student_id']}/calendar-links",
        headers=student_headers,
        params={'group_id': seeded['group_id']},
    )
    assert links.status_code == 200
    payload = links.json()
    assert 'calendar.google.com' in payload['google_url']
    assert 'calendar.yandex.ru' in payload['yandex_url']
    assert payload['ics_url'].endswith(f"/api/students/{seeded['student_id']}/calendar.ics?group_id={seeded['group_id']}")

    ics = client.get(
        f"/api/students/{seeded['student_id']}/calendar.ics",
        headers=student_headers,
        params={'group_id': seeded['group_id']},
    )
    assert ics.status_code == 200
    assert 'text/calendar' in ics.headers.get('content-type', '')
    assert 'BEGIN:VCALENDAR' in ics.text
    assert 'webinar.example.com' in ics.text


def test_lesson_material_storage_and_download(client, admin_headers, student_headers):
    seeded = _create_program_group_and_enrollment(
        client,
        admin_headers,
        program_name='Materials Program',
        lesson_type='text',
        paid=False,
    )

    upload = client.post(
        f"/api/lessons/{seeded['lesson_id']}/materials/upload",
        headers=admin_headers,
        files={'file': ('guide.pdf', b'%PDF-1.4 test content', 'application/pdf')},
    )
    assert upload.status_code == 201
    material = upload.json()

    listed_admin = client.get(f"/api/lessons/{seeded['lesson_id']}/materials", headers=admin_headers)
    assert listed_admin.status_code == 200
    assert any(item['id'] == material['id'] for item in listed_admin.json())

    listed_student = client.get(
        f"/api/lessons/{seeded['lesson_id']}/materials",
        headers=student_headers,
        params={'group_id': seeded['group_id']},
    )
    assert listed_student.status_code == 200
    assert len(listed_student.json()) >= 1

    download_url = listed_student.json()[0]['download_url']
    download = client.get(download_url, headers=student_headers)
    assert download.status_code == 200
    assert download.content.startswith(b'%PDF')


def test_reports_and_integration_error_log(client, admin_headers, customer_headers, methodist_headers, student_headers):
    seeded = _create_program_group_and_enrollment(
        client,
        admin_headers,
        program_name='Reports Program',
        lesson_type='text',
        paid=True,
    )

    link_resp = client.get('/api/telegram/link', headers=student_headers)
    assert link_resp.status_code == 200
    token = link_resp.json()['invite_url'].split('start=', 1)[1]
    confirm = client.post('/api/telegram/confirm', json={'token': token, 'chat_id': '555', 'username': 's1'})
    assert confirm.status_code == 200

    webhook = client.post(
        '/api/payments/webhook',
        json={'enrollment_id': seeded['enrollment_id'], 'status': 'paid', 'external_id': 'payment-555'},
    )
    assert webhook.status_code == 200

    errors = client.get('/api/integrations/errors', headers=admin_headers)
    assert errors.status_code == 200
    assert any(item['service'] == 'telegram' for item in errors.json())

    group_report = client.get(f"/api/reports/groups/{seeded['group_id']}/final.xlsx", headers=admin_headers)
    assert group_report.status_code == 200
    assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in group_report.headers.get(
        'content-type',
        '',
    )

    customer_report = client.get('/api/reports/customers/me/final.xlsx', headers=customer_headers)
    assert customer_report.status_code == 200
    assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in customer_report.headers.get(
        'content-type',
        '',
    )

    methodist_stats = client.get(f"/api/reports/programs/{seeded['program_id']}/stats", headers=methodist_headers)
    assert methodist_stats.status_code == 200
    stats_payload = methodist_stats.json()
    assert stats_payload['program_id'] == seeded['program_id']
    assert 'problem_lessons' in stats_payload

