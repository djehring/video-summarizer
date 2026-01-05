from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc, asc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
import json
import io
import os

from app.database import get_session, is_database_configured, VideoHistory, ChatMessageDB

router = APIRouter()

# Configuration from environment
HISTORY_MAX_ENTRIES = int(os.getenv('HISTORY_MAX_ENTRIES', '50'))
HISTORY_RETENTION_DAYS = int(os.getenv('HISTORY_RETENTION_DAYS', '90'))


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


class ApiStatus(BaseModel):
    openai: bool
    exa: bool

class SettingsResponse(BaseModel):
    max_entries: int
    retention_days: int
    current_count: int
    api_status: ApiStatus


def check_db_enabled():
    """Raise error if database not configured."""
    if not is_database_configured():
        raise HTTPException(status_code=503, detail="History feature not available")


@router.get("", response_model=HistoryListResponse)
async def list_history(
    request: Request,
    search: Optional[str] = None,
    sort: Literal['date', 'title'] = 'date',
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_session)
):
    """List user's video history with optional search and sort."""
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
    )

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                VideoHistory.title.ilike(search_term),
                VideoHistory.channel.ilike(search_term)
            )
        )

    # Apply sort
    if sort == 'title':
        query = query.order_by(asc(VideoHistory.title))
    else:
        query = query.order_by(desc(VideoHistory.created_at))

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


@router.delete("")
async def clear_all_history(
    request: Request,
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_session)
):
    """Delete all history items for the current user."""
    check_db_enabled()

    user_email = user['email']

    # Get all history items for user
    query = select(VideoHistory).where(VideoHistory.user_email == user_email)
    result = await session.execute(query)
    items = result.scalars().all()

    deleted_count = len(items)
    for item in items:
        await session.delete(item)

    await session.commit()

    return {"success": True, "deleted_count": deleted_count}


@router.get("/settings/info", response_model=SettingsResponse)
async def get_settings(
    request: Request,
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_session)
):
    """Get history settings and current usage."""
    check_db_enabled()

    user_email = user['email']

    # Count current entries
    count_query = select(func.count(VideoHistory.id)).where(
        VideoHistory.user_email == user_email
    )
    result = await session.execute(count_query)
    current_count = result.scalar() or 0

    # Check API configurations
    openai_configured = bool(os.getenv('OPENAI_API_KEY'))
    exa_configured = bool(os.getenv('EXA_API_KEY'))

    return SettingsResponse(
        max_entries=HISTORY_MAX_ENTRIES,
        retention_days=HISTORY_RETENTION_DAYS,
        current_count=current_count,
        api_status=ApiStatus(openai=openai_configured, exa=exa_configured)
    )


@router.get("/export/json")
async def export_history(
    request: Request,
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_session)
):
    """Export all history as JSON file."""
    check_db_enabled()

    user_email = user['email']

    # Get all history items with chat messages
    query = (
        select(VideoHistory)
        .where(VideoHistory.user_email == user_email)
        .order_by(desc(VideoHistory.created_at))
    )
    result = await session.execute(query)
    items = result.scalars().all()

    export_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "user_email": user_email,
        "items": []
    }

    for item in items:
        # Get chat messages for this item
        messages_query = (
            select(ChatMessageDB)
            .where(ChatMessageDB.job_id == item.job_id)
            .order_by(ChatMessageDB.created_at)
        )
        messages_result = await session.execute(messages_query)
        messages = messages_result.scalars().all()

        export_data["items"].append({
            "job_id": item.job_id,
            "video_id": item.video_id,
            "title": item.title,
            "channel": item.channel,
            "duration": item.duration,
            "url": item.url,
            "references": item.references,
            "transcript": item.transcript,
            "llm_prompt": item.llm_prompt,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "chat_messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None
                }
                for m in messages
            ]
        })

    # Create JSON file response
    json_bytes = json.dumps(export_data, indent=2).encode('utf-8')
    filename = f"video-history-{datetime.utcnow().strftime('%Y%m%d')}.json"

    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
