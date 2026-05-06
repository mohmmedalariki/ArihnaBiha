"""
خدمة Gemini — تصنيف السياق فقط (لا يُولّد أي نص ديني)
يستخدم google-genai (المكتبة الجديدة)
⚡ Batch mode + Auto-retry on rate limit
"""
import asyncio
import re
from google import genai
from google.genai import types
from app.core.config import settings

# ── System Prompt الصارم لـ Gemini ──
CLASSIFICATION_SYSTEM_PROMPT = """أنت مصنّف أحداث تقويم فقط. مهمتك الوحيدة هي تحليل عنوان ووصف الحدث وإرجاع فئة واحدة فقط من القائمة أدناه.

القواعد الصارمة:
1. أَرجِع فئة واحدة فقط من القائمة — بدون أي نص إضافي
2. لا تُولّد أي نص ديني أو دعاء أو ذكر
3. لا تُضف شرحاً أو تعليقاً
4. إذا لم يتطابق الحدث مع أي فئة بوضوح، أرجع: general
5. الرد يكون كلمة واحدة فقط (الـ tag)

الفئات المتاحة:
- travel → سفر، رحلة، طيران، مطار، عطلة
- exam_success → امتحان، اختبار، دراسة، جامعة، مذاكرة، عرض تقديمي
- health_healing → طبيب، مستشفى، عملية، فحص، علاج، موعد طبي
- meeting → اجتماع، مقابلة عمل، مؤتمر، مكالمة عمل
- marriage → زواج، خطوبة، عرس، وليمة
- newborn → مولود، ولادة، حمل
- rain → مطر، عاصفة، رعد
- general_stress → قلق، ضغط، مشكلة، صعوبة
- friday → جمعة، خطبة الجمعة
- morning → صباح، بداية اليوم
- evening → مساء، نهاية اليوم
- sleep → نوم، راحة
- food → غداء، عشاء، فطور، مطعم، وجبة
- fasting → صيام، رمضان، إفطار، سحور
- hajj_umrah → حج، عمرة، مكة، المدينة
- anger → غضب، خلاف
- fear → خوف، فزع، خطر
- debt → دين، قرض، سداد، مالي
- leaving_home → خروج من المنزل
- entering_home → دخول المنزل، عودة
- mosque → مسجد، صلاة جماعة
- repentance → توبة، استغفار
- death_funeral → جنازة، وفاة، تعزية
- new_clothes → ملابس جديدة، تسوق
- general → أي حدث لا يتطابق مع الفئات أعلاه
"""

# الفئات المسموح بها
VALID_CATEGORIES = {
    "travel", "exam_success", "health_healing", "meeting", "marriage",
    "newborn", "rain", "general_stress", "friday", "morning", "evening",
    "sleep", "food", "fasting", "hajj_umrah", "anger", "fear", "debt",
    "leaving_home", "entering_home", "mosque", "repentance",
    "death_funeral", "new_clothes", "general",
}

MAX_RETRIES = 3


def _extract_retry_delay(error_msg: str) -> float:
    """استخراج مدة الانتظار من رسالة خطأ 429"""
    match = re.search(r"retry in (\d+\.?\d*)", str(error_msg), re.IGNORECASE)
    if match:
        return min(float(match.group(1)) + 2, 120)  # +2 ثانية أمان، حد أقصى 120
    return 60  # افتراضي: 60 ثانية


def _is_rate_limit_error(error: Exception) -> bool:
    """التحقق هل الخطأ هو تجاوز الحصة (429)"""
    return "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error)


class GeminiClassifier:
    """مصنّف الأحداث عبر Gemini — يُرجع tag فقط، مع إعادة محاولة تلقائية"""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def _call_gemini(self, contents: str, max_tokens: int = 20) -> str:
        """
        استدعاء Gemini مع إعادة محاولة تلقائية عند 429
        """
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=CLASSIFICATION_SYSTEM_PROMPT,
                        temperature=0.1,
                        max_output_tokens=max_tokens,
                        top_p=0.8,
                    ),
                )
                return response.text.strip()

            except Exception as e:
                if _is_rate_limit_error(e) and attempt < MAX_RETRIES - 1:
                    delay = _extract_retry_delay(str(e))
                    print(f"⏳ تجاوز الحصة (محاولة {attempt+1}/{MAX_RETRIES}) — انتظار {delay:.0f} ثانية...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise

        return ""

    async def classify_event(self, title: str, description: str = "") -> str:
        """تصنيف حدث واحد"""
        prompt = f"حدث: \"{title}\""
        if description:
            prompt += f"\nالوصف: \"{description}\""

        try:
            raw = await self._call_gemini(prompt)
            tag = raw.lower().replace('"', '').replace("'", "")
            if tag not in VALID_CATEGORIES:
                return "general"
            return tag
        except Exception as e:
            print(f"⚠️ فشل تصنيف Gemini نهائياً: {e}")
            return "general"

    async def classify_events_batch(self, events: list[dict]) -> dict[str, str]:
        """
        ⚡ تصنيف جميع الأحداث في طلب واحد (Batching + Auto-retry)

        Args:
            events: قائمة أحداث [{id, title, description}, ...]

        Returns:
            {event_id: category, ...}
        """
        if not events:
            return {}

        # بناء prompt واحد لكل الأحداث
        lines = []
        for i, ev in enumerate(events):
            title = ev.get("title", "")
            desc = ev.get("description", "")
            line = f"{i+1}. \"{title}\""
            if desc:
                line += f" — {desc[:80]}"
            lines.append(line)

        batch_prompt = (
            "صنّف كل حدث إلى فئة واحدة. أرجع رقم الحدث والفئة فقط بهذا الشكل:\n"
            "1:category\n2:category\n\nالأحداث:\n" + "\n".join(lines)
        )

        try:
            raw = await self._call_gemini(batch_prompt, max_tokens=500)

            # تحليل الرد: "1:travel\n2:meeting\n3:general"
            result = {}
            for line in raw.split("\n"):
                line = line.strip()
                if ":" not in line:
                    continue
                parts = line.split(":", 1)
                try:
                    idx = int(parts[0].strip()) - 1
                    tag = parts[1].strip().lower().replace('"', '').replace("'", "")
                    if 0 <= idx < len(events) and tag in VALID_CATEGORIES:
                        result[events[idx]["id"]] = tag
                except (ValueError, IndexError):
                    continue

            # ملء الأحداث التي لم تُصنَّف بـ general
            for ev in events:
                if ev["id"] not in result:
                    result[ev["id"]] = "general"

            print(f"✅ تصنيف {len(events)} أحداث في طلب واحد: {result}")
            return result

        except Exception as e:
            print(f"⚠️ فشل التصنيف الجماعي نهائياً: {e}")
            return {ev["id"]: "general" for ev in events}


gemini_classifier = GeminiClassifier()
