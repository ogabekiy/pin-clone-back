from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, get_optional_current_user
from app.models.board import Board
from app.models.board_pin import BoardPin
from app.models.pin import Pin
from app.models.user import User
from app.schemas.board import BoardCreate, BoardDetailRead, BoardRead
from app.schemas.pin import PinRead

router = APIRouter(prefix="/boards", tags=["boards"])


@router.post("", response_model=BoardRead, status_code=status.HTTP_201_CREATED)
async def create_board(
    payload: BoardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new board."""
    board = Board(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        is_public=payload.is_public,
    )
    db.add(board)
    await db.commit()
    await db.refresh(board)

    return BoardRead(
        id=board.id,
        user_id=board.user_id,
        title=board.title,
        description=board.description,
        is_public=board.is_public,
        created_at=board.created_at,
        pins_count=0,
        cover_images=[],
    )


@router.get("/me", response_model=List[BoardRead])
async def get_my_boards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns boards belonging to the current user."""
    stmt = (
        select(Board)
        .where(Board.user_id == current_user.id)
        .order_by(Board.created_at.desc())
    )
    res = await db.execute(stmt)
    boards = res.scalars().all()

    result = []
    for b in boards:
        # Get count and previews
        pin_stmt = (
            select(Pin.image_url)
            .join(BoardPin, BoardPin.pin_id == Pin.id)
            .where(BoardPin.board_id == b.id)
            .order_by(BoardPin.saved_at.desc())
            .limit(3)
        )
        pins_res = await db.execute(pin_stmt)
        covers = list(pins_res.scalars().all())

        count_stmt = select(func.count(BoardPin.pin_id)).where(BoardPin.board_id == b.id)
        count_res = await db.execute(count_stmt)
        p_count = count_res.scalar() or 0

        result.append(
            BoardRead(
                id=b.id,
                user_id=b.user_id,
                title=b.title,
                description=b.description,
                is_public=b.is_public,
                created_at=b.created_at,
                pins_count=p_count,
                cover_images=covers,
            )
        )
    return result


@router.get("/{board_id}", response_model=BoardDetailRead)
async def get_board_detail(
    board_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns board details and its pins."""
    stmt = (
        select(Board)
        .options(selectinload(Board.user))
        .where(Board.id == board_id)
    )
    result = await db.execute(stmt)
    board = result.scalar_one_or_none()

    if not board:
        raise HTTPException(status_code=404, detail="Board topilmadi")

    # If private, only owner can view
    if not board.is_public and (not current_user or current_user.id != board.user_id):
        raise HTTPException(status_code=403, detail="Bu maxfiy board")

    # Fetch pins inside board
    pins_stmt = (
        select(Pin)
        .join(BoardPin, BoardPin.pin_id == Pin.id)
        .options(selectinload(Pin.user))
        .where(BoardPin.board_id == board_id)
        .order_by(BoardPin.saved_at.desc())
    )
    pins_res = await db.execute(pins_stmt)
    pins = list(pins_res.scalars().all())

    pin_reads = [
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
        for p in pins
    ]

    covers = [p.image_url for p in pins[:3]]

    return BoardDetailRead(
        id=board.id,
        user_id=board.user_id,
        title=board.title,
        description=board.description,
        is_public=board.is_public,
        created_at=board.created_at,
        pins_count=len(pins),
        cover_images=covers,
        user=board.user,
        pins=pin_reads,
    )


@router.post("/{board_id}/pins", status_code=status.HTTP_200_OK)
async def save_pin_to_board(
    board_id: int,
    pin_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saves a pin into a board."""
    # Check board ownership
    stmt = select(Board).where(Board.id == board_id, Board.user_id == current_user.id)
    result = await db.execute(stmt)
    board = result.scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=404, detail="Board topilmadi yoki sizga tegishli emas")

    # Check pin exists
    pin_stmt = select(Pin).where(Pin.id == pin_id)
    pin_res = await db.execute(pin_stmt)
    if not pin_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Pin topilmadi")

    # Check if already added
    exists_stmt = select(BoardPin).where(BoardPin.board_id == board_id, BoardPin.pin_id == pin_id)
    exists_res = await db.execute(exists_stmt)
    if exists_res.scalar_one_or_none():
        return {"message": "Pin bu boardga allaqachon saqlangan"}

    board_pin = BoardPin(board_id=board_id, pin_id=pin_id)
    db.add(board_pin)
    await db.commit()
    return {"message": "Pin muvaffaqiyatli saqlandi"}


@router.delete("/{board_id}/pins/{pin_id}")
async def remove_pin_from_board(
    board_id: int,
    pin_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Removes a pin from a board."""
    # Check board ownership
    stmt = select(Board).where(Board.id == board_id, Board.user_id == current_user.id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Board topilmadi yoki sizga tegishli emas")

    del_stmt = delete(BoardPin).where(BoardPin.board_id == board_id, BoardPin.pin_id == pin_id)
    await db.execute(del_stmt)
    await db.commit()
    return {"message": "Pin boarddan olib tashlandi"}

