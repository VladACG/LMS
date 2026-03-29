from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import HealthResponse, settings
from app.db.base import Base
from app.db.migrations import apply_sqlite_compat_migrations
from app.db.session import SessionLocal, engine
from app.models import *  # noqa: F401,F403
from app.services.seed import seed_default_data


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    apply_sqlite_compat_migrations(engine)
    with SessionLocal() as db:
        seed_default_data(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.get('/health', response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status='ok')

    app.include_router(router)
    return app


app = create_app()
