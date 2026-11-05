from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import GoogleAuthRequest, UserRead
from app.services.google_auth import verify_google_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=UserRead)
async def auth_google(
    payload: GoogleAuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        user_info = verify_google_token(payload.id_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    google_id = user_info["google_id"]
    email = user_info.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google hisobida email topilmadi",
        )

    # Find user by google_id (Rule 8)
    stmt = select(User).where(User.google_id == google_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # Create unique username
        base_username = email.split("@")[0].lower()
        clean_username = "".join(c for c in base_username if c.isalnum() or c == "_")
        if not clean_username:
            clean_username = f"user_{google_id[:8]}"

        username = clean_username
        suffix = 1
        while True:
            u_check = await db.execute(select(User).where(User.username == username))
            if not u_check.scalar_one_or_none():
                break
            username = f"{clean_username}_{suffix}"
            suffix += 1

        # Create new user
        user = User(
            google_id=google_id,
            email=email,
            username=username,
            name=user_info.get("name"),
            avatar_url=user_info.get("avatar_url"),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Existing user: do NOT overwrite custom name or avatar if already set
        if not user.name:
            user.name = user_info.get("name")
        if not user.avatar_url:
            user.avatar_url = user_info.get("avatar_url")
        await db.commit()
        await db.refresh(user)

    # Issue JWT token
    token = create_access_token({"sub": str(user.id)})

    # Set httpOnly cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return user


@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        httponly=True,
        samesite="lax",
    )
    return {"message": "Muvaffaqiyatli chiqildi"}


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user

