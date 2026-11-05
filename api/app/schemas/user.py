from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class GoogleAuthRequest(BaseModel):
    id_token: str


class UserRead(BaseModel):
    id: int
    email: str
    username: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    access_token: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    username: Optional[str] = Field(None, min_length=3, max_length=30, pattern="^[a-zA-Z0-9_]+$")
    avatar_url: Optional[str] = None


class UserProfileRead(UserRead):
    pins_count: int = 0
    boards_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False
