"""
إعدادات التطبيق — يتم تحميلها من ملف .env
"""
from pathlib import Path
import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """إعدادات التطبيق المركزية"""

    # ── المسارات ──
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = Path(__file__).parent.parent / "data"

    # ── معلومات التطبيق ──
    APP_NAME: str = "أرحنا بها"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── قاعدة البيانات ──
    DATABASE_URL: str = "sqlite+aiosqlite:///./arihna_biha.db"

    # ── Google OAuth 2.0 ──
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback"

    # ── أوقات الصلاة (Aladhan API) ──
    DEFAULT_LATITUDE: float = 3.1390
    DEFAULT_LONGITUDE: float = 101.6869
    DEFAULT_TIMEZONE: str = "Asia/Kuala_Lumpur"
    PRAYER_CALCULATION_METHOD: int = 4  # Umm Al-Qura

    # ── الجدولة ──
    ADHKAR_OFFSET_MINUTES: int = 15  # حقن الذكر قبل الحدث بـ 15 دقيقة
    SYNC_DAYS_AHEAD: int = 1  # المزامنة التلقائية ليوم واحد
    PRAYER_SYNC_CRON_HOUR: int = 1  # مزامنة الصلاة الساعة 1 فجراً
    ADHKAR_SYNC_CRON_HOUR: int = 2  # حقن الأذكار الساعة 2 فجراً

    # ── التشفير ──
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"

    # ── CORS ──
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
