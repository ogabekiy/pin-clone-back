from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AdminSetupStatusResponse(BaseModel):
    has_admin: bool


class AdminSetupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)


class AdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str


class AdminCreateUserRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field("admin", pattern="^(admin|user)$")


class AdminUserUpdateStatus(BaseModel):
    is_blocked: bool


class AdminUserUpdateRole(BaseModel):
    role: str = Field(..., pattern="^(admin|user)$")


class AdminStatsResponse(BaseModel):
    total_users: int
    total_admins: int
    total_blocked: int
    total_pins: int
    total_boards: int
    total_comments: int


class AdminUserItem(BaseModel):
    id: int
    email: str
    username: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    is_blocked: bool
    created_at: datetime
    pins_count: int = 0
    boards_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class AdminPinItem(BaseModel):
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: str
    image_key: str
    width: Optional[int] = None
    height: Optional[int] = None
    views_count: int = 0
    likes_count: int = 0
    comments_count: int = 0
    created_at: datetime
    user_id: int
    user_name: Optional[str] = None
    user_email: str
    user_avatar: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdminPinsResponse(BaseModel):
    items: List[AdminPinItem]
    total: int

    model_config = ConfigDict(from_attributes=True)


class AdminCommentItem(BaseModel):
    id: int
    pin_id: int
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    user_avatar: Optional[str] = None
    pin_title: Optional[str] = None
    pin_image: Optional[str] = None
    text: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
