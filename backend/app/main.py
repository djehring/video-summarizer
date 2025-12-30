from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import videos

app = FastAPI(
    title="Video Summarizer API",
    description="Extract transcripts from YouTube videos and generate summaries with annotated references",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
