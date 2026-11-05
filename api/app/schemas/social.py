from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserRead


class CommentCreate(BaseModel):
    body: str


class CommentRead(BaseModel):
    id: int
    pin_id: int
    user_id: int
    body: str
    created_at: datetime
    user: Optional[UserRead] = None

    model_config = ConfigDict(from_attributes=True)


class LikeToggleResponse(BaseModel):
    liked: bool
    likes_count: int


class FollowToggleResponse(BaseModel):
    following: bool
    followers_count: int

