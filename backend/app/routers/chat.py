import os
import time
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatRequest, ChatResponse, SummarizeRequest, SummarizeResponse, VideoAnalysis, VideoMetadata, References
from app.routers.videos import jobs
from app.services.ai_agent import AIAgent
from app.database import get_session, is_database_configured, ChatMessageDB, VideoHistory

router = APIRouter()


async def require_auth(request: Request) -> dict:
    """Check if user is authenticated."""
    # Try session first (desktop browsers)
    user = request.session.get('user')
    if user:
        return user

    # Try Authorization header (mobile browsers)
    from app.routers.auth import auth_tokens
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        token_data = auth_tokens.get(token)
        if token_data and token_data.get('expires', 0) > time.time():
            return token_data['user']

    raise HTTPException(status_code=401, detail="Not authenticated")


async def save_chat_messages(job_id: str, messages: list[dict], session: AsyncSession):
    """Save chat messages to database."""
    print(f"[Chat] Saving {len(messages)} messages for job {job_id}")
    for msg in messages:
        db_message = ChatMessageDB(
            job_id=job_id,
            role=msg['role'],
            content=msg['content']
        )
        session.add(db_message)
    await session.commit()
    print(f"[Chat] Successfully saved messages for job {job_id}")


async def get_job_analysis(job_id: str, user_email: str) -> VideoAnalysis | None:
    """Get job analysis from memory or database."""
    # First check in-memory jobs
    if job_id in jobs:
        job = jobs[job_id]
        if job.status == "completed" and job.result:
            return job.result

    # Fall back to database
    if is_database_configured():
        try:
            async for session in get_session():
                query = select(VideoHistory).where(
                    VideoHistory.job_id == job_id,
                    VideoHistory.user_email == user_email
                )
                result = await session.execute(query)
                history = result.scalar_one_or_none()

                if history:
                    # Reconstruct VideoAnalysis from database
                    return VideoAnalysis(
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
                break
        except Exception as e:
            print(f"[Chat] Failed to load job from database: {e}")

    return None


def get_agent() -> AIAgent:
    """Get AI agent, checking for API key."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
        )
    return AIAgent()


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_video(request: SummarizeRequest, req: Request, user: dict = Depends(require_auth)):
    """Generate an AI summary of the analyzed video."""
    analysis = await get_job_analysis(request.job_id, user['email'])
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")

    agent = get_agent()
    summary = agent.summarize(analysis)

    # Save chat messages to database if configured
    if is_database_configured():
        try:
            async for session in get_session():
                # Save the initial summary request and response
                messages = [
                    {"role": "user", "content": "Generate annotated summary"},
                    {"role": "assistant", "content": summary}
                ]
                await save_chat_messages(request.job_id, messages, session)
                break
        except Exception as e:
            # Log but don't fail the request if DB save fails
            import traceback
            print(f"[Chat] Failed to save summary messages: {e}")
            print(f"[Chat] Traceback: {traceback.format_exc()}")
    else:
        print("[Chat] Database not configured, skipping message save")

    return SummarizeResponse(summary=summary)


@router.post("/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest, req: Request, user: dict = Depends(require_auth)):
    """Send a chat message about the analyzed video."""
    analysis = await get_job_analysis(request.job_id, user['email'])
    if not analysis:
        raise HTTPException(status_code=404, detail="Job not found")

    agent = get_agent()
    history = [{"role": m.role, "content": m.content} for m in request.history]
    response = agent.chat(analysis, history, request.message)

    # Save chat messages to database if configured
    if is_database_configured():
        try:
            async for session in get_session():
                # Save the user message and assistant response
                new_messages = [
                    {"role": "user", "content": request.message},
                    {"role": "assistant", "content": response}
                ]
                await save_chat_messages(request.job_id, new_messages, session)
                break
        except Exception as e:
            # Log but don't fail the request if DB save fails
            import traceback
            print(f"[Chat] Failed to save chat messages: {e}")
            print(f"[Chat] Traceback: {traceback.format_exc()}")
    else:
        print("[Chat] Database not configured, skipping message save")

    return ChatResponse(response=response)
