from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


connect_args = {'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}

engine_kwargs = {
    'future': True,
    'echo': False,
    'connect_args': connect_args,
}
if not settings.database_url.startswith('sqlite'):
    engine_kwargs.update({'pool_pre_ping': True, 'pool_size': 20, 'max_overflow': 40})

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
