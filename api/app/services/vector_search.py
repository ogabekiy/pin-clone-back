from typing import List, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pin import Pin


async def search_similar(
    db: AsyncSession,
    vector: List[float],
    limit: int = 20,
    offset: int = 0,
    exclude_pin_id: int | None = None,
) -> List[Tuple[Pin, float]]:
    """
    Rule 5 & 6: Searches similar pins using cosine distance (<=>).
    All vector searches in the application MUST go through this function.
    Returns a list of (Pin, distance) tuples sorted by similarity.
    """
    distance_col = Pin.embedding.cosine_distance(vector).label("distance")
    stmt = (
        select(Pin, distance_col)
        .where(Pin.embedding.is_not(None))
    )

    if exclude_pin_id is not None:
        stmt = stmt.where(Pin.id != exclude_pin_id)

    stmt = stmt.order_by(distance_col.asc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()
    return [(row[0], float(row[1])) for row in rows]

