"""
المجدول — APScheduler مدمج مع FastAPI
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.user import User
from app.services.aladhan import aladhan_service
from app.services.google_calendar import calendar_service
from app.services.adhkar_injector import adhkar_injector
from app.models.sync_log import SyncLog
from datetime import date

scheduler = AsyncIOScheduler()


async def _sync_prayers_for_all_users():
    """مهمة مجدولة: مزامنة أوقات الصلاة لجميع المستخدمين النشطين"""
    print("🕌 بدء مزامنة أوقات الصلاة لجميع المستخدمين...")

    async with async_session_factory() as db:
        result = await db.execute(
            select(User).where(User.is_active == True, User.auto_sync_enabled == True)
        )
        users = result.scalars().all()

        for user in users:
            try:
                today = date.today().isoformat()
                prayers = await aladhan_service.get_prayer_times(
                    latitude=user.latitude,
                    longitude=user.longitude,
                    timezone=user.timezone,
                    method=settings.PRAYER_CALCULATION_METHOD,
                )

                service = calendar_service._build_service(user.access_token, user.refresh_token)

                for prayer in prayers:
                    # التحقق من عدم التكرار
                    existing = await db.execute(
                        select(SyncLog).where(
                            SyncLog.user_id == user.id,
                            SyncLog.event_type == "prayer",
                            SyncLog.reference_id == prayer["name_en"],
                            SyncLog.target_date == today,
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    result = calendar_service.create_prayer_event(
                        service=service,
                        calendar_id=user.calendar_id,
                        prayer_name=prayer["name_ar"],
                        prayer_time=prayer["time"],
                        target_date=today,
                        timezone=user.timezone,
                    )

                    log = SyncLog(
                        user_id=user.id,
                        event_type="prayer",
                        reference_id=prayer["name_en"],
                        target_date=today,
                        google_event_id=result["id"],
                    )
                    db.add(log)

                await db.commit()
                print(f"  ✅ {user.email}: تمت مزامنة الصلوات")

            except Exception as e:
                print(f"  ❌ {user.email}: فشلت المزامنة — {e}")


async def _sync_adhkar_for_all_users():
    """مهمة مجدولة: تحليل الأحداث وحقن الأذكار لجميع المستخدمين"""
    print("🤲 بدء حقن الأذكار لجميع المستخدمين...")

    async with async_session_factory() as db:
        result = await db.execute(
            select(User).where(User.is_active == True, User.auto_sync_enabled == True)
        )
        users = result.scalars().all()

        for user in users:
            try:
                service = calendar_service._build_service(user.access_token, user.refresh_token)
                events = calendar_service.get_upcoming_events(
                    service=service,
                    calendar_id=user.calendar_id,
                    days_ahead=settings.SYNC_DAYS_AHEAD,
                )

                count = 0
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
                    if existing.scalar_one_or_none():
                        continue

                    cal_result = await adhkar_injector.inject_adhkar_for_event(
                        service=service,
                        calendar_id=user.calendar_id,
                        event=event,
                        timezone=user.timezone,
                    )

                    if cal_result:
                        log = SyncLog(
                            user_id=user.id,
                            event_type="adhkar",
                            reference_id=event_id,
                            target_date=event_date,
                            google_event_id=cal_result["id"],
                        )
                        db.add(log)
                        count += 1

                await db.commit()
                print(f"  ✅ {user.email}: تم حقن {count} أذكار")

            except Exception as e:
                print(f"  ❌ {user.email}: فشل الحقن — {e}")


def setup_scheduler():
    """إعداد المهام المجدولة"""
    # مزامنة أوقات الصلاة يومياً
    scheduler.add_job(
        _sync_prayers_for_all_users,
        CronTrigger(hour=settings.PRAYER_SYNC_CRON_HOUR, minute=0),
        id="prayer_sync",
        name="مزامنة أوقات الصلاة اليومية",
        replace_existing=True,
    )

    # حقن الأذكار يومياً
    scheduler.add_job(
        _sync_adhkar_for_all_users,
        CronTrigger(hour=settings.ADHKAR_SYNC_CRON_HOUR, minute=0),
        id="adhkar_sync",
        name="حقن الأذكار اليومي",
        replace_existing=True,
    )

    scheduler.start()
    print("⏰ تم تشغيل المجدول — الصلاة: {}:00 | الأذكار: {}:00".format(
        settings.PRAYER_SYNC_CRON_HOUR, settings.ADHKAR_SYNC_CRON_HOUR
    ))
