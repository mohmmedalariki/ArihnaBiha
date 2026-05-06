"""
خدمة Google Calendar — إدارة الأحداث (CRUD)
"""
from datetime import datetime, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

# ── علامة النظام لتمييز أحداثنا ──
SYSTEM_SOURCE_KEY = "arihna_biha"
EXTENDED_PROP_KEY = "arihna_biha_type"


class GoogleCalendarService:
    """إدارة أحداث Google Calendar"""

    SCOPES = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
    ]

    def _build_service(self, access_token: str, refresh_token: str | None = None):
        """بناء خدمة Google Calendar API"""
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=self.SCOPES,
        )
        return build("calendar", "v3", credentials=creds)

    def create_prayer_event(
        self,
        service,
        calendar_id: str,
        prayer_name: str,
        prayer_time: str,
        target_date: str,
        timezone: str,
    ) -> dict[str, Any]:
        """
        إنشاء حدث صلاة في التقويم

        Args:
            service: خدمة Google Calendar
            calendar_id: معرّف التقويم
            prayer_name: اسم الصلاة بالعربي
            prayer_time: وقت الصلاة (HH:MM)
            target_date: التاريخ (YYYY-MM-DD)
            timezone: المنطقة الزمنية
        """
        start_dt = f"{target_date}T{prayer_time}:00"
        # مدة حدث الصلاة: 30 دقيقة
        end_hour, end_min = prayer_time.split(":")
        end_dt_obj = datetime.strptime(f"{target_date} {prayer_time}", "%Y-%m-%d %H:%M") + timedelta(minutes=30)
        end_dt = end_dt_obj.strftime(f"%Y-%m-%dT%H:%M:%S")

        event = {
            "summary": f"🕌 صلاة {prayer_name}",
            "description": f"وقت صلاة {prayer_name} — أُضيف تلقائياً بواسطة أرحنا بها",
            "start": {"dateTime": start_dt, "timeZone": timezone},
            "end": {"dateTime": end_dt, "timeZone": timezone},
            "colorId": "2",  # أخضر
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 10}],
            },
            "extendedProperties": {
                "private": {
                    EXTENDED_PROP_KEY: "prayer",
                    "source": SYSTEM_SOURCE_KEY,
                    "prayer_name": prayer_name,
                }
            },
        }

        try:
            return service.events().insert(calendarId=calendar_id, body=event).execute()
        except HttpError as e:
            raise RuntimeError(f"فشل إنشاء حدث الصلاة: {e}") from e

    def create_adhkar_event(
        self,
        service,
        calendar_id: str,
        adhkar_title: str,
        adhkar_text: str,
        source: str,
        original_event_id: str,
        event_start: str,
        category: str,
        timezone: str,
        offset_minutes: int = 15,
    ) -> dict[str, Any]:
        """
        إنشاء حدث ذكر قبل الحدث الأصلي

        Args:
            adhkar_title: عنوان الذكر
            adhkar_text: نص الذكر
            source: مصدر الذكر (حديث/آية)
            original_event_id: معرّف الحدث الأصلي
            event_start: وقت بداية الحدث الأصلي (ISO format)
            category: فئة الذكر
            timezone: المنطقة الزمنية
            offset_minutes: دقائق قبل الحدث
        """
        start_obj = datetime.fromisoformat(event_start.replace("Z", "+00:00"))
        adhkar_start = start_obj - timedelta(minutes=offset_minutes)
        adhkar_end = start_obj - timedelta(minutes=2)

        event = {
            "summary": f"🤲 {adhkar_title}",
            "description": f"{adhkar_text}\n\n📖 المصدر: {source}\n\n— أُضيف تلقائياً بواسطة أرحنا بها",
            "start": {"dateTime": adhkar_start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": adhkar_end.isoformat(), "timeZone": timezone},
            "colorId": "5",  # أصفر/ذهبي
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 0}],
            },
            "extendedProperties": {
                "private": {
                    EXTENDED_PROP_KEY: "adhkar",
                    "source": SYSTEM_SOURCE_KEY,
                    "category": category,
                    "linked_event_id": original_event_id,
                }
            },
        }

        try:
            return service.events().insert(calendarId=calendar_id, body=event).execute()
        except HttpError as e:
            raise RuntimeError(f"فشل إنشاء حدث الذكر: {e}") from e

    def get_upcoming_events(
        self,
        service,
        calendar_id: str,
        days_ahead: int = 3,
    ) -> list[dict[str, Any]]:
        """جلب الأحداث القادمة (باستثناء أحداث النظام)"""
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        try:
            result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            ).execute()

            events = result.get("items", [])

            # استبعاد أحداث النظام (الصلاة والأذكار المُضافة سابقاً)
            user_events = []
            for ev in events:
                ext_props = ev.get("extendedProperties", {}).get("private", {})
                if ext_props.get("source") != SYSTEM_SOURCE_KEY:
                    user_events.append(ev)

            return user_events

        except HttpError as e:
            raise RuntimeError(f"فشل جلب الأحداث: {e}") from e

    def delete_system_events(
        self,
        service,
        calendar_id: str,
        target_date: str,
        event_type: str = "prayer",
    ) -> int:
        """حذف أحداث النظام القديمة لتاريخ محدد (للتحديث الذكي)"""
        time_min = f"{target_date}T00:00:00Z"
        time_max = f"{target_date}T23:59:59Z"

        try:
            result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                privateExtendedProperty=f"source={SYSTEM_SOURCE_KEY}",
                privateExtendedProperty2=f"{EXTENDED_PROP_KEY}={event_type}" if event_type else None,
                singleEvents=True,
                maxResults=50,
            ).execute()

            deleted = 0
            for ev in result.get("items", []):
                ext = ev.get("extendedProperties", {}).get("private", {})
                if ext.get(EXTENDED_PROP_KEY) == event_type:
                    service.events().delete(calendarId=calendar_id, eventId=ev["id"]).execute()
                    deleted += 1

            return deleted

        except HttpError as e:
            raise RuntimeError(f"فشل حذف الأحداث: {e}") from e


calendar_service = GoogleCalendarService()
