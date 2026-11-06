from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_admin, get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.board import Board
from app.models.comment import Comment
from app.models.like import Like
from app.models.pin import Pin
from app.models.user import User
from app.schemas.admin import (
    AdminCommentItem,
    AdminCreateUserRequest,
    AdminLoginRequest,
    AdminPinItem,
    AdminPinsResponse,
    AdminSetupRequest,
    AdminSetupStatusResponse,
    AdminStatsResponse,
    AdminUserItem,
    AdminUserUpdateRole,
    AdminUserUpdateStatus,
)
from app.schemas.user import UserRead
from app.services.storage import delete_r2_object

router = APIRouter(prefix="/admin", tags=["admin"])


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def _ensure_admin_columns(db: AsyncSession):
    """Self-healing: ensure users table has role, is_blocked, password_hash columns."""
    try:
        await db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user';"))
        await db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;"))
        await db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;"))
        await db.execute(text("ALTER TABLE users ALTER COLUMN google_id DROP NOT NULL;"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS ix_users_is_blocked ON users (is_blocked);"))
        await db.commit()
    except Exception:
        await db.rollback()


@router.get("/setup-status", response_model=AdminSetupStatusResponse)
async def check_setup_status(db: AsyncSession = Depends(get_db)):
    """Check if at least one admin exists in the system."""
    try:
        stmt = select(func.count(User.id)).where(User.role == "admin")
        result = await db.execute(stmt)
        admin_count = result.scalar() or 0
        return AdminSetupStatusResponse(has_admin=admin_count > 0)
    except Exception:
        await db.rollback()
        await _ensure_admin_columns(db)
        try:
            stmt = select(func.count(User.id)).where(User.role == "admin")
            result = await db.execute(stmt)
            admin_count = result.scalar() or 0
            return AdminSetupStatusResponse(has_admin=admin_count > 0)
        except Exception:
            return AdminSetupStatusResponse(has_admin=False)


@router.post("/setup", response_model=UserRead)
async def setup_initial_admin(
    payload: AdminSetupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Initial system bootstrap: the very first admin registered in the system."""
    await _ensure_admin_columns(db)

    try:
        stmt = select(func.count(User.id)).where(User.role == "admin")
        result = await db.execute(stmt)
        admin_count = result.scalar() or 0
    except Exception:
        admin_count = 0

    if admin_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tizimda admin allaqachon mavjud. Yangi adminni mavjud admin o'z panelidan qo'shishi kerak.",
        )

    # Check if user with this email already exists
    clean_email = payload.email.strip().lower()
    existing_user_stmt = select(User).where(User.email == clean_email)
    existing_user_res = await db.execute(existing_user_stmt)
    existing_user = existing_user_res.scalar_one_or_none()

    if existing_user:
        # Promote existing user to admin and set password
        existing_user.role = "admin"
        existing_user.is_blocked = False
        existing_user.password_hash = get_password_hash(payload.password)
        if payload.name:
            existing_user.name = payload.name
        user = existing_user
    else:
        # Generate clean username
        base_username = clean_email.split("@")[0]
        clean_username = "".join(c for c in base_username if c.isalnum() or c == "_") or "superadmin"
        username = clean_username
        suffix = 1
        while True:
            u_check = await db.execute(select(User).where(User.username == username))
            if not u_check.scalar_one_or_none():
                break
            username = f"{clean_username}_{suffix}"
            suffix += 1

        user = User(
            email=clean_email,
            username=username,
            name=payload.name.strip(),
            role="admin",
            is_blocked=False,
            password_hash=get_password_hash(payload.password),
            google_id=f"admin_{clean_email}",
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "role": "admin"})
    _set_auth_cookie(response, token)

    user_dict = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "is_blocked": user.is_blocked,
        "created_at": user.created_at,
        "access_token": token,
    }
    return UserRead(**user_dict)


@router.post("/login", response_model=UserRead)
async def admin_login(
    payload: AdminLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate admin using email and password."""
    await _ensure_admin_columns(db)
    clean_email = payload.email.strip().lower()
    stmt = select(User).where(User.email == clean_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email yoki parol noto'g'ri",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email yoki parol noto'g'ri",
        )

    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin paneliga faqat admin huquqiga ega foydalanuvchilar kira oladi",
        )

    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ushbu hisob bloklangan",
        )

    token = create_access_token({"sub": str(user.id), "role": "admin"})
    _set_auth_cookie(response, token)

    user_dict = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "is_blocked": user.is_blocked,
        "created_at": user.created_at,
        "access_token": token,
    }
    return UserRead(**user_dict)


@router.get("/me", response_model=UserRead)
async def get_admin_me(
    admin: User = Depends(get_current_admin),
):
    """Get current authenticated admin info."""
    user_dict = {
        "id": admin.id,
        "email": admin.email,
        "username": admin.username,
        "name": admin.name,
        "avatar_url": admin.avatar_url,
        "role": admin.role,
        "is_blocked": admin.is_blocked,
        "created_at": admin.created_at,
    }
    return UserRead(**user_dict)


@router.get("/stats", response_model=AdminStatsResponse)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Overall system statistics for admin dashboard."""
    total_users_res = await db.execute(select(func.count(User.id)))
    total_users = total_users_res.scalar() or 0

    total_admins_res = await db.execute(select(func.count(User.id)).where(User.role == "admin"))
    total_admins = total_admins_res.scalar() or 0

    total_blocked_res = await db.execute(select(func.count(User.id)).where(User.is_blocked.is_(True)))
    total_blocked = total_blocked_res.scalar() or 0

    total_pins_res = await db.execute(select(func.count(Pin.id)))
    total_pins = total_pins_res.scalar() or 0

    total_boards_res = await db.execute(select(func.count(Board.id)))
    total_boards = total_boards_res.scalar() or 0

    total_comments_res = await db.execute(select(func.count(Comment.id)))
    total_comments = total_comments_res.scalar() or 0

    return AdminStatsResponse(
        total_users=total_users,
        total_admins=total_admins,
        total_blocked=total_blocked,
        total_pins=total_pins,
        total_boards=total_boards,
        total_comments=total_comments,
    )


@router.get("/users", response_model=List[AdminUserItem])
async def list_users(
    q: Optional[str] = Query(None, description="Search by name, email, or username"),
    role: Optional[str] = Query(None, description="Filter by role: admin or user"),
    is_blocked: Optional[bool] = Query(None, description="Filter by blocked status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """List users with search, filtering, and stats."""
    # Subqueries for pin & board counts
    pins_count_sub = (
        select(func.count(Pin.id))
        .where(Pin.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    boards_count_sub = (
        select(func.count(Board.id))
        .where(Board.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )

    query = select(
        User,
        pins_count_sub.label("pins_count"),
        boards_count_sub.label("boards_count"),
    )

    if q:
        search_pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(User.name).ilike(search_pattern),
                func.lower(User.email).ilike(search_pattern),
                func.lower(User.username).ilike(search_pattern),
            )
        )

    if role:
        query = query.where(User.role == role)

    if is_blocked is not None:
        query = query.where(User.is_blocked == is_blocked)

    query = query.order_by(desc(User.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)

    items = []
    for row in result.all():
        u = row[0]
        pins_cnt = row[1] or 0
        boards_cnt = row[2] or 0
        items.append(
            AdminUserItem(
                id=u.id,
                email=u.email,
                username=u.username,
                name=u.name,
                avatar_url=u.avatar_url,
                role=u.role,
                is_blocked=u.is_blocked,
                created_at=u.created_at,
                pins_count=pins_cnt,
                boards_count=boards_cnt,
            )
        )
    return items


@router.post("/users", response_model=AdminUserItem)
async def create_user_or_admin(
    payload: AdminCreateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Existing admin creates a new user or administrator."""
    clean_email = payload.email.strip().lower()
    existing_user_stmt = select(User).where(User.email == clean_email)
    existing_user_res = await db.execute(existing_user_stmt)
    if existing_user_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ushbu email bilan foydalanuvchi allaqachon mavjud",
        )

    base_username = clean_email.split("@")[0]
    clean_username = "".join(c for c in base_username if c.isalnum() or c == "_") or "user"
    username = clean_username
    suffix = 1
    while True:
        u_check = await db.execute(select(User).where(User.username == username))
        if not u_check.scalar_one_or_none():
            break
        username = f"{clean_username}_{suffix}"
        suffix += 1

    new_user = User(
        email=clean_email,
        username=username,
        name=payload.name.strip(),
        role=payload.role,
        is_blocked=False,
        password_hash=get_password_hash(payload.password),
        google_id=f"created_{clean_email}",
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return AdminUserItem(
        id=new_user.id,
        email=new_user.email,
        username=new_user.username,
        name=new_user.name,
        avatar_url=new_user.avatar_url,
        role=new_user.role,
        is_blocked=new_user.is_blocked,
        created_at=new_user.created_at,
        pins_count=0,
        boards_count=0,
    )


@router.patch("/users/{user_id}/block", response_model=AdminUserItem)
async def toggle_user_block(
    user_id: int,
    payload: AdminUserUpdateStatus,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Block or unblock a user."""
    if admin.id == user_id and payload.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin o'zini o'zi bloklay olmaydi",
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foydalanuvchi topilmadi",
        )

    target_user.is_blocked = payload.is_blocked
    await db.commit()
    await db.refresh(target_user)

    pins_cnt = (await db.execute(select(func.count(Pin.id)).where(Pin.user_id == target_user.id))).scalar() or 0
    boards_cnt = (await db.execute(select(func.count(Board.id)).where(Board.user_id == target_user.id))).scalar() or 0

    return AdminUserItem(
        id=target_user.id,
        email=target_user.email,
        username=target_user.username,
        name=target_user.name,
        avatar_url=target_user.avatar_url,
        role=target_user.role,
        is_blocked=target_user.is_blocked,
        created_at=target_user.created_at,
        pins_count=pins_cnt,
        boards_count=boards_cnt,
    )


@router.patch("/users/{user_id}/role", response_model=AdminUserItem)
async def change_user_role(
    user_id: int,
    payload: AdminUserUpdateRole,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Promote user to admin or demote to standard user."""
    if admin.id == user_id and payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin o'zining admin huquqini bekor qila olmaydi",
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foydalanuvchi topilmadi",
        )

    target_user.role = payload.role
    await db.commit()
    await db.refresh(target_user)

    pins_cnt = (await db.execute(select(func.count(Pin.id)).where(Pin.user_id == target_user.id))).scalar() or 0
    boards_cnt = (await db.execute(select(func.count(Board.id)).where(Board.user_id == target_user.id))).scalar() or 0

    return AdminUserItem(
        id=target_user.id,
        email=target_user.email,
        username=target_user.username,
        name=target_user.name,
        avatar_url=target_user.avatar_url,
        role=target_user.role,
        is_blocked=target_user.is_blocked,
        created_at=target_user.created_at,
        pins_count=pins_cnt,
        boards_count=boards_cnt,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Delete a user, cascading their pins, boards, comments, likes, and files."""
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin o'zini o'zi o'chira olmaydi",
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foydalanuvchi topilmadi",
        )

    # Clean up user's pin images from R2
    pins_stmt = select(Pin.image_key).where(Pin.user_id == user_id)
    pins_result = await db.execute(pins_stmt)
    for row in pins_result.all():
        image_key = row[0]
        if image_key:
            delete_r2_object(image_key)

    await db.delete(target_user)
    await db.commit()
    return {"message": "Foydalanuvchi va uning barcha ma'lumotlari muvaffaqiyatli o'chirildi"}


@router.get("/pins", response_model=AdminPinsResponse)
async def list_all_pins(
    q: Optional[str] = Query(None, description="Search pins by title or description"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """List all pins across all users with author details and total count."""
    likes_count_sub = (
        select(func.count(Like.user_id))
        .where(Like.pin_id == Pin.id)
        .correlate(Pin)
        .scalar_subquery()
    )
    comments_count_sub = (
        select(func.count(Comment.id))
        .where(Comment.pin_id == Pin.id)
        .correlate(Pin)
        .scalar_subquery()
    )

    base_filter = []
    if q:
        search_pattern = f"%{q.strip().lower()}%"
        base_filter.append(
            or_(
                func.lower(Pin.title).ilike(search_pattern),
                func.lower(Pin.description).ilike(search_pattern),
            )
        )

    if user_id:
        base_filter.append(Pin.user_id == user_id)

    # Count total matching pins
    count_query = select(func.count(Pin.id))
    if base_filter:
        count_query = count_query.where(*base_filter)
    total_res = await db.execute(count_query)
    total_count = total_res.scalar() or 0

    query = (
        select(
            Pin,
            User.name.label("user_name"),
            User.email.label("user_email"),
            User.avatar_url.label("user_avatar"),
            likes_count_sub.label("likes_count"),
            comments_count_sub.label("comments_count"),
        )
        .join(User, Pin.user_id == User.id)
    )

    if base_filter:
        query = query.where(*base_filter)

    query = query.order_by(desc(Pin.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)

    items = []
    for row in result.all():
        p = row[0]
        u_name = row[1]
        u_email = row[2]
        u_avatar = row[3]
        likes_cnt = row[4] or 0
        comments_cnt = row[5] or 0

        items.append(
            AdminPinItem(
                id=p.id,
                title=p.title,
                description=p.description,
                image_url=p.image_url,
                image_key=p.image_key,
                width=p.width,
                height=p.height,
                views_count=getattr(p, "views_count", 0),
                likes_count=likes_cnt,
                comments_count=comments_cnt,
                created_at=p.created_at,
                user_id=p.user_id,
                user_name=u_name,
                user_email=u_email,
                user_avatar=u_avatar,
            )
        )
    return AdminPinsResponse(items=items, total=total_count)


@router.delete("/pins/{pin_id}")
async def delete_pin(
    pin_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin can delete any user's pin (removes file from R2 and removes from database)."""
    stmt = select(Pin).where(Pin.id == pin_id)
    result = await db.execute(stmt)
    pin = result.scalar_one_or_none()

    if not pin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pin topilmadi",
        )

    if pin.image_key:
        delete_r2_object(pin.image_key)

    await db.delete(pin)
    await db.commit()
    return {"message": "Pin muvaffaqiyatli o'chirildi"}


@router.get("/comments", response_model=List[AdminCommentItem])
async def list_recent_comments(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """List recent comments across all pins."""
    query = (
        select(
            Comment,
            User.name.label("user_name"),
            User.email.label("user_email"),
            User.avatar_url.label("user_avatar"),
            Pin.title.label("pin_title"),
            Pin.image_url.label("pin_image"),
        )
        .join(User, Comment.user_id == User.id)
        .outerjoin(Pin, Comment.pin_id == Pin.id)
        .order_by(desc(Comment.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)

    items = []
    for row in result.all():
        c = row[0]
        u_name = row[1]
        u_email = row[2]
        u_avatar = row[3]
        p_title = row[4]
        p_image = row[5]
        items.append(
            AdminCommentItem(
                id=c.id,
                pin_id=c.pin_id,
                user_id=c.user_id,
                user_name=u_name,
                user_email=u_email,
                user_avatar=u_avatar,
                pin_title=p_title,
                pin_image=p_image,
                text=c.body,
                created_at=c.created_at,
            )
        )
    return items


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin deletes an inappropriate or reported comment."""
    stmt = select(Comment).where(Comment.id == comment_id)
    result = await db.execute(stmt)
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Izoh topilmadi",
        )

    await db.delete(comment)
    await db.commit()
    return {"message": "Izoh muvaffaqiyatli o'chirildi"}

