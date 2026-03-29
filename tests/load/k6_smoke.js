import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 20,
  duration: '1m',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<900'],
  },
};

export function setup() {
  const base = __ENV.BASE_URL || 'http://localhost:8000';
  const login = http.post(
    `${base}/api/auth/login`,
    JSON.stringify({ email: 'admin@lms.local', password: 'Admin123!' }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  check(login, {
    'login status 200': (r) => r.status === 200,
    'login has token': (r) => Boolean(r.json('access_token')),
  });

  return { base, token: login.json('access_token') };
}

export default function (data) {
  const headers = { Authorization: `Bearer ${data.token}` };

  const health = http.get(`${data.base}/health`);
  check(health, {
    'health status 200': (r) => r.status === 200,
  });

  const programs = http.get(`${data.base}/api/programs`, { headers });
  check(programs, {
    'programs status 200': (r) => r.status === 200,
  });

  const groups = http.get(`${data.base}/api/groups`, { headers });
  check(groups, {
    'groups status 200': (r) => r.status === 200,
  });

  const progress = http.get(`${data.base}/api/progress`, { headers });
  check(progress, {
    'progress status 200': (r) => r.status === 200,
  });

  sleep(1);
}
