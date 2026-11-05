import time
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, get_optional_current_user
from app.models.board_pin import BoardPin
from app.models.comment import Comment
from app.models.like import Like
from app.models.pin import Pin
from app.models.pin_view import PinView
from app.models.user import User
from app.schemas.pin import (
    PaginatedPinsResponse,
    PinCreate,
    PinDetailRead,
    PinRead,
    PresignedUrlRequest,
    PresignedUrlResponse,
)
from app.schemas.social import CommentCreate, CommentRead, LikeToggleResponse
from app.services.storage import create_presigned_upload_url, delete_r2_object
from app.services.vector_search import search_similar
from app.workers.embed_pin import process_pin_embedding

router = APIRouter(prefix="/pins", tags=["pins"])


@router.post("/upload-url", response_model=PresignedUrlResponse)
async def get_upload_url(
    payload: PresignedUrlRequest,
    current_user: User = Depends(get_current_user),
):
    """Generates presigned URL for direct upload to R2."""
    data = create_presigned_upload_url(
        content_type=payload.content_type,
        file_extension=payload.file_extension,
    )
    return data


@router.post("", response_model=PinRead, status_code=status.HTTP_201_CREATED)
async def create_pin(
    payload: PinCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new pin and queues asynchronous CLIP embedding task."""
    pin = Pin(
        user_id=current_user.id,
        image_key=payload.image_key,
        image_url=payload.image_url,
        title=payload.title,
        description=payload.description,
        link_url=payload.link_url,
        width=payload.width,
        height=payload.height,
        embed_status="pending",
    )
    db.add(pin)
    await db.commit()
    await db.refresh(pin)

    # Save to board if provided
    if payload.board_id:
        board_pin = BoardPin(board_id=payload.board_id, pin_id=pin.id)
        db.add(board_pin)
        await db.commit()

    # Rule 4: Embedding is handled in background
    background_tasks.add_task(process_pin_embedding, pin.id)

    # Load relation
    stmt = (
        select(Pin)
        .options(selectinload(Pin.user))
        .where(Pin.id == pin.id)
    )
    res = await db.execute(stmt)
    pin_loaded = res.scalar_one()

    return PinRead(
        id=pin_loaded.id,
        user_id=pin_loaded.user_id,
        image_key=pin_loaded.image_key,
        image_url=pin_loaded.image_url,
        width=pin_loaded.width,
        height=pin_loaded.height,
        title=pin_loaded.title,
        description=pin_loaded.description,
        link_url=pin_loaded.link_url,
        embed_status=pin_loaded.embed_status,
        created_at=pin_loaded.created_at,
        user=pin_loaded.user,
        likes_count=0,
        views_count=0,
        is_liked=False,
    )


@router.get("", response_model=PaginatedPinsResponse)
async def get_pins_feed(
    cursor: Optional[int] = Query(None, description="Cursor for pagination (last seen pin ID)"),
    limit: int = Query(20, ge=1, le=50),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cursor-based paginated general feed."""
    stmt = (
        select(Pin)
        .options(selectinload(Pin.user))
        .order_by(desc(Pin.id))
        .limit(limit + 1)
    )
    if cursor is not None:
        stmt = stmt.where(Pin.id < cursor)

    result = await db.execute(stmt)
    pins = list(result.scalars().all())

    has_more = len(pins) > limit
    if has_more:
        pins = pins[:limit]

    next_cursor = pins[-1].id if pins and has_more else None

    # Get likes data for these pins
    pin_ids = [p.id for p in pins]
    likes_count_map = {}
    user_liked_set = set()

    if pin_ids:
        # Count likes
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

    items = [
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

    return PaginatedPinsResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{pin_id}", response_model=PinDetailRead)
async def get_pin(
    pin_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns pin details, like count, comment count, and saved board IDs."""
    stmt = (
        select(Pin)
        .options(selectinload(Pin.user))
        .where(Pin.id == pin_id)
    )
    result = await db.execute(stmt)
    pin = result.scalar_one_or_none()

    if not pin:
        raise HTTPException(status_code=404, detail="Pin topilmadi")

    # Likes count & is_liked
    likes_count_res = await db.execute(
        select(func.count(Like.user_id)).where(Like.pin_id == pin_id)
    )
    likes_count = likes_count_res.scalar() or 0

    is_liked = False
    if current_user:
        user_like_res = await db.execute(
            select(Like).where(Like.pin_id == pin_id, Like.user_id == current_user.id)
        )
        is_liked = user_like_res.scalar_one_or_none() is not None

    # Comments count
    comments_count_res = await db.execute(
        select(func.count(Comment.id)).where(Comment.pin_id == pin_id)
    )
    comments_count = comments_count_res.scalar() or 0

    # User saved board IDs
    board_ids = []
    if current_user:
        board_stmt = (
            select(BoardPin.board_id)
            .join(BoardPin.board)
            .where(BoardPin.pin_id == pin_id, BoardPin.board.has(user_id=current_user.id))
        )
        board_res = await db.execute(board_stmt)
        board_ids = list(board_res.scalars().all())

    return PinDetailRead(
        id=pin.id,
        user_id=pin.user_id,
        image_key=pin.image_key,
        image_url=pin.image_url,
        width=pin.width,
        height=pin.height,
        title=pin.title,
        description=pin.description,
        link_url=pin.link_url,
        embed_status=pin.embed_status,
        created_at=pin.created_at,
        user=pin.user,
        likes_count=likes_count,
        views_count=pin.views_count,
        is_liked=is_liked,
        comments_count=comments_count,
        board_ids=board_ids,
    )


@router.get("/{pin_id}/similar", response_model=List[PinRead])
async def get_similar_pins(
    pin_id: int,
    limit: int = Query(20, ge=1, le=50),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CLIP cosine distance based similar pins with graceful fallback."""
    stmt = select(Pin).where(Pin.id == pin_id)
    result = await db.execute(stmt)
    target_pin = result.scalar_one_or_none()

    if not target_pin:
        return []

    # If embedding exists, perform true CLIP vector similarity search (Rule 6)
    if target_pin.embedding:
        similar_pairs = await search_similar(
            db=db,
            vector=target_pin.embedding,
            limit=limit,
            exclude_pin_id=pin_id,
        )
        pins = [p for p, _ in similar_pairs]
    else:
        # Graceful fallback: If embedding is not yet computed, trigger background worker
        background_tasks.add_task(process_pin_embedding, pin_id)
        # Fetch other pins so the UI is not empty
        fallback_stmt = (
            select(Pin)
            .options(selectinload(Pin.user))
            .where(Pin.id != pin_id)
            .order_by(desc(Pin.id))
            .limit(limit)
        )
        fallback_res = await db.execute(fallback_stmt)
        pins = list(fallback_res.scalars().all())

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

    # Preload user
    for p in pins:
        if "user" not in p.__dict__:
            await db.refresh(p, ["user"])

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


_recent_views_cache: dict[tuple[str, int], float] = {}


@router.post("/{pin_id}/view", status_code=status.HTTP_200_OK)
async def record_pin_view(
    pin_id: int,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Records user viewing a pin for behavioral recommendation engine and view count (deduplicated)."""
    now = time.time()
    client_key = f"user_{current_user.id}" if current_user else f"ip_{request.client.host if request.client else 'anon'}"
    cache_key = (client_key, pin_id)

    # Clean old cache entries occasionally
    if len(_recent_views_cache) > 3000:
        cutoff = now - 60
        expired = [k for k, v in _recent_views_cache.items() if v < cutoff]
        for k in expired:
            _recent_views_cache.pop(k, None)

    # If viewed in the last 30 seconds, return current count without duplicate increment
    last_viewed = _recent_views_cache.get(cache_key)
    if last_viewed and (now - last_viewed) < 30.0:
        v_res = await db.execute(select(Pin.views_count).where(Pin.id == pin_id))
        return {"status": "ok", "views_count": v_res.scalar() or 0}

    _recent_views_cache[cache_key] = now

    # Increment views_count
    await db.execute(
        update(Pin).where(Pin.id == pin_id).values(views_count=Pin.views_count + 1)
    )
    if current_user:
        view = PinView(user_id=current_user.id, pin_id=pin_id)
        db.add(view)
    await db.commit()

    # Get updated view count
    v_res = await db.execute(select(Pin.views_count).where(Pin.id == pin_id))
    current_views = v_res.scalar() or 0
    return {"status": "ok", "views_count": current_views}


@router.delete("/{pin_id}")
async def delete_pin(
    pin_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletes a pin (only owner can delete) and deletes image from R2."""
    stmt = select(Pin).where(Pin.id == pin_id)
    result = await db.execute(stmt)
    pin = result.scalar_one_or_none()

    if not pin:
        raise HTTPException(status_code=404, detail="Pin topilmadi")

    if pin.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu pinni o'chirishga ruxsat yo'q")

    # Delete from R2
    if pin.image_key:
        delete_r2_object(pin.image_key)

    await db.delete(pin)
    await db.commit()
    return {"message": "Pin muvaffaqiyatli o'chirildi"}


@router.post("/{pin_id}/like", response_model=LikeToggleResponse)
async def toggle_pin_like(
    pin_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggles like on a pin."""
    stmt = select(Like).where(Like.pin_id == pin_id, Like.user_id == current_user.id)
    result = await db.execute(stmt)
    like = result.scalar_one_or_none()

    if like:
        await db.delete(like)
        liked = False
    else:
        new_like = Like(pin_id=pin_id, user_id=current_user.id)
        db.add(new_like)
        liked = True

    await db.commit()

    likes_count_res = await db.execute(
        select(func.count(Like.user_id)).where(Like.pin_id == pin_id)
    )
    likes_count = likes_count_res.scalar() or 0

    return LikeToggleResponse(liked=liked, likes_count=likes_count)


@router.post("/{pin_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def add_comment(
    pin_id: int,
    payload: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adds a comment to a pin."""
    comment = Comment(
        pin_id=pin_id,
        user_id=current_user.id,
        body=payload.body,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return CommentRead(
        id=comment.id,
        pin_id=comment.pin_id,
        user_id=comment.user_id,
        body=comment.body,
        created_at=comment.created_at,
        user=current_user,
    )


@router.get("/{pin_id}/comments", response_model=List[CommentRead])
async def get_comments(
    pin_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Returns comments of a pin."""
    stmt = (
        select(Comment)
        .options(selectinload(Comment.user))
        .where(Comment.pin_id == pin_id)
        .order_by(Comment.created_at.asc())
    )
    result = await db.execute(stmt)
    comments = result.scalars().all()
    return comments

