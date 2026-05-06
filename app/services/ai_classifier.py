import json
import re
import unicodedata
from app.core.config import settings

class AIClassifier:
    """مصنّف الأحداث المحلي يعتمد على الكلمات المفتاحية (بديل للذكاء الاصطناعي)"""

    def __init__(self):
        DICT_PATH = settings.DATA_DIR / "keyword_matcher.json"
        with open(DICT_PATH, encoding="utf-8") as f:
            dictionary = json.load(f)
            self.categories = sorted(dictionary["categories"], key=lambda c: c["priority"])
            self.fallback = dictionary["fallback"]

    def strip_diacritics(self, text):
        return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

    def normalize_ar(self, text):
        text = self.strip_diacritics(text)
        for a, b in [("ى","ي"),("ة","ه"),("أ","ا"),("إ","ا"),("آ","ا"),("ؤ","و"),("ئ","ي")]:
            text = text.replace(a, b)
        return text

    def normalize_en(self, text):
        return text.lower()

    def tokenize(self, text):
        parts = re.split(r"[\s\-_/،,.·•|@#\(\)\[\]]+", text)
        return {p.strip() for p in parts if len(p.strip()) >= 2}

    def build_search(self, title, description, location):
        raw = f"{title} {description} {location}"
        ar_norm = self.normalize_ar(raw)
        en_norm = self.normalize_en(raw)
        combined = f"{ar_norm} {en_norm}"
        tokens = self.tokenize(combined)
        return combined, tokens

    def _match(self, keyword, combined, tokens):
        kw_ar = self.normalize_ar(keyword)
        kw_en = self.normalize_en(keyword)

        toks_ar = self.tokenize(kw_ar)
        toks_en = self.tokenize(kw_en)

        # single-token Arabic — exact token match (word boundary)
        if len(toks_ar) == 1:
            tok = next(iter(toks_ar))
            if tok in tokens:
                return True, "high"

        # single-token English — regex word boundary
        if len(toks_en) == 1:
            tok = next(iter(toks_en))
            if re.search(rf"\b{re.escape(tok)}\b", combined):
                return True, "high"

        # multi-token English phrase
        if len(toks_en) > 1:
            if re.search(rf"\b{re.escape(kw_en)}\b", combined):
                return True, "medium"

        # multi-token Arabic phrase
        if len(toks_ar) > 1:
            if kw_ar in combined:
                return True, "medium"

        return False, "none"

    async def classify_event(self, title: str, description: str = "", location: str = "") -> dict:
        combined, tokens = self.build_search(title, description, location)
        for cat in self.categories:
            for kw in cat.get("keywords_ar", []) + cat.get("keywords_en", []):
                matched, conf = self._match(kw, combined, tokens)
                if matched:
                    print(f"🔍 [Match] '{title}' -> {cat['dua_key']} (Keyword: {kw})")
                    return {
                        "category_id": cat["id"], 
                        "dua_key": cat["dua_key"],
                        "label_ar": cat["label_ar"], 
                        "label_en": cat["label_en"],
                        "matched_keyword": kw, 
                        "confidence": conf, 
                        "priority": cat["priority"]
                    }
        return {
            "category_id": self.fallback["id"], 
            "dua_key": self.fallback["dua_key"],
            "label_ar": self.fallback["label_ar"], 
            "label_en": self.fallback["label_en"],
            "matched_keyword": None, 
            "confidence": "fallback", 
            "priority": 999
        }

    async def classify_events_batch(self, events: list[dict]) -> dict[str, str]:
        result = {}
        for ev in events:
            ev_id = ev["id"]
            title = ev.get("title", "")
            desc = ev.get("description", "")
            loc = ev.get("location", "")
            cat_dict = await self.classify_event(title, desc, loc)
            result[ev_id] = cat_dict["dua_key"]
            
        print(f"✅ تم تصنيف {len(events)} أحداث محلياً بنجاح.")
        return result

ai_classifier = AIClassifier()
