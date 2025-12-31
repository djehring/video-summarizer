from pydantic import BaseModel
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoRequest(BaseModel):
    url: str


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    channel: str
    duration: int
    url: str


class References(BaseModel):
    studies: list[str] = []
    people: list[str] = []
    books: list[str] = []
    organizations: list[str] = []
    terms: list[str] = []
    paper_links: list[str] = []  # PubMed, DOI, PMC, academic paper URLs
    urls: list[str] = []  # Other URLs


class VideoAnalysis(BaseModel):
    video: VideoMetadata
    references: References
    transcript: str
    llm_prompt: str
    synopsis: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    error: Optional[str] = None
    result: Optional[VideoAnalysis] = None


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    job_id: str
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str


class SummarizeRequest(BaseModel):
    job_id: str


class SummarizeResponse(BaseModel):
    summary: str
