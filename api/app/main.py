from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.routers import admin, auth, boards, chat, pins, search, social, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure pgvector extension and admin columns exist on startup
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            # Auto-ensure role, is_blocked, password_hash columns exist on users
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user';"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;"))
            await conn.execute(text("ALTER TABLE users ALTER COLUMN google_id DROP NOT NULL;"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_is_blocked ON users (is_blocked);"))
    except Exception as e:
        print(f"[Warning] Failed to verify/create schema additions: {e}")
    yield
    await engine.dispose()


app = FastAPI(
    title="Pinterest Clone API",
    description="FastAPI + PostgreSQL + pgvector backend for Pinterest clone",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration (supports localhost, custom domains, and Vercel deployments)
allow_all = "*" in settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*" if allow_all else None,
    allow_origins=[] if allow_all else settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
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

