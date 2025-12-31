from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_session, is_database_configured, VideoHistory, ChatMessageDB

router = APIRouter()


# Auth helper - same pattern as other routers
async def require_auth(request: Request) -> dict:
    """Check if user is authenticated."""
    # Try session first (desktop browsers)
    user = request.session.get('user')
    if user:
        return user

    # Try Authorization header (mobile browsers)
    from app.routers.auth import auth_tokens
    import time
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        token_data = auth_tokens.get(token)
        if token_data and token_data.get('expires', 0) > time.time():
            return token_data['user']

    raise HTTPException(status_code=401, detail="Not authenticated")


# Pydantic models for responses
class HistoryListItem(BaseModel):
    job_id: str
    video_id: str
    title: Optional[str]
    channel: Optional[str]
    duration: Optional[int]
    url: Optional[str]
    created_at: datetime
    message_count: int


class HistoryListResponse(BaseModel):
    items: list[HistoryListItem]
    total: int


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    created_at: datetime


class HistoryDetailResponse(BaseModel):
    job_id: str
    video_id: str
    title: Optional[str]
    channel: Optional[str]
    duration: Optional[int]
    url: Optional[str]
    references: Optional[dict]
    transcript: Optional[str]
    llm_prompt: Optional[str]
    chat_messages: list[ChatMessageResponse]
    created_at: datetime


def check_db_enabled():
    """Raise error if database not configured."""
    if not is_database_configured():
        raise HTTPException(status_code=503, detail="History feature not available")


@router.get("", response_model=HistoryListResponse)
async def list_history(
    request: Request,
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_session)
):
    """List user's video history."""
    check_db_enabled()

    user_email = user['email']

    # Get history items with message count
    subquery = (
        select(ChatMessageDB.job_id, func.count(ChatMessageDB.id).label('message_count'))
        .group_by(ChatMessageDB.job_id)
        .subquery()
    )

    query = (
        select(
            VideoHistory.job_id,
            VideoHistory.video_id,
            VideoHistory.title,
            VideoHistory.channel,
            VideoHistory.duration,
            VideoHistory.url,
            VideoHistory.created_at,
            func.coalesce(subquery.c.message_count, 0).label('message_count')
        )
        .outerjoin(subquery, VideoHistory.job_id == subquery.c.job_id)
        .where(VideoHistory.user_email == user_email)
        .order_by(desc(VideoHistory.created_at))
    )

    result = await session.execute(query)
    rows = result.all()

    items = [
        HistoryListItem(
            job_id=row.job_id,
            video_id=row.video_id,
            title=row.title,
            channel=row.channel,
            duration=row.duration,
            url=row.url,
            created_at=row.created_at,
            message_count=row.message_count
        )
        for row in rows
    ]

    return HistoryListResponse(items=items, total=len(items))


@router.get("/{job_id}", response_model=HistoryDetailResponse)
async def get_history_item(
    job_id: str,
    request: Request,
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_session)
):
    """Get full analysis and chat history for a video."""
    check_db_enabled()

    user_email = user['email']

    # Get video history
    query = select(VideoHistory).where(
        VideoHistory.job_id == job_id,
        VideoHistory.user_email == user_email
    )
    result = await session.execute(query)
    history = result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="History item not found")

    # Get chat messages
    messages_query = (
        select(ChatMessageDB)
        .where(ChatMessageDB.job_id == job_id)
        .order_by(ChatMessageDB.created_at)
    )
    messages_result = await session.execute(messages_query)
    messages = messages_result.scalars().all()

    return HistoryDetailResponse(
        job_id=history.job_id,
        video_id=history.video_id,
        title=history.title,
        channel=history.channel,
        duration=history.duration,
        url=history.url,
        references=history.references,
        transcript=history.transcript,
        llm_prompt=history.llm_prompt,
        chat_messages=[
            ChatMessageResponse(
                role=m.role,
                content=m.content,
                created_at=m.created_at
            )
            for m in messages
        ],
        created_at=history.created_at
    )


@router.delete("/{job_id}")
async def delete_history_item(
    job_id: str,
    request: Request,
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_session)
):
    """Delete a history item."""
    check_db_enabled()

    user_email = user['email']

    # Find and delete
    query = select(VideoHistory).where(
        VideoHistory.job_id == job_id,
        VideoHistory.user_email == user_email
    )
    result = await session.execute(query)
    history = result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="History item not found")

    await session.delete(history)
    await session.commit()

    return {"success": True}
