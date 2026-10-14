"""Application configuration loaded from environment / .env files.

Never hardcode secrets. Use `.env.example` as the template.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. All sensitive values come from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    APP_ENV: str = Field(default="development")
    APP_NAME: str = Field(default="DMS Backend")
    API_V1_PREFIX: str = Field(default="/api/v1")
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")
    # Interactive docs (/api/docs, /api/openapi.json).
    # Default False so production deployments do not expose docs accidentally.
    # Non-production APP_ENV still enables docs regardless of this flag
    # (see main.create_app). Set ENABLE_API_DOCS=true to opt-in on production.
    ENABLE_API_DOCS: bool = Field(default=False)

    MYSQL_HOST: str = Field(default="127.0.0.1")
    MYSQL_PORT: int = Field(default=3306)
    MYSQL_DATABASE: str = Field(default="dms")
    MYSQL_USER: str = Field(default="dms_user")
    MYSQL_PASSWORD: str = Field(default="")
    MYSQL_ECHO: bool = Field(default=False)

    SECRET_KEY: str = Field(default="")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=14)
    JWT_ALGORITHM: str = Field(default="HS256")

    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"])

    # Bootstrap admin (used only by init_admin script / first boot seed)
    DMS_ADMIN_USERNAME: str = Field(default="admin")
    DMS_ADMIN_PASSWORD: str = Field(default="")
    DMS_ADMIN_DISPLAY_NAME: str = Field(default="Super Administrator")

    # M4 background scanner (reservation expiry + alert refresh)
    SCANNER_ENABLED: bool = Field(default=True)
    SCANNER_INTERVAL_SECONDS: int = Field(default=60, ge=5)

    @property
    def database_url(self) -> str:
        """Build an async SQLAlchemy URL with safe escaping for special chars."""
        from sqlalchemy.engine import URL

        return URL.create(
            drivername="mysql+asyncmy",
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD,
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            database=self.MYSQL_DATABASE,
        ).render_as_string(hide_password=False)

    @property
    def sync_database_url(self) -> str:
        """Sync URL used by Alembic migrations."""
        from sqlalchemy.engine import URL

        return URL.create(
            drivername="mysql+pymysql",
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD,
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            database=self.MYSQL_DATABASE,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
