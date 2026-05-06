"""
خدمة أوقات الصلاة — جلب الأوقات من Aladhan API
"""
import httpx
from datetime import date
from typing import TypedDict


class PrayerTime(TypedDict):
    name_ar: str
    name_en: str
    time: str  # HH:MM


class AladhanService:
    """جلب أوقات الصلاة الدقيقة بناءً على الموقع الجغرافي"""

    BASE_URL = "https://api.aladhan.com/v1/timings"

    PRAYER_NAMES = {
        "Fajr": "الفجر",
        "Dhuhr": "الظهر",
        "Asr": "العصر",
        "Maghrib": "المغرب",
        "Isha": "العشاء",
    }

    async def get_prayer_times(
        self,
        latitude: float,
        longitude: float,
        target_date: date | None = None,
        method: int = 4,
        timezone: str = "Asia/Kuala_Lumpur",
    ) -> list[PrayerTime]:
        """
        جلب أوقات الصلوات الخمس لتاريخ معيّن

        Args:
            latitude: خط العرض
            longitude: خط الطول
            target_date: التاريخ المطلوب (اليوم افتراضياً)
            method: طريقة الحساب (4 = أم القرى)
            timezone: المنطقة الزمنية

        Returns:
            قائمة بأوقات الصلوات الخمس
        """
        if target_date is None:
            target_date = date.today()

        timestamp = int(target_date.strftime("%s")) if hasattr(target_date, "strftime") else None
        url = f"{self.BASE_URL}/{target_date.strftime('%d-%m-%Y')}"

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "method": method,
            "timezonestring": timezone,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            timings = data["data"]["timings"]
            prayers: list[PrayerTime] = []

            for eng_name, ar_name in self.PRAYER_NAMES.items():
                raw_time = timings.get(eng_name, "00:00")
                # إزالة أي معلومات إضافية بعد الوقت (مثل التوقيت الصيفي)
                clean_time = raw_time.split(" ")[0]
                prayers.append(PrayerTime(
                    name_ar=ar_name,
                    name_en=eng_name,
                    time=clean_time,
                ))

            return prayers

        except httpx.HTTPError as e:
            raise RuntimeError(f"فشل جلب أوقات الصلاة من Aladhan API: {e}") from e
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"خطأ في تحليل بيانات Aladhan API: {e}") from e


aladhan_service = AladhanService()
