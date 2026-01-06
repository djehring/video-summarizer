import os
import time
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatRequest, ChatResponse, SummarizeRequest, SummarizeResponse, VideoAnalysis, VideoMetadata, References
from app.routers.videos import jobs
from app.services.ai_agent import AIAgent
from app.services.exa_agent import ExaAgent
from app.database import get_session, is_database_configured, ChatMessageDB, VideoHistory

router = APIRouter()
exa_agent = ExaAgent() if os.getenv("EXA_API_KEY") else None


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

    # Optional: retrieve citations at chat-time via Exa when the user is asking for a paper/study/source.
    extra_context_parts: list[str] = []
    msg_l = (request.message or "").lower()
    # If the user explicitly asks to "use exa", treat that as a hard trigger for retrieval.
    explicit_exa = ("exa.ai" in msg_l) or ("use exa" in msg_l) or ("use exa.ai" in msg_l) or ("exa " in msg_l) or (msg_l.strip() == "exa")

    wants_citation = explicit_exa or any(
        k in msg_l for k in [
            "which study",
            "which paper",
            "what study",
            "what paper",
            "citation",
            "source",
            "reference",
            "pmid",
            "doi",
            "framingham",
            "trial",
            "cohort",
            "find the link",
            "find me the link",
            "find the research",
            "link to the research",
            "links to the research",
            "link to the study",
            "links to the stud",
            "pubmed",
            "paper",
            "human stud",
        ]
    )

    if exa_agent and exa_agent.enabled and wants_citation:

        # Use a clean base query (avoid sending the entire instruction sentence to Exa).
        base_query = (request.message or "").strip()
        if explicit_exa:
            import re
            base_query = re.sub(r'\buse\s+exa(\.ai)?\b', '', base_query, flags=re.IGNORECASE)
            base_query = re.sub(r'\bexa(\.ai)?\b', '', base_query, flags=re.IGNORECASE)
            base_query = " ".join(base_query.split()).strip()

        try:
            video_title = analysis.video.title if analysis.video else ""
            studies_hint = []
            try:
                studies_hint = list(getattr(analysis.references, "studies", []) or [])
            except Exception:
                studies_hint = []

            # Pull a few relevant keyword hints from the transcript to improve retrieval
            keywords_hint: list[str] = []
            try:
                t = (analysis.transcript or "").lower()
                for kw in [
                    "sulforaphane",
                    "broccoli sprouts",
                    "broccoli",
                    "sprouts",
                    "multivitamin",
                    "centrum",
                    "cosmos",
                    "cardiorespiratory",
                    "vo2",
                    "vo₂",
                    "vilpa",
                    "fitness",
                    "vitamin d",
                    "dementia",
                    "omega-3 index",
                    "omega 3 index",
                    "framingham",
                    "benzene",
                ]:
                    if kw in t:
                        keywords_hint.append(kw)
                keywords_hint = keywords_hint[:12]
            except Exception:
                keywords_hint = []

            papers = exa_agent.search_papers_sync(base_query or video_title, max_items=3)

            # If Exa returns nothing, refine into a few focused academic queries and retry.
            attempted_queries: list[str] = [base_query or video_title]
            if not papers:
                # Targeted fallbacks for common "headline claims" in these videos.
                # These are intentionally PubMed-friendly (works with our PubMed fallback too).
                if ("sulforaphane" in keywords_hint) or ("broccoli sprouts" in keywords_hint) or ("benzene" in keywords_hint):
                    targeted = [
                        "broccoli sprout beverage benzene acrolein mercapturic acid randomized trial",
                        "glucoraphanin-rich sulforaphane-rich broccoli sprout beverages Qidong airborne pollutants",
                        "broccoli sprout beverage S-phenylmercapturic acid 3-hydroxypropylmercapturic acid",
                    ]
                    for tq in targeted:
                        attempted_queries.append(tq)
                        papers.extend(exa_agent.search_papers_sync(tq, max_items=2))

                refined = exa_agent.refine_chat_queries_sync(
                    user_message=request.message,
                    video_title=video_title,
                    studies_hint=studies_hint,
                    keywords_hint=keywords_hint,
                )
                for q in refined:
                    attempted_queries.append(q)
                    papers.extend(exa_agent.search_papers_sync(q, max_items=2))

            # De-dup URLs while preserving order
            deduped = []
            seen_urls = set()
            for p in papers:
                u = (p.enriched_url or "").strip().lower()
                if not u or u in seen_urls:
                    continue
                seen_urls.add(u)
                deduped.append(p)
            papers = deduped[:5]

            if papers:
                lines = []
                for p in papers:
                    title = p.enriched_title or p.original_text
                    journal = f" ({p.enriched_journal})" if p.enriched_journal else ""
                    if p.enriched_url:
                        lines.append(f"- {title}{journal}: {p.enriched_url}")
                if lines:
                    extra_context_parts.append("On-demand paper lookup:\n" + "\n".join(lines))
        except Exception as e:
            # Never fail chat if Exa lookup fails
            print(f"[Chat] Exa lookup failed: {e}")

    extra_context = "\n\n".join(extra_context_parts) if extra_context_parts else None
    response = agent.chat(analysis, history, request.message, extra_context=extra_context)

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
