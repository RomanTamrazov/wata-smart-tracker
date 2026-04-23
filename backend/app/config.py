from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./wata_tracker_v2.db")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    ollama_request_timeout_seconds: int = int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "120"))
    frontend_dist_dir: str = os.getenv("FRONTEND_DIST_DIR", "")
    timezone: str = os.getenv("APP_TIMEZONE", "Europe/Moscow")
    token_ttl_hours: int = int(os.getenv("TOKEN_TTL_HOURS", "72"))
    enable_reminder_worker: bool = os.getenv("ENABLE_REMINDER_WORKER", "true").lower() == "true"
    reminder_worker_interval_seconds: int = int(os.getenv("REMINDER_WORKER_INTERVAL_SECONDS", "300"))

    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str | None = os.getenv("SMTP_USER")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from: str | None = os.getenv("SMTP_FROM")
    smtp_starttls: bool = os.getenv("SMTP_STARTTLS", "true").lower() == "true"
    smtp_ssl: bool = os.getenv("SMTP_SSL", "false").lower() == "true"

    cors_origins_raw: str = os.getenv("CORS_ORIGINS", "")
    email_check_deliverability: bool = os.getenv("EMAIL_CHECK_DELIVERABILITY", "true").lower() == "true"
    blocked_email_domains_raw: str = os.getenv(
        "BLOCKED_EMAIL_DOMAINS",
        "example.com,example.org,example.net,mailinator.com,10minutemail.com,guerrillamail.com,temp-mail.org",
    )

    upload_dir: str = os.getenv("UPLOAD_DIR", "./storage/uploads")
    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))

    ocr_enabled: bool = os.getenv("OCR_ENABLED", "true").lower() == "true"
    ocr_lang: str = os.getenv("OCR_LANG", "rus+eng")

    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_api_base: str = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
    telegram_poll_interval_seconds: int = int(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "2"))
    telegram_login_attempt_limit: int = int(os.getenv("TELEGRAM_LOGIN_ATTEMPT_LIMIT", "5"))


settings = Settings()
