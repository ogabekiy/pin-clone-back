from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, get_optional_current_user
from app.models.board import Board
from app.models.follow import Follow
from app.models.like import Like
from app.models.pin import Pin
from app.models.user import User
from app.schemas.board import BoardRead
from app.schemas.pin import PinRead
from app.schemas.social import FollowToggleResponse
from app.schemas.user import UserProfileRead, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserRead)
async def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates user's name, unique username, or avatar URL."""
    if payload.username is not None and payload.username != current_user.username:
        # Check unique username
        u_stmt = select(User).where(User.username == payload.username, User.id != current_user.id)
        res = await db.execute(u_stmt)
        if res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Bu username allaqachon band qilingan")
        current_user.username = payload.username.lower()

    if payload.name is not None:
        current_user.name = payload.name.strip()

    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url

    await db.commit()
    await db.refresh(current_user)
    return current_user


async def get_target_user(identifier: str, db: AsyncSession) -> User:
    """Finds user by numeric ID or unique username."""
    if identifier.isdigit():
        stmt = select(User).where((User.id == int(identifier)) | (User.username == identifier.lower()))
    else:
        stmt = select(User).where(User.username == identifier.lower())
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return user


@router.get("/{identifier}", response_model=UserProfileRead)
async def get_user_profile(
    identifier: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns user profile with statistics by ID or username."""
    user = await get_target_user(identifier, db)
    user_id = user.id

    # Counts
    pins_count_res = await db.execute(select(func.count(Pin.id)).where(Pin.user_id == user_id))
    pins_count = pins_count_res.scalar() or 0

    boards_count_res = await db.execute(select(func.count(Board.id)).where(Board.user_id == user_id))
    boards_count = boards_count_res.scalar() or 0

    followers_count_res = await db.execute(select(func.count(Follow.follower_id)).where(Follow.following_id == user_id))
    followers_count = followers_count_res.scalar() or 0

    following_count_res = await db.execute(select(func.count(Follow.following_id)).where(Follow.follower_id == user_id))
    following_count = following_count_res.scalar() or 0

    is_following = False
    if current_user and current_user.id != user_id:
        f_res = await db.execute(
            select(Follow).where(Follow.follower_id == current_user.id, Follow.following_id == user_id)
        )
        is_following = f_res.scalar_one_or_none() is not None

    return UserProfileRead(
        id=user.id,
        email=user.email,
        username=user.username,
        name=user.name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        pins_count=pins_count,
        boards_count=boards_count,
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following,
    )


@router.get("/{identifier}/pins", response_model=List[PinRead])
async def get_user_pins(
    identifier: str,
    limit: int = Query(30, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
):
    """Returns pins created by a user (by ID or username)."""
    user = await get_target_user(identifier, db)
    user_id = user.id

    stmt = (
        select(Pin)
        .options(selectinload(Pin.user))
        .where(Pin.user_id == user_id)
        .order_by(Pin.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    pins = result.scalars().all()

    return [
        PinRead(
            id=p.id,
            user_id=p.user_id,
            image_key=p.image_key,
            image_url=p.image_url,
            width=p.width,
            height=p.height,
            title=p.title,
            description=p.description,
            link_url=p.link_url,
            embed_status=p.embed_status,
            created_at=p.created_at,
            user=p.user,
            likes_count=0,
            views_count=p.views_count,
            is_liked=False,
        )
        for p in pins
    ]


@router.get("/{identifier}/likes", response_model=List[PinRead])
async def get_user_liked_pins(
    identifier: str,
    limit: int = Query(30, ge=1, le=60),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns pins liked by a user (by ID or username)."""
    user = await get_target_user(identifier, db)
    user_id = user.id

    stmt = (
        select(Pin)
        .join(Like, Like.pin_id == Pin.id)
        .options(selectinload(Pin.user))
        .where(Like.user_id == user_id)
        .order_by(Like.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    pins = list(result.scalars().all())

    pin_ids = [p.id for p in pins]
    likes_count_map = {}
    user_liked_set = set()

    if pin_ids:
        count_stmt = (
            select(Like.pin_id, func.count(Like.user_id))
            .where(Like.pin_id.in_(pin_ids))
            .group_by(Like.pin_id)
        )
        count_res = await db.execute(count_stmt)
        likes_count_map = dict(count_res.all())

        if current_user:
            user_likes_stmt = (
                select(Like.pin_id)
                .where(Like.pin_id.in_(pin_ids), Like.user_id == current_user.id)
            )
            user_likes_res = await db.execute(user_likes_stmt)
            user_liked_set = set(user_likes_res.scalars().all())

    return [
        PinRead(
            id=p.id,
            user_id=p.user_id,
            image_key=p.image_key,
            image_url=p.image_url,
            width=p.width,
            height=p.height,
            title=p.title,
            description=p.description,
            link_url=p.link_url,
            embed_status=p.embed_status,
            created_at=p.created_at,
            user=p.user,
            likes_count=likes_count_map.get(p.id, 0),
            views_count=p.views_count,
            is_liked=p.id in user_liked_set,
        )
        for p in pins
    ]


@router.post("/{identifier}/follow", response_model=FollowToggleResponse)
async def toggle_follow(
    identifier: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Follows or unfollows a user (by ID or username)."""
    target_user = await get_target_user(identifier, db)
    user_id = target_user.id

    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="O'zingizga obuna bo'la olmaysiz")

    stmt = select(Follow).where(Follow.follower_id == current_user.id, Follow.following_id == user_id)
    result = await db.execute(stmt)
    follow = result.scalar_one_or_none()

    if follow:
        await db.delete(follow)
        following = False
    else:
        new_follow = Follow(follower_id=current_user.id, following_id=user_id)
        db.add(new_follow)
        following = True

    await db.commit()

    followers_count_res = await db.execute(select(func.count(Follow.follower_id)).where(Follow.following_id == user_id))
    followers_count = followers_count_res.scalar() or 0

    return FollowToggleResponse(
        following=following,
        followers_count=followers_count,
    )
