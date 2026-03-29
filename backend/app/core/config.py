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


class HealthResponse(BaseModel):
    status: str


settings = Settings()
