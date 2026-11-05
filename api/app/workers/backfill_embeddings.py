import asyncio
import httpx
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.pin import Pin
from app.services.embedder_client import get_image_embedding


async def backfill_all_pins():
    """Generates CLIP embeddings for all existing pins that lack them."""
    async with async_session_factory() as db:
        stmt = (
            select(Pin)
            .where((Pin.embedding.is_(None)) | (Pin.embed_status != "done"))
            .order_by(Pin.id.asc())
        )
        result = await db.execute(stmt)
        pins = list(result.scalars().all())

        print(f"Embedding mavjud bo'lmagan {len(pins)} ta pin topildi.")

        for p in pins:
            print(f"Pin #{p.id} ({p.title or 'Nomsiz'}) tahlil qilinmoqda...")
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.get(p.image_url)
                    res.raise_for_status()
                    image_bytes = res.content

                embedding = await get_image_embedding(image_bytes)
                p.embedding = embedding
                p.embed_status = "done"
                await db.commit()
                print(f"Pin #{p.id} uchun embedding muvaffaqiyatli saqlandi! (512-dim)")
            except Exception as e:
                print(f"Pin #{p.id} da xatolik: {e}")


if __name__ == "__main__":
    asyncio.run(backfill_all_pins())

