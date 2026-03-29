from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'LMS API'
    app_version: str = '0.1.0'
    database_url: str = 'sqlite:///./lms.db'

    jwt_secret_key: str = 'change-me-in-production'
    jwt_algorithm: str = 'HS256'
    jwt_expire_minutes: int = 720

    app_base_url: str = 'http://localhost:8000'

    telegram_bot_token: str | None = None
    telegram_bot_username: str | None = None

    storage_backend: str = 'local'
    storage_local_path: str = './storage_data'
    s3_endpoint_url: str | None = None
    s3_region: str = 'ru-central1'
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket_name: str | None = None

    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    yookassa_return_url: str = 'http://localhost:80'


class HealthResponse(BaseModel):
    status: str


settings = Settings()
