from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserRead


class PresignedUrlRequest(BaseModel):
    content_type: str = "image/jpeg"
    file_extension: str = "jpg"


class PresignedUrlResponse(BaseModel):
    upload_url: str
    image_key: str
    image_url: str


class PinCreate(BaseModel):
    image_key: str
    image_url: str
    title: Optional[str] = None
    description: Optional[str] = None
    link_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    board_id: Optional[int] = None


class PinRead(BaseModel):
    id: int
    user_id: int
    image_key: str
    image_url: str
    width: Optional[int] = None
    height: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    link_url: Optional[str] = None
    embed_status: str
    created_at: datetime
    user: Optional[UserRead] = None
    likes_count: int = 0
    views_count: int = 0
    is_liked: bool = False

    model_config = ConfigDict(from_attributes=True)


class PinDetailRead(PinRead):
    comments_count: int = 0
    board_ids: List[int] = []


class PaginatedPinsResponse(BaseModel):
    items: List[PinRead]
    next_cursor: Optional[int] = None
    has_more: bool = False

