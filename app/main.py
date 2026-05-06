"""
أرحنا بها — نقطة الدخول الرئيسية
المساعد الديني الذكي للتقويم
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.scheduler import setup_scheduler, scheduler
from app.api.routes import auth, prayer, adhkar

# مسار الملفات الثابتة (HTML/CSS/JS)
FRONTEND_DIR = Path(__file__).parent.parent.parent  # ArihnaBiha/


@asynccontextmanager
async def lifespan(app: FastAPI):
    """دورة حياة التطبيق: بدء → تشغيل → إيقاف"""
    # ── عند البدء ──
    print(f"🌙 بسم الله — تشغيل {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # ── Migration ──
    import sqlite3
    try:
        conn = sqlite3.connect(FRONTEND_DIR / "arihna-biha-backend" / "arihna_biha.db")
        conn.execute("ALTER TABLE users ADD COLUMN auto_sync_enabled BOOLEAN DEFAULT 0;")
        conn.commit()
        conn.close()
        print("✅ تمت إضافة عمود auto_sync_enabled بنجاح.")
    except Exception as e:
        pass # Probably already exists
        
    await init_db()
    setup_scheduler()
    yield
    # ── عند الإيقاف ──
    scheduler.shutdown()
    print("🌙 تم إيقاف التطبيق")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="نظام ذكي يربط Google Calendar بأوقات الصلاة والأذكار المناسبة",
    lifespan=lifespan,
)

# ── CORS — السماح لكل المنافذ المحلية ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── المسارات (API) ──
app.include_router(auth.router)
app.include_router(prayer.router)
app.include_router(adhkar.router)


@app.get("/", tags=["الرئيسية"])
async def root():
    """يقدّم الموقع مباشرة من الـ backend"""
    html_file = FRONTEND_DIR / "arihna-biha.html"
    if html_file.exists():
        return FileResponse(html_file, media_type="text/html")
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "يعمل ✅",
        "docs": "/docs",
    }


@app.get("/health", tags=["الرئيسية"])
async def health():
    return {"status": "healthy"}
