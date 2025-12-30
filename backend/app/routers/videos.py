import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends

from app.models import VideoRequest, JobResponse, JobStatus, VideoAnalysis
from app.services.summarizer import VideoSummarizer

router = APIRouter()

# In-memory job storage (use Redis in production)
jobs: dict[str, JobResponse] = {}
summarizer = VideoSummarizer()


async def require_auth(request: Request):
    """Check if user is authenticated."""
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def process_video(job_id: str, url: str):
    """Background task to process video."""
    try:
        jobs[job_id].status = JobStatus.PROCESSING
        result = summarizer.analyze(url)
        jobs[job_id].status = JobStatus.COMPLETED
        jobs[job_id].result = result
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
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.PENDING)
    background_tasks.add_task(process_video, job_id, request.url)
    return jobs[job_id]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str, user: dict = Depends(require_auth)):
    """Get the status and results of an analysis job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]
