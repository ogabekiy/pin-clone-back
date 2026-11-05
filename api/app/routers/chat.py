from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models.message import Message
from app.models.pin import Pin
from app.models.user import User
from app.schemas.chat import ConversationRead, MessageCreate, MessageRead
from app.schemas.user import UserRead

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns total number of unread messages for current user."""
    stmt = (
        select(func.count(Message.id))
        .where(Message.recipient_id == current_user.id, Message.is_read == False)
    )
    res = await db.execute(stmt)
    count = res.scalar() or 0
    return {"unread_count": count}


@router.get("/search-users", response_model=List[UserRead])
async def search_users_for_chat(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Searches other users to start a new chat conversation."""
    search_pattern = f"%{q.strip().lower()}%"
    stmt = (
        select(User)
        .where(
            User.id != current_user.id,
            or_(
                func.lower(User.username).like(search_pattern),
                func.lower(User.name).like(search_pattern),
            ),
        )
        .limit(10)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/conversations", response_model=List[ConversationRead])
async def get_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns list of active chat conversations with last message and unread count."""
    # 1. Find all messages involving current user
    stmt = (
        select(Message)
        .options(selectinload(Message.pin))
        .where(
            or_(
                Message.sender_id == current_user.id,
                Message.recipient_id == current_user.id,
            )
        )
        .order_by(desc(Message.created_at))
    )
    result = await db.execute(stmt)
    all_msgs = result.scalars().all()

    # 2. Group by partner ID
    conversations_map = {}
    unread_counts = {}
    partner_ids = []

    for msg in all_msgs:
        partner_id = msg.recipient_id if msg.sender_id == current_user.id else msg.sender_id

        if partner_id not in partner_ids:
            partner_ids.append(partner_id)
            conversations_map[partner_id] = msg

        if msg.recipient_id == current_user.id and not msg.is_read:
            unread_counts[partner_id] = unread_counts.get(partner_id, 0) + 1

    if not partner_ids:
        return []

    # 3. Load partner users
    users_stmt = select(User).where(User.id.in_(partner_ids))
    users_res = await db.execute(users_stmt)
    users_by_id = {u.id: u for u in users_res.scalars().all()}

    # 4. Assemble response ordered by last message time
    output = []
    for pid in partner_ids:
        partner_user = users_by_id.get(pid)
        if partner_user:
            last_msg = conversations_map[pid]
            output.append(
                ConversationRead(
                    user=partner_user,
                    last_message=last_msg,
                    unread_count=unread_counts.get(pid, 0),
                )
            )

    return output


@router.get("/messages/{other_user_id}", response_model=List[MessageRead])
async def get_chat_messages(
    other_user_id: int,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns messages in a dialogue and marks incoming messages as read."""
    # 1. Fetch messages
    stmt = (
        select(Message)
        .options(selectinload(Message.pin))
        .where(
            or_(
                (Message.sender_id == current_user.id) & (Message.recipient_id == other_user_id),
                (Message.sender_id == other_user_id) & (Message.recipient_id == current_user.id),
            )
        )
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = list(result.scalars().all())

    # 2. Mark incoming messages as read
    mark_stmt = (
        update(Message)
        .where(
            Message.sender_id == other_user_id,
            Message.recipient_id == current_user.id,
            Message.is_read == False,
        )
        .values(is_read=True)
    )
    await db.execute(mark_stmt)
    await db.commit()

    return messages


@router.post("/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sends a new chat message to another user."""
    if payload.recipient_id == current_user.id:
        raise HTTPException(status_code=400, detail="O'zingizga xabar yubora olmaysiz")

    # Check recipient exists
    rec_stmt = select(User).where(User.id == payload.recipient_id)
    rec_res = await db.execute(rec_stmt)
    if not rec_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Qabul qiluvchi foydalanuvchi topilmadi")

    # If pin_id provided, verify pin exists
    if payload.pin_id:
        p_stmt = select(Pin).where(Pin.id == payload.pin_id)
        p_res = await db.execute(p_stmt)
        if not p_res.scalar_one_or_none():
            payload.pin_id = None

    message = Message(
        sender_id=current_user.id,
        recipient_id=payload.recipient_id,
        body=payload.body.strip(),
        pin_id=payload.pin_id,
        is_read=False,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Preload pin relation if attached
    if message.pin_id:
        msg_stmt = (
            select(Message)
            .options(selectinload(Message.pin))
            .where(Message.id == message.id)
        )
        msg_res = await db.execute(msg_stmt)
        message = msg_res.scalar_one()

    return message

