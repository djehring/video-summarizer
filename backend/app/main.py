import os
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from app.routers import videos, chat, auth, history
from app.database import init_db, is_database_configured

load_dotenv()

# Static files directory (frontend build output)
STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield

app = FastAPI(
    title="Video Summarizer API",
    description="Extract transcripts from YouTube videos and generate summaries with annotated references",
    version="1.0.0",
    lifespan=lifespan,
)

# Session middleware (must be added before CORS)
# SameSite=none + Secure required for cross-domain cookies
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv('SESSION_SECRET', 'change-me-in-production'),
    max_age=86400 * 7,  # 7 days
    same_site='none',
    https_only=True,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3008",
        "http://localhost:5173",
        "https://video-summariser.net",
        "https://www.video-summariser.net",
        "https://video-summarizer-frontend-production.up.railway.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Auth dependency - use this to protect routes
async def require_auth(request: Request):
    """Check if user is authenticated."""
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(history.router, prefix="/api/history", tags=["history"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Serve frontend static files (if available)
if STATIC_DIR.exists():
    # Mount static assets (js, css, images)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # Serve index.html for all non-API routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't serve index.html for API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Try to serve the exact file first
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        # Fallback to index.html for SPA routing
        return FileResponse(STATIC_DIR / "index.html")
