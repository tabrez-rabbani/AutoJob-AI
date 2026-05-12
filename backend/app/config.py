"""
AutoJob AI — Application Configuration
Loads settings from environment variables using pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────
    app_name: str = "AutoJob AI"
    app_env: str = "development"
    debug: bool = False  # Must explicitly set DEBUG=true in .env for dev

    # ── Database ─────────────────────────────────────
    database_url: str = "postgresql+asyncpg://autojob:autojob_dev@localhost:5432/autojob"

    # ── Redis ────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── JWT Auth ─────────────────────────────────────
    jwt_secret_key: str = "change-me-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # ── Encryption ───────────────────────────────────
    encryption_key: str = "change-me-to-a-32-byte-hex-key"

    # ── LLM Provider ─────────────────────────────────
    llm_provider: str = "gemini"  # "gemini", "openai", or "groq"
    llm_api_key: str = ""
    llm_model: str = ""  # empty = use provider default
    llm_base_url: str = ""  # empty = use provider default

    # ── Celery ───────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Proxy ────────────────────────────────────────
    # Comma-separated list:  "http://user:pass@host:port, socks5://host:port"
    proxy_list: str = ""
    proxy_rotation: str = "round_robin"  # "round_robin", "random", "sticky"

    # ── CAPTCHA Solver ───────────────────────────────
    captcha_provider: str = ""  # "2captcha", "capsolver", or "" (manual)
    captcha_api_key: str = ""
    captcha_timeout: int = 120  # seconds to wait for solve

    # ── Rate Limiting (Daily Safe Limits) ────────────
    # LinkedIn gives out bans very easily if pushed too fast.
    linkedin_max_scrapes_per_day: int = 50
    linkedin_max_applies_per_day: int = 10

    # Naukri is more forgiving of automation
    naukri_max_scrapes_per_day: int = 100
    naukri_max_applies_per_day: int = 25

    # Indeed and Glassdoor are moderate
    indeed_max_scrapes_per_day: int = 75
    indeed_max_applies_per_day: int = 20

    glassdoor_max_scrapes_per_day: int = 50
    glassdoor_max_applies_per_day: int = 15

    # Wait times between actions
    min_delay_between_applies: int = 10   # seconds
    max_delay_between_applies: int = 25   # seconds

    # ── Retry ────────────────────────────────────────
    max_retries_per_job: int = 1         # max times to retry a failed apply (1 retry = 2 total attempts)
    retry_base_delay: int = 10           # first retry waits 10s

    # ── Google OAuth ─────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""

    # ── CORS ─────────────────────────────────────────
    # Comma-separated list of allowed origins
    # e.g. "http://localhost:3000,https://autojob.ai"
    frontend_url: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        """Parse frontend_url into a list of allowed origins."""
        return [u.strip() for u in self.frontend_url.split(",") if u.strip()]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


# Singleton instance — import this everywhere
settings = Settings()
