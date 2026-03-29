import asyncio
import os
import statistics
import time
from pathlib import Path

load_db = Path('.tmp_load.db').resolve()
os.environ['DATABASE_URL'] = f"sqlite:///{load_db.as_posix()}"

import httpx

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.services.seed import seed_default_data


async def admin_token(client: httpx.AsyncClient) -> str:
    response = await client.post('/api/auth/login', json={'email': 'admin@lms.local', 'password': 'Admin123!'})
    response.raise_for_status()
    return response.json()['access_token']


async def run_load(total_requests: int = 60, concurrency: int = 6) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_default_data(db)

    transport = httpx.ASGITransport(app=app)
    latencies: list[float] = []
    errors = 0

    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        token = await admin_token(client)
        auth_headers = {'Authorization': f'Bearer {token}'}

        endpoints = [
            ('GET', '/health', None),
            ('GET', '/api/programs', auth_headers),
            ('GET', '/api/groups', auth_headers),
            ('GET', '/api/progress', auth_headers),
        ]

        lock = asyncio.Lock()
        sent = 0

        async def worker() -> None:
            nonlocal sent, errors
            local_idx = 0
            while True:
                async with lock:
                    if sent >= total_requests:
                        return
                    sent += 1
                    request_no = sent
                method, url, headers = endpoints[local_idx % len(endpoints)]
                local_idx += 1

                start = time.perf_counter()
                response = await client.request(method, url, headers=headers)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

                if response.status_code >= 400:
                    errors += 1

                if request_no % 40 == 0:
                    await asyncio.sleep(0)

        await asyncio.gather(*(worker() for _ in range(concurrency)))

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    avg = statistics.mean(latencies)
    error_rate = (errors / total_requests) * 100

    print(f'total_requests={total_requests}')
    print(f'errors={errors}')
    print(f'error_rate_percent={error_rate:.2f}')
    print(f'latency_avg_ms={avg:.2f}')
    print(f'latency_p95_ms={p95:.2f}')
    print(f'latency_p99_ms={p99:.2f}')

    assert error_rate < 1.0, 'error_rate SLA failed'
    assert p95 < 500.0, 'p95 SLA failed'
    assert p99 < 900.0, 'p99 SLA failed'

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if load_db.exists():
        try:
            load_db.unlink()
        except PermissionError:
            pass


if __name__ == '__main__':
    asyncio.run(run_load())
