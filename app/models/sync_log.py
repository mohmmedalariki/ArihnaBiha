"""
نموذج تتبع المزامنة — لمنع التكرار (Idempotency)
"""
import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncLog(Base):
    """
    سجل المزامنة — يتتبع كل حدث تم إنشاؤه في التقويم
    لمنع التكرار عند إعادة تشغيل المزامنة
    """

    __tablename__ = "sync_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "event_type", "reference_id", "target_date",
                         name="uq_sync_event"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # ── نوع الحدث: prayer | adhkar ──
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── معرّف مرجعي: اسم الصلاة أو ID الحدث الأصلي ──
    reference_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── التاريخ المستهدف (لمنع تكرار نفس اليوم) ──
    target_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD

    # ── معرّف الحدث في Google Calendar ──
    google_event_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── الفئة (للأذكار فقط) ──
    adhkar_category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
