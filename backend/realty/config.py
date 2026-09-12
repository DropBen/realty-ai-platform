from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "staging", "production"] = "development"
    demo_mode: bool = True
    database_url: str = "sqlite:///./data/realty-demo.db"
    app_origin: str = "http://localhost:5173"
    api_origin: str = "http://localhost:8000"
    cookie_secure: bool = False
    session_hours: int = Field(default=12, ge=1, le=168)
    encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google/callback"
    ai_provider: Literal["disabled", "openai"] = "disabled"
    ai_api_key: str = ""
    ai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: int = Field(default=30, ge=1, le=120)
    ai_monthly_limit: int = Field(default=1000, ge=0)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    storage_backend: Literal["local", "azure"] = "local"
    storage_path: str = "./data/documents"
    storage_connection_string: str = ""
    storage_container: str = "documents"
    metrics_token: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    require_email_verification: bool = False
    mail_backend: Literal["disabled", "outbox", "smtp"] = "disabled"
    mail_from: str = "RealtyAI <noreply@example.com>"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    mail_outbox_path: str = "./data/account-mail"

    @field_validator("app_origin", "api_origin")
    @classmethod
    def exact_origin(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
            or any(char.isspace() for char in value)
        ):
            raise ValueError(
                "Configure an HTTP(S) origin without credentials, path, query or fragment"
            )
        _ = parts.port  # Reject malformed or out-of-range ports.
        return value.rstrip("/")

    @model_validator(mode="after")
    def production_guards(self) -> "Settings":
        if self.app_env in {"staging", "production"}:
            if self.demo_mode or not self.cookie_secure or not self.encryption_key:
                raise ValueError("Production requires demo disabled, secure cookies and encryption")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if not all(
                origin.startswith("https://") for origin in (self.app_origin, self.api_origin)
            ):
                raise ValueError("Staging/production require HTTPS application and API origins")
            if not self.require_email_verification or self.mail_backend != "smtp":
                raise ValueError("Production requires email verification and SMTP delivery")
            if not self.smtp_host or not self.smtp_starttls or "example.com" in self.mail_from:
                raise ValueError("Production requires configured TLS mail and a verified sender")
        if self.demo_mode and self.mail_backend == "smtp":
            raise ValueError("Demo mode does not send external account email")
        if self.encryption_key:
            from cryptography.fernet import Fernet

            Fernet(self.encryption_key.encode())
        if self.demo_mode and self.ai_provider != "disabled":
            raise ValueError("Demo data must not be sent to an external AI provider")
        return self


settings = Settings()
Path("data").mkdir(exist_ok=True)
