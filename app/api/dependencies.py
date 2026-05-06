"""
Auth middleware و DB session dependencies
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    التحقق من هوية المستخدم عبر Google ID المُخزّن
    يُستخدم كـ Dependency في الـ routes المحمية
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="مطلوب تسجيل الدخول",
        )

    token = credentials.credentials

    # البحث عن المستخدم بالتوكن
    result = await db.execute(
        select(User).where(User.access_token == token, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="جلسة غير صالحة — الرجاء إعادة تسجيل الدخول",
        )

    # التحقق من انتهاء صلاحية التوكن
    if user.token_expiry and user.token_expiry.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="انتهت صلاحية الجلسة — الرجاء إعادة تسجيل الدخول",
        )

    return user
