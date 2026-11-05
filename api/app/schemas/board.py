from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserRead
from app.schemas.pin import PinRead


class BoardCreate(BaseModel):
    title: str
    description: Optional[str] = None
    is_public: bool = True


class BoardRead(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    is_public: bool
    created_at: datetime
    pins_count: int = 0
    cover_images: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class BoardDetailRead(BoardRead):
    user: Optional[UserRead] = None
    pins: List[PinRead] = []

