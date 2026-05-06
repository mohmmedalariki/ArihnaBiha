"""
مسارات الأذكار — تصنيف وحقن
⚡ يستخدم Batch Classification: طلب Gemini واحد لكل الأحداث
"""
import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.sync_log import SyncLog
from app.services.google_calendar import calendar_service
from app.services.adhkar_injector import adhkar_injector, get_adhkar_db
from app.services.ai_classifier import ai_classifier

router = APIRouter(prefix="/adhkar", tags=["الأذكار"])


@router.get("/categories")
async def list_categories():
    """قائمة جميع فئات الأذكار المدعومة"""
    db = get_adhkar_db()
    categories = []
    for key, val in db.get("adhkar", {}).items():
        categories.append({
            "tag": val.get("category_id"),
            "dua_key": key,
            "title_ar": val.get("label_ar"),
            "title_en": val.get("label_en"),
            "duas_count": len(val.get("duas", []))
        })
    return {"categories": categories, "total": len(categories)}


@router.post("/classify")
async def classify_event(
    title: str,
    description: str = "",
    user: User = Depends(get_current_user),
):
    """تصنيف حدث تجريبي (بدون إنشاء حدث في التقويم)"""
    result = await adhkar_injector.classify_and_get_adhkar(title, description)
    if not result:
        return {"category": "general", "adhkar": None}
    return {"category": result.category, "adhkar": result.to_dict()}


@router.post("/sync")
async def sync_adhkar(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ⚡ المزامنة الكاملة للأذكار (Batch Mode):
    1. جلب الأحداث القادمة
    2. فلترة الأحداث الجديدة فقط
    3. تصنيف الكل في طلب Gemini واحد
    4. جلب الأذكار وحقنها
    """
    service = calendar_service._build_service(user.access_token, user.refresh_token)

    # جلب الأحداث القادمة
    events = calendar_service.get_upcoming_events(
        service=service,
        calendar_id=user.calendar_id,
        days_ahead=settings.SYNC_DAYS_AHEAD,
    )

    # فلترة: فقط الأحداث التي لم تُصنَّف بعد
    new_events = []
    for event in events:
        event_id = event.get("id", "")
        event_date = event.get("start", {}).get("dateTime", "")[:10]
        if not event_id or not event_date:
            continue

        existing = await db.execute(
            select(SyncLog).where(
                SyncLog.user_id == user.id,
                SyncLog.event_type == "adhkar",
                SyncLog.reference_id == event_id,
            )
        )
        if not existing.scalar_one_or_none():
            new_events.append(event)

    if not new_events:
        return {"injected": 0, "details": [], "message": "لا توجد أحداث جديدة"}

    # ⚡ تصنيف جميع الأحداث في طلب واحد
    batch_input = [
        {
            "id": ev.get("id"),
            "title": ev.get("summary", ""),
            "description": ev.get("description", ""),
        }
        for ev in new_events
    ]
    classifications = await ai_classifier.classify_events_batch(batch_input)

    # حقن الأذكار بناءً على التصنيفات
    injected = []
    for event in new_events:
        event_id = event.get("id", "")
        event_date = event.get("start", {}).get("dateTime", "")[:10]
        dua_key = classifications.get(event_id, "dua_fallback")

        if dua_key == "dua_fallback":
            continue

        # جلب الذكر المناسب من القاعدة المحلية
        adhkar = adhkar_injector._fetch_adhkar_for_category(dua_key)
        if not adhkar:
            continue

        # إنشاء الحدث في التقويم
        try:
            event_start = event.get("start", {}).get("dateTime", "")
            result = calendar_service.create_adhkar_event(
                service=service,
                calendar_id=user.calendar_id,
                adhkar_title=adhkar.title,
                adhkar_text=adhkar.text,
                source=adhkar.source,
                original_event_id=event_id,
                event_start=event_start,
                category=adhkar.category,
                timezone=user.timezone,
            )

            # تسجيل المزامنة
            log = SyncLog(
                user_id=user.id,
                event_type="adhkar",
                reference_id=event_id,
                target_date=event_date,
                google_event_id=result["id"],
                adhkar_category=adhkar.category,
            )
            db.add(log)
            injected.append({
                "event": event.get("summary"),
                "category": adhkar.category,
                "adhkar": result.get("summary"),
            })
        except Exception as e:
            print(f"⚠️ فشل حقن ذكر للحدث '{event.get('summary')}': {e}")

    return {"injected": len(injected), "details": injected}


@router.get("/preview/{dua_key}")
async def preview_adhkar(dua_key: str):
    """جلب أذكار تجريبية لفئة معينة"""
    result = adhkar_injector._fetch_adhkar_for_category(dua_key)
    if not result:
        return {"error": f"لم يُعثر على أذكار للفئة: {dua_key}"}
    return result.to_dict()
