"""
مسارات المصادقة — Google OAuth 2.0
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.api.dependencies import get_current_user

# Frontend URL for OAuth redirect
FRONTEND_ORIGIN = settings.FRONTEND_URL.rstrip("/")

router = APIRouter(prefix="/auth", tags=["المصادقة"])

# ── Google OAuth URLs ──
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


@router.get("/login")
async def login():
    """توجيه المستخدم إلى صفحة تسجيل الدخول في Google"""
    scope = " ".join(SCOPES)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return {"auth_url": f"{GOOGLE_AUTH_URL}?{query}"}


@router.get("/callback")
async def callback(code: str, db: AsyncSession = Depends(get_db)):
    """
    استقبال الـ callback من Google بعد المصادقة
    → تبادل الكود بالتوكنات → حفظ/تحديث المستخدم
    """
    # تبادل الكود بالتوكنات
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="فشل تبادل الكود بالتوكنات")

    tokens = token_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # جلب بيانات المستخدم
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if user_response.status_code != 200:
        raise HTTPException(status_code=400, detail="فشل جلب بيانات المستخدم")

    user_info = user_response.json()
    google_id = user_info["id"]
    email = user_info["email"]
    name = user_info.get("name", "")
    picture = user_info.get("picture", "")

    # البحث عن المستخدم أو إنشاء جديد
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if user:
        user.access_token = access_token
        if refresh_token:
            user.refresh_token = refresh_token
        user.token_expiry = token_expiry
        user.name = name
        user.picture_url = picture
    else:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            picture_url=picture,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
        )
        db.add(user)

    await db.flush()

    # توجيه المستخدم مرة أخرى إلى الموقع مع التوكن
    params = urlencode({
        "token": access_token,
        "name": name,
        "email": email,
        "auto_sync": str(user.auto_sync_enabled).lower(),
    })
    return RedirectResponse(url=f"{FRONTEND_ORIGIN}/?{params}")


@router.post("/refresh")
async def refresh_token(db: AsyncSession = Depends(get_db)):
    """تجديد التوكن تلقائياً باستخدام refresh_token"""
    # يُستدعى من الـ scheduler عند اقتراب انتهاء الصلاحية
    result = await db.execute(
        select(User).where(User.is_active == True, User.refresh_token.isnot(None))
    )
    users = result.scalars().all()
    refreshed = 0

    for user in users:
        if not user.refresh_token:
            continue

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": user.refresh_token,
                        "grant_type": "refresh_token",
                    },
                )

            if resp.status_code == 200:
                data = resp.json()
                user.access_token = data["access_token"]
                user.token_expiry = datetime.now(timezone.utc) + timedelta(
                    seconds=data.get("expires_in", 3600)
                )
                refreshed += 1
        except Exception as e:
            print(f"⚠️ فشل تجديد توكن المستخدم {user.email}: {e}")
    await db.commit()
    return {"status": "success", "refreshed_count": refreshed}

@router.post("/auto-sync")
async def toggle_auto_sync(enabled: bool, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """تفعيل أو تعطيل المزامنة التلقائية (كل أسبوع)"""
    user.auto_sync_enabled = enabled
    await db.commit()
    return {"status": "success", "auto_sync_enabled": enabled}


