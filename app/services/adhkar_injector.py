import json
import random
from pathlib import Path
from typing import Any

from app.services.ai_classifier import ai_classifier
from app.services.google_calendar import calendar_service
from app.core.config import settings

def _load_adhkar() -> dict:
    filepath = settings.DATA_DIR / "adhkar.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

_adhkar_data: dict | None = None

def get_adhkar_db() -> dict:
    global _adhkar_data
    if _adhkar_data is None:
        _adhkar_data = _load_adhkar()
    return _adhkar_data

class AdhkarResult:
    def __init__(self, title: str, text: str, source: str, category: str):
        self.title = title
        self.text = text
        self.source = source
        self.category = category

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "text": self.text,
            "source": self.source,
            "category": self.category
        }

class AdhkarInjector:
    def _fetch_adhkar_for_category(self, dua_key: str) -> AdhkarResult | None:
        db = get_adhkar_db()
        adhkar_section = db.get("adhkar", {})
        
        if dua_key not in adhkar_section:
            return None
            
        category_data = adhkar_section[dua_key]
        duas = category_data.get("duas", [])
        
        if not duas:
            return None
            
        chosen_dua = random.choice(duas)
        arabic_text = chosen_dua.get("arabic", "").strip()
        source = chosen_dua.get("source", "")
        
        title = category_data.get("calendar_title", category_data.get("label_ar", "دعاء"))
        
        return AdhkarResult(
            title=title,
            text=arabic_text,
            source=source,
            category=category_data.get("category_id", "general")
        )

    async def classify_and_get_adhkar(
        self, event_title: str, event_description: str = "", event_location: str = ""
    ) -> AdhkarResult | None:
        classification = await ai_classifier.classify_event(event_title, event_description, event_location)
        dua_key = classification["dua_key"]

        if dua_key == "dua_fallback":
            return None

        return self._fetch_adhkar_for_category(dua_key)

    async def inject_adhkar_for_event(
        self,
        service,
        calendar_id: str,
        event: dict,
        timezone: str,
        offset_minutes: int | None = None,
    ) -> dict | None:
        if offset_minutes is None:
            offset_minutes = settings.ADHKAR_OFFSET_MINUTES

        title = event.get("summary", "")
        description = event.get("description", "")
        location = event.get("location", "")
        event_id = event.get("id", "")
        event_start = event.get("start", {}).get("dateTime", "")

        if not title or not event_start:
            return None

        adhkar = await self.classify_and_get_adhkar(title, description, location)
        if not adhkar:
            return None

        try:
            result = calendar_service.create_adhkar_event(
                service=service,
                calendar_id=calendar_id,
                adhkar_title=adhkar.title,
                adhkar_text=adhkar.text,
                source=adhkar.source,
                original_event_id=event_id,
                event_start=event_start,
                category=adhkar.category,
                timezone=timezone,
                offset_minutes=offset_minutes,
            )
            return result
        except Exception as e:
            print(f"⚠️ فشل حقن الذكر للحدث '{title}': {e}")
            return None

adhkar_injector = AdhkarInjector()
