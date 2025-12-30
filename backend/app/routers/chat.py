import os
from fastapi import APIRouter, HTTPException

from app.models import ChatRequest, ChatResponse, SummarizeRequest, SummarizeResponse
from app.routers.videos import jobs
from app.services.ai_agent import AIAgent

router = APIRouter()


def get_agent() -> AIAgent:
    """Get AI agent, checking for API key."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
        )
    return AIAgent()


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_video(request: SummarizeRequest):
    """Generate an AI summary of the analyzed video."""
    if request.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[request.job_id]
    if job.status != "completed" or not job.result:
        raise HTTPException(status_code=400, detail="Video analysis not completed")

    agent = get_agent()
    summary = agent.summarize(job.result)
    return SummarizeResponse(summary=summary)


@router.post("/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest):
    """Send a chat message about the analyzed video."""
    if request.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[request.job_id]
    if job.status != "completed" or not job.result:
        raise HTTPException(status_code=400, detail="Video analysis not completed")

    agent = get_agent()
    history = [{"role": m.role, "content": m.content} for m in request.history]
    response = agent.chat(job.result, history, request.message)
    return ChatResponse(response=response)
