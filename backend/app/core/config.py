"""Application settings, loaded from environment variables (12-factor).

Every value here has a matching, documented entry in the repo-root `.env.example`.
Nothing environment-specific (URLs, secrets, hostnames) may be hardcoded elsewhere.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]

_INSECURE_DEFAULT_SECRET = "change-me-in-env-at-least-32-characters-long"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "GlideUp API"
    environment: Environment = "local"
    log_level: str = "INFO"
    log_json: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # --- Database / cache ---
    database_url: str = "postgresql+asyncpg://glideup:glideup@localhost:5432/glideup"
    database_pool_size: int = 10
    database_echo: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # --- Auth ---
    jwt_secret: SecretStr = SecretStr(_INSECURE_DEFAULT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "glideup-api"
    jwt_audience: str = "glideup"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    # Seconds a just-rotated refresh token may be replayed (parallel requests) before
    # a replay is treated as token theft. 0 disables the grace window.
    refresh_reuse_grace_seconds: int = 30
    google_client_id: str | None = None
    google_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"
    # Dev-only password-less login so the app is usable before Google OAuth is configured.
    # Refused outright outside the "local"/"test" environments (see validator below).
    auth_dev_login_enabled: bool = False
    # Emails that are granted `super_admin` on sign-in. The only bootstrap path to admin.
    admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Observability ---
    metrics_enabled: bool = True

    @field_validator("cors_origins", "admin_emails", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("admin_emails")
    @classmethod
    def _lower_emails(cls, value: list[str]) -> list[str]:
        return [email.lower() for email in value]

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        if self.environment in ("staging", "production"):
            if self.auth_dev_login_enabled:
                raise ValueError("AUTH_DEV_LOGIN_ENABLED must be false outside local/test")
            secret = self.jwt_secret.get_secret_value()
            if secret == _INSECURE_DEFAULT_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET must be set to a strong value (32+ chars)")
        return self

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def is_local(self) -> bool:
        return self.environment in ("local", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
