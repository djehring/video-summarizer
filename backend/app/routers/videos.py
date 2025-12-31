import os
import re
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends

from app.models import VideoRequest, JobResponse, JobStatus, VideoAnalysis, VideoMetadata, References
from app.services.summarizer import VideoSummarizer
from app.services.ai_agent import AIAgent
from app.database import VideoHistory, is_database_configured

router = APIRouter()

# In-memory job storage (use Redis in production)
jobs: dict[str, JobResponse] = {}
# Track user email for each job (for saving to history)
job_users: dict[str, str] = {}
summarizer = VideoSummarizer()
ai_agent = AIAgent() if os.getenv("OPENAI_API_KEY") else None


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def check_existing_history(video_id: str, user_email: str) -> tuple[str, VideoAnalysis] | None:
    """Check if video already exists in user's history. Returns (job_id, analysis) or None."""
    import os
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    db_url = os.getenv('DATABASE_URL', '')
    if not db_url:
        return None

    # Use sync driver
    if db_url.startswith('postgresql+asyncpg://'):
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

    try:
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        history = session.query(VideoHistory).filter(
            VideoHistory.video_id == video_id,
            VideoHistory.user_email == user_email
        ).order_by(VideoHistory.created_at.desc()).first()

        if history:
            # Reconstruct VideoAnalysis from database
            analysis = VideoAnalysis(
                video=VideoMetadata(
                    video_id=history.video_id,
                    title=history.title or '',
                    channel=history.channel or '',
                    duration=history.duration or 0,
                    url=history.url or ''
                ),
                references=References(**(history.references or {})),
                transcript=history.transcript or '',
                llm_prompt=history.llm_prompt or ''
            )
            job_id = history.job_id
            session.close()
            engine.dispose()
            return (job_id, analysis)

        session.close()
        engine.dispose()
    except Exception as e:
        print(f"[DB] Error checking existing history: {e}")

    return None


async def require_auth(request: Request):
    """Check if user is authenticated."""
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def save_to_history_sync(job_id: str, result: VideoAnalysis, user_email: str):
    """Save analysis result to database (sync version for background tasks)."""
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = os.getenv('DATABASE_URL', '')
    if not db_url:
        return

    # Use sync driver (psycopg2) instead of async (asyncpg)
    if db_url.startswith('postgresql+asyncpg://'):
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
    elif db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    try:
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        history = VideoHistory(
            user_email=user_email,
            job_id=job_id,
            video_id=result.video.video_id,
            title=result.video.title,
            channel=result.video.channel,
            duration=result.video.duration,
            url=result.video.url,
            references=result.references.model_dump(),
            transcript=result.transcript,
            llm_prompt=result.llm_prompt
        )
        session.add(history)
        session.commit()
        session.close()
        engine.dispose()
    except Exception as e:
        print(f"[DB] Error saving history: {e}")


def process_video(job_id: str, url: str):
    """Background task to process video."""
    try:
        jobs[job_id].status = JobStatus.PROCESSING
        result = summarizer.analyze(url)

        # Generate synopsis if AI agent is available
        if ai_agent:
            try:
                result.synopsis = ai_agent.generate_synopsis(result)
            except Exception as e:
                print(f"[Videos] Failed to generate synopsis: {e}")
                # Continue without synopsis if generation fails

        jobs[job_id].status = JobStatus.COMPLETED
        jobs[job_id].result = result

        # Save to history database
        user_email = job_users.get(job_id)
        if user_email:
            save_to_history_sync(job_id, result, user_email)
    except Exception as e:
        jobs[job_id].status = JobStatus.FAILED
        jobs[job_id].error = str(e)


@router.post("/analyze", response_model=JobResponse)
async def analyze_video(
    request: VideoRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_auth)
):
    """Submit a YouTube URL for analysis. Returns a job ID to poll for results."""
    user_email = user.get('email', '')

    # Check if video already exists in user's history
    video_id = extract_video_id(request.url)
    if video_id and is_database_configured():
        existing = check_existing_history(video_id, user_email)
        if existing:
            job_id, analysis = existing
            # Populate in-memory store so subsequent requests work
            jobs[job_id] = JobResponse(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                result=analysis
            )
            job_users[job_id] = user_email
            print(f"[Videos] Returning existing analysis for video {video_id}")
            return jobs[job_id]

    # Create new analysis job
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.PENDING)
    job_users[job_id] = user_email
    background_tasks.add_task(process_video, job_id, request.url)
    return jobs[job_id]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str, user: dict = Depends(require_auth)):
    """Get the status and results of an analysis job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]
