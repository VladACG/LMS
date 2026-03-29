def test_program_module_lesson_tree(client, admin_headers):
    program = client.post('/api/programs', headers=admin_headers, json={'name': 'Python Basics', 'description': 'Intro'}).json()
    module = client.post(
        f"/api/programs/{program['id']}/modules",
        headers=admin_headers,
        json={'title': 'Module 1', 'order_index': 1},
    ).json()

    lesson_resp = client.post(
        f"/api/modules/{module['id']}/lessons",
        headers=admin_headers,
        json={
            'title': 'Video lesson',
            'type': 'video',
            'order_index': 1,
            'video_url': 'https://example.com/video',
        },
    )
    assert lesson_resp.status_code == 201

    detail = client.get(f"/api/programs/{program['id']}", headers=admin_headers)
    assert detail.status_code == 200
    data = detail.json()
    assert data['name'] == 'Python Basics'
    assert len(data['modules']) == 1
    assert len(data['modules'][0]['lessons']) == 1


def test_lesson_payload_validation(client, admin_headers):
    program = client.post('/api/programs', headers=admin_headers, json={'name': 'JS Basics', 'description': ''}).json()
    module = client.post(
        f"/api/programs/{program['id']}/modules",
        headers=admin_headers,
        json={'title': 'M1', 'order_index': 1},
    ).json()

    invalid = client.post(
        f"/api/modules/{module['id']}/lessons",
        headers=admin_headers,
        json={
            'title': 'Invalid video',
            'type': 'video',
            'order_index': 1,
        },
    )
    assert invalid.status_code == 422
