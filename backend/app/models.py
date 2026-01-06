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
    force_refresh: bool = False


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    channel: str
    duration: int
    url: str


class EnrichedReference(BaseModel):
    """A study reference enriched with actual source URL from Exa search."""
    original_text: str
    enriched_url: Optional[str] = None
    enriched_title: Optional[str] = None
    enriched_journal: Optional[str] = None
    confidence: float = 0.0
    source: str = "exa"


class EnrichedPerson(BaseModel):
    """A person mentioned in the video with corrected name and authoritative link."""
    original_text: str  # The name as it appeared in transcript (possibly mispronounced)
    corrected_name: str  # The correct spelling
    title: Optional[str] = None  # e.g. "M.D.", "Ph.D."
    affiliation: Optional[str] = None  # e.g. "UT Southwestern Medical Center"
    url: Optional[str] = None  # Authoritative profile URL
    confidence: float = 1.0


class References(BaseModel):
    studies: list[str] = []
    studies_enriched: list[EnrichedReference] = []  # Studies with actual paper URLs
    people: list[str] = []
    people_enriched: list[EnrichedPerson] = []  # People with corrected names and profile URLs
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
    image_base64: Optional[str] = None  # For messages with attached images


class ChatRequest(BaseModel):
    job_id: str
    message: str
    history: list[ChatMessage] = []
    image_base64: Optional[str] = None  # Base64-encoded image data (JPEG/PNG)


class ChatResponse(BaseModel):
    response: str


class SummarizeRequest(BaseModel):
    job_id: str


class SummarizeResponse(BaseModel):
    summary: str
