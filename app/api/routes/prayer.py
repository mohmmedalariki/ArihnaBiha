"""
مسارات مزامنة أوقات الصلاة
"""
from datetime import date, datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.sync_log import SyncLog
from app.services.aladhan import aladhan_service
from app.services.google_calendar import calendar_service

router = APIRouter(prefix="/prayer", tags=["أوقات الصلاة"])


@router.get("/times")
async def get_prayer_times(
    user: User = Depends(get_current_user),
):
    """جلب أوقات الصلاة لليوم بناءً على موقع المستخدم"""
    prayers = await aladhan_service.get_prayer_times(
        latitude=user.latitude,
        longitude=user.longitude,
        timezone=user.timezone,
        method=settings.PRAYER_CALCULATION_METHOD,
    )
    return {"date": date.today().isoformat(), "prayers": prayers}


@router.post("/sync")
async def sync_prayer_times(
    target_date: str | None = None,
    days: int = 1,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    مزامنة أوقات الصلاة مع Google Calendar
    """
    from datetime import timedelta
    
    start_date = date.fromisoformat(target_date) if target_date else date.today()
    service = calendar_service._build_service(user.access_token, user.refresh_token)
    
    total_created = []
    
    for i in range(days):
        current_date = start_date + timedelta(days=i)
        date_str = current_date.isoformat()
        
        prayers = await aladhan_service.get_prayer_times(
            latitude=user.latitude,
            longitude=user.longitude,
            target_date=current_date,
            timezone=user.timezone,
            method=settings.PRAYER_CALCULATION_METHOD,
        )

        for prayer in prayers:
            existing = await db.execute(
                select(SyncLog).where(
                    SyncLog.user_id == user.id,
                    SyncLog.event_type == "prayer",
                    SyncLog.reference_id == prayer["name_en"],
                    SyncLog.target_date == date_str,
                )
            )
            if existing.scalar_one_or_none():
                continue

            result = calendar_service.create_prayer_event(
                service=service,
                calendar_id=user.calendar_id,
                prayer_name=prayer["name_ar"],
                prayer_time=prayer["time"],
                target_date=date_str,
                timezone=user.timezone,
            )

            log = SyncLog(
                user_id=user.id,
                event_type="prayer",
                reference_id=prayer["name_en"],
                target_date=date_str,
                google_event_id=result["id"],
            )
            db.add(log)
            total_created.append(f"{prayer['name_ar']} ({date_str})")

    return {
        "synced": len(total_created),
        "prayers": total_created,
        "date": start_date.isoformat(),
        "days": days
    }


@router.put("/settings")
async def update_location(
    latitude: float,
    longitude: float,
    timezone: str = "Asia/Kuala_Lumpur",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """تحديث موقع المستخدم لأوقات الصلاة"""
    user.latitude = latitude
    user.longitude = longitude
    user.timezone = timezone
    return {"message": "تم تحديث الموقع ✅"}
