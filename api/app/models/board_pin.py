from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.board import Board
    from app.models.pin import Pin


class BoardPin(Base):
    __tablename__ = "board_pins"

    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("boards.id", ondelete="CASCADE"), primary_key=True
    )
    pin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pins.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    board: Mapped["Board"] = relationship("Board", back_populates="board_pins")
    pin: Mapped["Pin"] = relationship("Pin", back_populates="board_pins")

    __table_args__ = (
        PrimaryKeyConstraint("board_id", "pin_id"),
        Index("board_pins_pin_idx", "pin_id"),
    )

