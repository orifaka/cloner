from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    builder_bot_token: str = Field(alias="BUILDER_BOT_TOKEN")
    builder_bot_username: str = Field(default="", alias="BUILDER_BOT_USERNAME")

    public_base_url: str = Field(default="http://127.0.0.1:8080", alias="PUBLIC_BASE_URL")
    api_public_url: str = Field(default="http://127.0.0.1:8080", alias="API_PUBLIC_URL")

    platform_database_url: str = Field(
        default=f"sqlite+aiosqlite:///{(ROOT_DIR / 'data' / 'platform.db').as_posix()}",
        alias="PLATFORM_DATABASE_URL",
    )

    postgres_host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_admin_user: str = Field(default="mafia", alias="POSTGRES_ADMIN_USER")
    postgres_admin_password: str = Field(default="mafia_secret", alias="POSTGRES_ADMIN_PASSWORD")
    postgres_admin_db: str = Field(default="postgres", alias="POSTGRES_ADMIN_DB")

    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")

    aes_secret_key: str = Field(alias="AES_SECRET_KEY")
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=10080, alias="JWT_EXPIRE_MINUTES")

    admin_telegram_ids_raw: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")

    subscription_price_stars: int = Field(default=300, alias="SUBSCRIPTION_PRICE_STARS")
    subscription_days: int = Field(default=30, alias="SUBSCRIPTION_DAYS")
    grace_period_hours: int = Field(default=24, alias="GRACE_PERIOD_HOURS")
    data_retention_days: int = Field(default=30, alias="DATA_RETENTION_DAYS")
    # False = test mode: no Stars invoice, free subscription for deploy testing
    payments_enabled: bool = Field(default=True, alias="PAYMENTS_ENABLED")

    deploy_provider: str = Field(default="process", alias="DEPLOY_PROVIDER")
    mafia_image_name: str = Field(default="mafia-bot-template:latest", alias="MAFIA_IMAGE_NAME")
    template_path: str = Field(default=str(ROOT_DIR / "template" / "mafia-bot"), alias="TEMPLATE_PATH")
    deployments_root: str = Field(default=str(ROOT_DIR / "data" / "deployments"), alias="DEPLOYMENTS_ROOT")
    backups_root: str = Field(default=str(ROOT_DIR / "data" / "backups"), alias="BACKUPS_ROOT")
    docker_network: str = Field(default="mafia_builder_net", alias="DOCKER_NETWORK")
    python_executable: str = Field(default="python", alias="PYTHON_EXECUTABLE")

    support_url: str = Field(default="https://t.me", alias="SUPPORT_URL")
    brand_name: str = Field(default="True Mafia Builder", alias="BRAND_NAME")
    default_language: str = Field(default="uz", alias="DEFAULT_LANGUAGE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8080, alias="API_PORT")

    @field_validator("aes_secret_key")
    @classmethod
    def validate_aes_key(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 32:
            raise ValueError("AES_SECRET_KEY must be at least 32 characters (prefer 64 hex chars)")
        return cleaned

    @property
    def admin_telegram_ids(self) -> set[int]:
        ids: set[int] = set()
        for raw in self.admin_telegram_ids_raw.replace(";", ",").split(","):
            item = raw.strip()
            if item.lstrip("-").isdigit():
                ids.add(int(item))
        return ids

    @property
    def template_dir(self) -> Path:
        return Path(self.template_path).resolve()

    @property
    def deployments_dir(self) -> Path:
        path = Path(self.deployments_root).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def backups_dir(self) -> Path:
        path = Path(self.backups_root).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()
