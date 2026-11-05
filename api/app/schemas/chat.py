from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserRead
from app.schemas.pin import PinRead


class MessageCreate(BaseModel):
    recipient_id: int
    body: str
    pin_id: Optional[int] = None


class MessageRead(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    body: str
    pin_id: Optional[int] = None
    pin: Optional[PinRead] = None
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationRead(BaseModel):
    user: UserRead
    last_message: MessageRead
    unread_count: int

