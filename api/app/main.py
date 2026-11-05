from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.routers import auth, boards, chat, pins, search, social, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure pgvector extension exists on startup
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    except Exception as e:
        print(f"[Warning] Failed to verify/create pgvector extension: {e}")
    yield
    await engine.dispose()


app = FastAPI(
    title="Pinterest Clone API",
    description="FastAPI + PostgreSQL + pgvector backend for Pinterest clone",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(pins.router)
app.include_router(boards.router)
app.include_router(search.router)
app.include_router(users.router)
app.include_router(chat.router)
app.include_router(social.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Pinterest Clone API"}


@app.get("/")
async def root():
    return {
        "message": "Pinterest Clone API is running",
        "docs": "/docs",
    }

