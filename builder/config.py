from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    builder_bot_token: str = Field(alias="BUILDER_BOT_TOKEN")
    builder_bot_username: str = Field(default="", alias="BUILDER_BOT_USERNAME")

    platform_database_url: str = Field(
        default=f"sqlite+aiosqlite:///{(ROOT_DIR / 'data' / 'platform.db').as_posix()}",
        alias="PLATFORM_DATABASE_URL",
    )

    aes_secret_key: str = Field(alias="AES_SECRET_KEY")
    admin_telegram_ids_raw: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")

    subscription_price_stars: int = Field(default=300, alias="SUBSCRIPTION_PRICE_STARS")
    subscription_days: int = Field(default=30, alias="SUBSCRIPTION_DAYS")
    # Immediate suspend on expiry; permanent purge after this many days
    grace_period_days: int = Field(default=7, alias="GRACE_PERIOD_DAYS")
    grace_period_hours: int = Field(default=168, alias="GRACE_PERIOD_HOURS")  # legacy alias (7d)
    payments_enabled: bool = Field(default=False, alias="PAYMENTS_ENABLED")

    # Limited-time offer banner
    promo_enabled: bool = Field(default=True, alias="PROMO_ENABLED")
    promo_title: str = Field(default="🔥 LIMITED OFFER", alias="PROMO_TITLE")
    promo_text: str = Field(
        default="Bugun ochsangiz — maxsus chegirma!",
        alias="PROMO_TEXT",
    )
    promo_discount_stars: int = Field(default=50, alias="PROMO_DISCOUNT_STARS")  # 300→250

    # Referral program
    referral_enabled: bool = Field(default=True, alias="REFERRAL_ENABLED")
    referral_invitee_discount: int = Field(default=50, alias="REFERRAL_INVITEE_DISCOUNT")  # new user pays less
    referral_reward_days: int = Field(default=7, alias="REFERRAL_REWARD_DAYS")  # referrer bonus days

    # Optional intro media (gif/mp4) — if file exists, sent on /start
    intro_media_path: str = Field(default=str(ROOT_DIR / "media" / "intro.mp4"), alias="INTRO_MEDIA_PATH")

    template_path: str = Field(default=str(ROOT_DIR / "template" / "mafia-bot"), alias="TEMPLATE_PATH")
    deployments_root: str = Field(default=str(ROOT_DIR / "data" / "deployments"), alias="DEPLOYMENTS_ROOT")
    backups_root: str = Field(default=str(ROOT_DIR / "data" / "backups"), alias="BACKUPS_ROOT")
    python_executable: str = Field(default="python3", alias="PYTHON_EXECUTABLE")

    support_url: str = Field(default="https://t.me", alias="SUPPORT_URL")
    brand_name: str = Field(default="True Mafia Builder", alias="BRAND_NAME")
    default_language: str = Field(default="uz", alias="DEFAULT_LANGUAGE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def effective_price(self) -> int:
        """Base price after global promo (before personal credits)."""
        price = self.subscription_price_stars
        if self.promo_enabled and self.promo_discount_stars > 0:
            price = max(50, price - self.promo_discount_stars)
        return price

    @field_validator("aes_secret_key")
    @classmethod
    def _aes(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 32:
            raise ValueError("AES_SECRET_KEY kamida 32 belgi bo'lishi kerak")
        return v

    @property
    def admin_telegram_ids(self) -> set[int]:
        out: set[int] = set()
        for part in self.admin_telegram_ids_raw.replace(";", ",").split(","):
            p = part.strip()
            if p.lstrip("-").isdigit():
                out.add(int(p))
        return out

    @property
    def template_dir(self) -> Path:
        return Path(self.template_path).resolve()

    @property
    def deployments_dir(self) -> Path:
        p = Path(self.deployments_root).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def backups_dir(self) -> Path:
        p = Path(self.backups_root).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()
