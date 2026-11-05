from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, get_optional_current_user
from app.models.board_pin import BoardPin
from app.models.like import Like
from app.models.pin import Pin
from app.models.pin_view import PinView
from app.models.user import User
from app.schemas.pin import PinRead
from app.services.embedder_client import get_image_embedding, get_text_embedding
from app.services.vector_search import search_similar

router = APIRouter(tags=["search"])


@router.get("/search", response_model=List[PinRead])
async def search_by_text(
    q: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=60),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hybrid Search: Combines CLIP semantic visual vector similarity
    with lexical matching on Pin title and description.
    Most relevant results (exact/partial text matches + high visual similarity) appear first.
    """
    q_clean = q.strip().lower()
    tokens = [t for t in q_clean.split() if len(t) > 1]

    # 1. Fetch text candidate pins (title & description match)
    text_conditions = [
        Pin.title.ilike(f"%{q_clean}%"),
        Pin.description.ilike(f"%{q_clean}%"),
    ]
    for t in tokens:
        text_conditions.append(Pin.title.ilike(f"%{t}%"))
        text_conditions.append(Pin.description.ilike(f"%{t}%"))

    text_stmt = (
        select(Pin)
        .options(selectinload(Pin.user))
        .where(or_(*text_conditions))
        .limit(limit * 2)
    )
    text_res = await db.execute(text_stmt)
    text_candidates = list(text_res.scalars().all())

    # 2. Fetch vector candidate pins via CLIP text-to-image
    vec_map: dict[int, float] = {}  # pin_id -> distance
    vector_candidates: list[Pin] = []
    try:
        query_vector = await get_text_embedding(q)
        pairs = await search_similar(db=db, vector=query_vector, limit=limit * 2)
        for p, dist in pairs:
            vec_map[p.id] = dist
            vector_candidates.append(p)
    except Exception as e:
        print(f"[Search Warning] Embedder unavailable for text query: {e}")

    # 3. Combine unique candidates
    all_candidates: dict[int, Pin] = {}
    for p in text_candidates:
        all_candidates[p.id] = p
    for p in vector_candidates:
        all_candidates[p.id] = p

    # 4. Hybrid Scoring
    # Text relevance score (0.0 to 1.0)
    # Visual cosine similarity (0.0 to 1.0)
    scored: list[tuple[Pin, float]] = []
    for p_id, p in all_candidates.items():
        title_lower = (p.title or "").lower().strip()
        desc_lower = (p.description or "").lower().strip()

        # Text score
        t_score = 0.0
        if title_lower == q_clean:
            t_score = 1.0
        elif title_lower.startswith(q_clean):
            t_score = 0.85
        elif q_clean in title_lower:
            t_score = 0.75
        elif desc_lower and q_clean in desc_lower:
            t_score = 0.40
        elif tokens:
            t_matches = sum(1 for t in tokens if t in title_lower)
            d_matches = sum(1 for t in tokens if t in desc_lower)
            if t_matches or d_matches:
                t_score = min(0.65, (t_matches * 0.5 + d_matches * 0.25) / len(tokens))

        # Vector score
        if p_id in vec_map:
            v_sim = max(0.0, 1.0 - vec_map[p_id])
        else:
            v_sim = 0.0

        # Hybrid final score:
        # If title/description matches, give it top-tier priority (1.0 + text_score + v_sim)
        # Pins with matching text will always rank above pins with 0 text match,
        # and among them, those with higher visual similarity and exact title matches will rank highest!
        if t_score > 0:
            final_score = 1.0 + (t_score * 0.6) + (v_sim * 0.4)
        else:
            final_score = v_sim

        scored.append((p, final_score))

    # Sort descending by final score
    scored.sort(key=lambda x: x[1], reverse=True)
    pins = [p for p, _ in scored[:limit]]

    # 5. Populate likes and users
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


@router.post("/search/image", response_model=List[PinRead])
async def search_by_image(
    file: UploadFile = File(...),
    limit: int = Query(30, ge=1, le=60),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CLIP image-to-image visual vector search."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Bo'sh fayl yuklandi")

    try:
        # Get 512-dim embedding from image
        query_vector = await get_image_embedding(content, filename=file.filename or "search.jpg")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedder xizmati bilan bog'lanib bo'lmadi: {e}")

    # Vector search via vector_search.search_similar() (Rule 6)
    pairs = await search_similar(db=db, vector=query_vector, limit=limit)
    pins = [p for p, _ in pairs]

    for p in pins:
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
            likes_count=0,
            views_count=p.views_count,
            is_liked=False,
        )
        for p in pins
    ]


@router.get("/feed/personal", response_model=List[PinRead])
async def get_personal_feed(
    limit: int = Query(30, ge=1, le=60),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Personalized recommendation feed based on vectors of saved, liked, and viewed pins."""
    weighted_vectors: List[tuple[List[float], float]] = []

    # 1. Saved pins (weight 2.0)
    saved_pins_stmt = (
        select(Pin)
        .join(BoardPin, BoardPin.pin_id == Pin.id)
        .join(BoardPin.board)
        .where(BoardPin.board.has(user_id=current_user.id), Pin.embedding.is_not(None))
        .limit(15)
    )
    res = await db.execute(saved_pins_stmt)
    for p in res.scalars().all():
        if p.embedding and len(p.embedding) == 512:
            weighted_vectors.append((p.embedding, 2.0))

    # 2. Liked pins (weight 1.5)
    liked_pins_stmt = (
        select(Pin)
        .join(Like, Like.pin_id == Pin.id)
        .where(Like.user_id == current_user.id, Pin.embedding.is_not(None))
        .limit(15)
    )
    liked_res = await db.execute(liked_pins_stmt)
    for p in liked_res.scalars().all():
        if p.embedding and len(p.embedding) == 512:
            weighted_vectors.append((p.embedding, 1.5))

    # 3. Viewed pins - User actions tracking (weight 1.0)
    viewed_pins_stmt = (
        select(Pin)
        .join(PinView, PinView.pin_id == Pin.id)
        .where(PinView.user_id == current_user.id, Pin.embedding.is_not(None))
        .order_by(PinView.viewed_at.desc())
        .limit(25)
    )
    viewed_res = await db.execute(viewed_pins_stmt)
    for p in viewed_res.scalars().all():
        if p.embedding and len(p.embedding) == 512:
            weighted_vectors.append((p.embedding, 1.0))

    # If no interactions/views yet, fallback to general feed
    if not weighted_vectors:
        general_stmt = (
            select(Pin)
            .options(selectinload(Pin.user))
            .order_by(Pin.id.desc())
            .limit(limit)
        )
        g_res = await db.execute(general_stmt)
        general_pins = g_res.scalars().all()
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
                is_liked=False,
            )
            for p in general_pins
        ]

    # Calculate weighted average vector
    dim = 512
    avg_vector = [0.0] * dim
    total_weight = 0.0

    for vec, weight in weighted_vectors:
        for i in range(dim):
            avg_vector[i] += vec[i] * weight
        total_weight += weight

    if total_weight > 0:
        for i in range(dim):
            avg_vector[i] /= total_weight
        # Normalize to unit length
        norm = sum(x * x for x in avg_vector) ** 0.5
        if norm > 0:
            avg_vector = [x / norm for x in avg_vector]

    # Vector search using search_similar (Rule 6)
    pairs = await search_similar(db=db, vector=avg_vector, limit=limit)
    pins = [p for p, _ in pairs]

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
            likes_count=0,
            views_count=p.views_count,
            is_liked=False,
        )
        for p in pins
    ]

