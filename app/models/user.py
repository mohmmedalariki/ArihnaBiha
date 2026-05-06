"""
نماذج المستخدم والتوكنات — User & Token Models
"""
import datetime
from sqlalchemy import String, DateTime, Text, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """نموذج المستخدم — يُخزّن بيانات Google OAuth"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    google_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    picture_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── التوكنات المشفّرة ──
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── إعدادات المستخدم ──
    latitude: Mapped[float] = mapped_column(default=3.1390)
    longitude: Mapped[float] = mapped_column(default=101.6869)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kuala_Lumpur")
    calendar_id: Mapped[str] = mapped_column(String(255), default="primary")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── الطوابع الزمنية ──
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
