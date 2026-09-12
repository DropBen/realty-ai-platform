from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    demo_mode: bool = True
    database_url: str = "sqlite:///./data/realty-demo.db"
    app_origin: str = "http://localhost:5173"
    api_origin: str = "http://localhost:8000"
    cookie_secure: bool = False
    session_hours: int = 12
    encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google/callback"
    ai_provider: str = "disabled"
    ai_api_key: str = ""
    ai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: int = 30
    ai_monthly_limit: int = 1000
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    storage_backend: str = "local"
    storage_path: str = "./data/documents"
    storage_connection_string: str = ""
    storage_container: str = "documents"
    metrics_token: str = ""
    log_level: str = "INFO"
    require_email_verification: bool = False
    mail_backend: str = "disabled"
    mail_from: str = "RealtyAI <noreply@example.com>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    mail_outbox_path: str = "./data/account-mail"

    @model_validator(mode="after")
    def production_guards(self) -> "Settings":
        if self.app_env == "production":
            if self.demo_mode or not self.cookie_secure or not self.encryption_key:
                raise ValueError("Production requires demo disabled, secure cookies and encryption")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if not self.app_origin.startswith("https://"):
                raise ValueError("Production requires an HTTPS application origin")
            if not self.require_email_verification or self.mail_backend != "smtp":
                raise ValueError("Production requires email verification and SMTP delivery")
            if not self.smtp_host or not self.smtp_starttls or "example.com" in self.mail_from:
                raise ValueError("Production requires configured TLS mail and a verified sender")
        if self.mail_backend not in {"disabled", "outbox", "smtp"}:
            raise ValueError("Choose disabled, outbox or smtp for account mail")
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
