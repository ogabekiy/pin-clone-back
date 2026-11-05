from typing import List
import httpx
from app.core.config import settings


async def get_text_embedding(text: str) -> List[float]:
    """Requests normalized 512-dim embedding for text from the embedder service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{settings.EMBEDDER_URL.rstrip('/')}/embed/text",
            params={"q": text},
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]


async def get_image_embedding(image_bytes: bytes, filename: str = "image.jpg") -> List[float]:
    """Requests normalized 512-dim embedding for image bytes from the embedder service."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        files = {"file": (filename, image_bytes, "image/jpeg")}
        response = await client.post(
            f"{settings.EMBEDDER_URL.rstrip('/')}/embed/image",
            files=files,
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]

