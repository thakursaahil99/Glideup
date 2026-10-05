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
    # Where browsers reach this API directly (only the interview WebSocket does; everything
    # else goes through the web app's BFF).
    api_public_url: str = "http://localhost:8000"
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

    # --- Background work ---
    # "celery" sends tasks to Redis for the worker; "inline" runs them in the API process
    # (local development without Redis, and tests). Same task code either way.
    task_execution: Literal["celery", "inline"] = "celery"

    # --- File storage ---
    storage_backend: Literal["s3", "local"] = "s3"
    local_storage_path: str = "./var/storage"
    s3_endpoint_url: str | None = None  # None = AWS; set for MinIO / other S3-compatible stores
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    s3_bucket_resumes: str = "resumes"

    # --- Job search & ingestion ---
    # "meilisearch" (falls back to the database if Meilisearch is unreachable) or "database".
    search_backend: Literal["meilisearch", "database"] = "meilisearch"
    meili_url: str = "http://localhost:7700"
    meili_master_key: SecretStr | None = None
    meili_jobs_index: str = "jobs"
    adzuna_app_id: str | None = None
    adzuna_app_key: SecretStr | None = None
    # Run due ingestions from the API process every N minutes when TASK_EXECUTION=inline
    # (development without Celery Beat). 0 disables it.
    inline_scheduler_minutes: int = 5

    # --- Resumes ---
    resume_max_bytes: int = 5 * 1024 * 1024
    resume_max_pages: int = 10

    # --- Portfolio analysis ---
    portfolio_fetch_max_bytes: int = 2 * 1024 * 1024
    portfolio_fetch_timeout_seconds: float = 10.0
    # Optional: raises GitHub's API limit from 60 to 5,000 requests/hour. No scopes needed.
    github_api_token: SecretStr | None = None

    # --- LLM providers ---
    ollama_base_url: str = "http://localhost:11434"
    github_models_base_url: str = "https://models.github.ai/inference"
    github_models_token: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: SecretStr | None = None
    llm_timeout_seconds: float = 90.0
    # Per-provider overrides (JSON). A 3B model on a laptop CPU can need minutes per resume.
    llm_provider_timeouts: dict[str, float] = Field(default_factory=lambda: {"ollama": 240.0})
    ollama_num_ctx: int = 8192  # context window; Ollama's default can silently truncate resumes
    # Task -> ordered "provider:model" fallback chain, as JSON. Overrides the code defaults
    # (app/llm/routing.py) per task. Phase 9 moves this into the admin console.
    llm_routes: dict[str, list[str]] = Field(default_factory=dict)
    # Append the mock provider as the last resort. Local/test only: it returns heuristic
    # output, which must never silently replace a real model in production.
    llm_allow_mock_fallback: bool = False
    # AI skill-gap analyses a user may start per 24 hours (each is one LLM call).
    match_analysis_daily_limit: int = Field(default=30, ge=0)
    # Mock interviews a user may start per 24 hours.
    interviews_daily_limit: int = Field(default=10, ge=0)

    # --- Code sandbox (Phase 6) ---
    # piston: local default (works on cgroup v2 / Docker Desktop); judge0: Judge0 CE; fake: tests.
    code_runner: Literal["piston", "judge0", "fake"] = "piston"
    piston_url: str = "http://localhost:2000"
    judge0_url: str = "http://localhost:2358"
    judge0_auth_token: SecretStr | None = None
    code_runner_concurrency: int = Field(default=4, ge=1, le=32)  # test cases run in parallel
    submissions_per_minute: int = Field(default=10, ge=1)
    mock_llm_delay_ms: int = 0
    mock_llm_error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_cooldown_seconds: float = 30.0

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
            if self.llm_allow_mock_fallback:
                raise ValueError("LLM_ALLOW_MOCK_FALLBACK must be false outside local/test")
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


_override: Settings | None = None


@lru_cache
def _load_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return _override or _load_settings()


def override_settings(settings: Settings | None) -> None:
    """Tests and scripts swap the process-wide settings (None restores the environment's)."""
    global _override
    _override = settings
