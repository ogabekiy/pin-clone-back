from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, DateTime, ForeignKey, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.pin import Pin


class Like(Base):
    __tablename__ = "likes"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    pin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pins.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="likes")
    pin: Mapped["Pin"] = relationship("Pin", back_populates="likes")

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "pin_id"),
    )

