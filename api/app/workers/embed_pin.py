import httpx
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.pin import Pin
from app.services.embedder_client import get_image_embedding


async def process_pin_embedding(pin_id: int) -> None:
    """
    Background worker task to fetch image and compute CLIP embedding asynchronously.
    Rule 4: Embedding is never computed synchronously during pin creation.
    """
    async with async_session_factory() as db:
        stmt = select(Pin).where(Pin.id == pin_id)
        result = await db.execute(stmt)
        pin = result.scalar_one_or_none()

        if not pin or not pin.image_url:
            return

        try:
            # Download image bytes
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(pin.image_url)
                res.raise_for_status()
                image_bytes = res.content

            # Request embedding from embedder service
            embedding = await get_image_embedding(image_bytes)

            pin.embedding = embedding
            pin.embed_status = "done"
            await db.commit()
        except Exception as e:
            pin.embed_status = "failed"
            await db.commit()
            # print or log error
            print(f"[Worker Error] Failed to generate embedding for pin {pin_id}: {e}")

