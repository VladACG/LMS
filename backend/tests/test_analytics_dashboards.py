def test_executive_dashboard_returns_aggregate_only(client, executive_headers):
    response = client.get('/api/analytics/executive', headers=executive_headers)
    assert response.status_code == 200

    payload = response.json()
    assert 'summary' in payload
    assert 'program_completion' in payload
    assert 'top_programs_by_students' in payload
    assert 'top_programs_by_score' in payload
    assert 'inactive_students' not in payload


def test_admin_cannot_open_executive_dashboard(client, admin_headers):
    response = client.get('/api/analytics/executive', headers=admin_headers)
    assert response.status_code == 403


def test_admin_dashboard_contains_detail_blocks(client, admin_headers):
    response = client.get('/api/analytics/admin', headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert 'executive' in payload
    assert 'groups' in payload
    assert 'inactive_students' in payload
    assert 'delayed_reviews' in payload
    assert 'integration_errors' in payload


def test_customer_dashboard_scoped_to_linked_students(client, customer_headers):
    response = client.get('/api/analytics/customer', headers=customer_headers)
    assert response.status_code == 200

    payload = response.json()
    names = {item['full_name'] for item in payload['employees']}
    assert names == {'Слушатель Один', 'Слушатель Два'}
