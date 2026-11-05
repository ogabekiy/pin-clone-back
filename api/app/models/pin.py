from datetime import datetime
from typing import TYPE_CHECKING, List
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, desc, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.board_pin import BoardPin
    from app.models.like import Like
    from app.models.comment import Comment


class Pin(Base):
    __tablename__ = "pins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_key: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[List[float] | None] = mapped_column(Vector(512), nullable=True)
    embed_status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)  # pending | done | failed
    views_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="pins")
    board_pins: Mapped[List["BoardPin"]] = relationship("BoardPin", back_populates="pin", cascade="all, delete-orphan")
    likes: Mapped[List["Like"]] = relationship("Like", back_populates="pin", cascade="all, delete-orphan")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="pin", cascade="all, delete-orphan")

    __table_args__ = (
        Index("pins_embedding_idx", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("pins_user_idx", "user_id", desc("created_at")),
    )

