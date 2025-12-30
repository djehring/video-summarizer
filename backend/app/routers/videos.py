import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models import VideoRequest, JobResponse, JobStatus, VideoAnalysis
from app.services.summarizer import VideoSummarizer

router = APIRouter()

# In-memory job storage (use Redis in production)
jobs: dict[str, JobResponse] = {}
summarizer = VideoSummarizer()


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
async def analyze_video(request: VideoRequest, background_tasks: BackgroundTasks):
    """Submit a YouTube URL for analysis. Returns a job ID to poll for results."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.PENDING)
    background_tasks.add_task(process_video, job_id, request.url)
    return jobs[job_id]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Get the status and results of an analysis job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]
