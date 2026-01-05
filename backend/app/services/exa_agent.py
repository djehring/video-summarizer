"""
Exa AI integration for enriching study references with actual paper URLs.
Uses OpenAI to clean up study references and generate better search queries.
"""
import os
import httpx
from typing import Optional
from pydantic import BaseModel
from openai import OpenAI
from urllib.parse import urlparse


class EnrichedReference(BaseModel):
    """A study reference enriched with actual source URL."""
    original_text: str
    enriched_url: Optional[str] = None
    enriched_title: Optional[str] = None
    enriched_journal: Optional[str] = None
    confidence: float = 0.0
    source: str = "exa"


# Academic domains to prioritize in search results
ACADEMIC_DOMAINS = [
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "doi.org",
    "dx.doi.org",
    "nature.com",
    "cell.com",
    "science.org",
    "thelancet.com",
    "jamanetwork.com",
    "bmj.com",
    "nejm.org",
    "pnas.org",
    "frontiersin.org",
    "springer.com",
    "wiley.com",
    "biorxiv.org",
    "medrxiv.org",
    "arxiv.org",
    "sciencedirect.com",
    "europepmc.org",
    "ieeexplore.ieee.org",
]

# Patterns that indicate a generic journal page, not a specific article
GENERIC_PAGE_PATTERNS = [
    "/articles$",
    "/research$",
    "/research-articles",
    "/browse",
    "/search",
    "/collections",
    "/subjects",
    "/ncomms$",  # Nature Communications homepage
    "/nature/journal",
    "nature.com/ncomms$",
]

GOOGLE_HOSTS = {
    "google.com",
    "www.google.com",
    "scholar.google.com",
}

def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""

def _is_google_url(url: str) -> bool:
    host = _hostname(url)
    return host in GOOGLE_HOSTS or host.endswith(".google.com")

def is_specific_article(url: str, title: str) -> bool:
    """Check if URL points to a specific article rather than a journal index page."""
    url_lower = url.lower()
    title_lower = title.lower() if title else ""

    # Check for generic page patterns in URL
    import re
    for pattern in GENERIC_PAGE_PATTERNS:
        if re.search(pattern, url_lower):
            return False

    # Check for generic titles
    generic_title_patterns = [
        "research articles |",
        "browse articles",
        "latest research",
        "all articles",
        "article search",
    ]
    for pattern in generic_title_patterns:
        if pattern in title_lower:
            return False

    # Good signs: URL contains article identifiers
    article_indicators = [
        "/article/",
        "/articles/",
        "/abs/",
        "/full/",
        "/pdf/",
        "doi.org/10.",
        "/pmc/articles/PMC",
        "/pubmed/",
    ]
    if any(indicator in url_lower for indicator in article_indicators):
        return True

    # If URL has numbers that look like article IDs, likely specific
    if re.search(r'/[a-z]*\d{4,}', url_lower):
        return True

    return True  # Default to accepting if no red flags

def clean_title_and_journal(title: str) -> tuple[str, Optional[str]]:
    """Clean up article titles from Exa results and extract journal/source when present."""
    if not title:
        return title, None

    # Try to capture journal/source suffix before stripping it
    suffix_map: list[tuple[str, str]] = [
        (" - PubMed", "PubMed"),
        (" – PubMed", "PubMed"),
        (" | Nature Communications", "Nature Communications"),
        (" - Nature Communications", "Nature Communications"),
        (" – Nature Communications", "Nature Communications"),
        (" | Nature", "Nature"),
        (" - Nature", "Nature"),
        (" – Nature", "Nature"),
        (" | Science", "Science"),
        (" - Science", "Science"),
        (" – Science", "Science"),
        (" - PMC", "PMC"),
        (" – PMC", "PMC"),
        (" - NCBI", "NCBI"),
        (" – NCBI", "NCBI"),
        (" - NIH", "NIH"),
        (" – NIH", "NIH"),
    ]

    journal: Optional[str] = None
    for suffix, j in suffix_map:
        if title.endswith(suffix):
            journal = j
            title = title[:-len(suffix)]
            break

    # Remove trailing ellipsis and whitespace (Exa sometimes truncates with ...)
    title = title.strip()
    if title.endswith("..."):
        title = title[:-3].rstrip()
    if title.endswith("…"):
        title = title[:-1].rstrip()
    title = title.rstrip(". ").strip()

    return title, journal

def infer_source_from_url(url: str) -> Optional[str]:
    """Infer a journal/source name from the URL when we can't extract it from title."""
    host = _hostname(url)
    if not host:
        return None
    if host == "nature.com":
        # Nature journal codes (common ones we see in health/fitness videos)
        url_l = url.lower()
        if "s41467" in url_l:
            return "Nature Communications"
        if "s41591" in url_l:
            return "Nature Medicine"
        if "s41586" in url_l:
            return "Nature"
        if "s41597" in url_l:
            return "Scientific Data"
        if "s41598" in url_l:
            return "Scientific Reports"
        return "Nature"
    if host.endswith("ieee.org"):
        return "IEEE Xplore"
    if host == "arxiv.org":
        return "arXiv"
    if host.endswith("ncbi.nlm.nih.gov") or host.endswith("pubmed.ncbi.nlm.nih.gov"):
        return "PubMed"
    if host == "doi.org" or host == "dx.doi.org":
        return "DOI"
    if host.endswith("thelancet.com"):
        return "The Lancet"
    if host.endswith("jamanetwork.com"):
        return "JAMA"
    if host.endswith("bmj.com"):
        return "BMJ"
    if host.endswith("nejm.org"):
        return "NEJM"
    # Fall back to host (humanized) only if we have nothing better
    return host.replace("www.", "")


# Journal names that are too vague to search for on their own
VAGUE_STUDY_PATTERNS = [
    "nature communications",
    "nature medicine",
    "nature neuroscience",
    "cell metabolism",
    "cell reports",
    "science advances",
    "the lancet",
    "lancet",
    "jama",
    "bmj",
    "nejm",
    "pnas",
]


def is_vague_study_reference(study_text: str) -> bool:
    """Check if study reference is too vague to search meaningfully."""
    text_lower = study_text.lower().strip()

    # Too short
    if len(text_lower) < 15:
        return True

    # Just a journal name without context
    for pattern in VAGUE_STUDY_PATTERNS:
        # If the text is basically just the journal name (with minor variations)
        if text_lower == pattern or text_lower == f"the {pattern}":
            return True
        # If it's just the journal name with minimal extra words
        if text_lower.startswith(pattern) and len(text_lower) < len(pattern) + 10:
            return True

    return False


class ExaAgent:
    """Exa AI client for searching and enriching study references."""

    def __init__(self):
        self.api_key = os.getenv("EXA_API_KEY")
        self.base_url = "https://api.exa.ai"
        self.enabled = bool(self.api_key)

        # Initialize OpenAI for query refinement
        openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = OpenAI(api_key=openai_key) if openai_key else None
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def _refine_study_query(self, raw_text: str) -> Optional[str]:
        """Use OpenAI to clean up a messy study reference into a proper search query."""
        if not self.openai_client:
            return raw_text

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": """You extract search queries for academic papers from text.
Given a messy study reference extracted from a video transcript, output ONLY a clean search query.

Rules:
- If it mentions a specific study/paper topic, extract that (e.g., "accelerometer data activity recognition")
- If it's just a journal name (Nature, Cell, JAMA), output "SKIP"
- If it's a dataset/survey name (NHANES, UK Biobank), output the full name
- Keep it concise (under 10 words)
- Output ONLY the search query, nothing else"""
                    },
                    {
                        "role": "user",
                        "content": raw_text
                    }
                ],
            )

            result = response.choices[0].message.content.strip()

            if result.upper() == "SKIP" or len(result) < 5:
                print(f"[Exa/AI] Skipping: '{raw_text}' -> SKIP")
                return None

            print(f"[Exa/AI] Refined: '{raw_text}' -> '{result}'")
            return result

        except Exception as e:
            print(f"[Exa/AI] Error refining query: {e}")
            return raw_text

    async def search_study(self, study_text: str) -> Optional[EnrichedReference]:
        """
        Search Exa for an academic paper matching the study description.

        Args:
            study_text: The study mention from the transcript (e.g., "Nature Communications 2023 study on sleep")

        Returns:
            EnrichedReference with URL and title if found, None otherwise
        """
        if not self.enabled:
            return None

        # Use AI to refine the query (or skip if too vague)
        refined_query = self._refine_study_query(study_text)
        if not refined_query:
            return None

        # Build search query optimized for academic papers
        query = f"{refined_query} research paper study"
        print(f"[Exa] Searching: '{query}'")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/search",
                    headers={
                        "x-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": query,
                        "numResults": 5,
                        "type": "auto",
                        # Request full content to get complete titles
                        "contents": {
                            "text": {"maxCharacters": 2000}
                        }
                    }
                )

                if response.status_code != 200:
                    print(f"[Exa] Search failed with status {response.status_code}: {response.text[:200]}")
                    return None

                data = response.json()
                results = data.get("results", [])

                if not results:
                    return None

                # First pass: look for specific articles from academic domains
                for result in results:
                    url = result.get("url", "")
                    title = result.get("title", "")
                    text_content = result.get("text", "")

                    print(f"[Exa] Result: title='{title}' url='{url[:80]}...'")

                    # Skip Google results (they look like "generic journal pages" in the UI)
                    if _is_google_url(url):
                        continue

                    # Skip generic journal pages
                    if not is_specific_article(url, title):
                        print(f"[Exa] Skipped generic page: {title}")
                        continue

                    url_lower = url.lower()
                    if any(domain in url_lower for domain in ACADEMIC_DOMAINS):
                        # Prefer a fuller title from Exa 'text' when title looks truncated
                        candidate_title = title
                        if ("..." in title) or ("…" in title):
                            if text_content:
                                first_line = text_content.split('\n')[0].strip()
                                if first_line and len(first_line) < 240:
                                    candidate_title = first_line

                        # Clean up the title + extract journal/source
                        cleaned, journal = clean_title_and_journal(candidate_title)

                        # If title looks truncated, try to extract from text content
                        if cleaned.endswith('...') or cleaned.endswith('…') or len(cleaned) < 20:
                            # Try to get better title from text content (first line often has title)
                            if text_content:
                                first_line = text_content.split('\n')[0].strip()
                                if len(first_line) > len(cleaned) and len(first_line) < 200:
                                    cleaned, journal2 = clean_title_and_journal(first_line)
                                    journal = journal or journal2
                                    print(f"[Exa] Used text for title: '{cleaned}'")

                        print(f"[Exa] Using: '{cleaned}'")
                        return EnrichedReference(
                            original_text=study_text,
                            enriched_url=url,
                            enriched_title=cleaned,
                            enriched_journal=journal or infer_source_from_url(url),
                            confidence=min(result.get("score", 0.5), 1.0),
                            source="exa"
                        )

                # Second pass: any specific article (non-academic domain)
                for result in results:
                    url = result.get("url", "")
                    title = result.get("title", "")

                    if _is_google_url(url):
                        continue

                    if is_specific_article(url, title):
                        cleaned, journal = clean_title_and_journal(title)
                        return EnrichedReference(
                            original_text=study_text,
                            enriched_url=url,
                            enriched_title=cleaned,
                            enriched_journal=journal or infer_source_from_url(url),
                            confidence=min(result.get("score", 0.3) * 0.7, 1.0),
                            source="exa"
                        )

                # No specific articles found
                return None

        except httpx.TimeoutException:
            print(f"[Exa] Timeout searching for: {study_text[:50]}")
            return None
        except Exception as e:
            print(f"[Exa] Error searching for study: {e}")
            return None

    async def enrich_studies(
        self,
        studies: list[str],
        max_items: int = 5
    ) -> list[EnrichedReference]:
        """
        Batch enrich multiple study references.

        Args:
            studies: List of study mentions from the transcript
            max_items: Maximum number of studies to enrich (to control API costs)

        Returns:
            List of EnrichedReference objects for studies that were successfully enriched
        """
        if not self.enabled or not studies:
            return []

        enriched = []

        # Limit to max_items to control API usage
        for study in studies[:max_items]:
            result = await self.search_study(study)
            if result and result.enriched_url:
                enriched.append(result)

        print(f"[Exa] Enriched {len(enriched)}/{min(len(studies), max_items)} studies")
        return enriched

    def enrich_studies_sync(
        self,
        studies: list[str],
        max_items: int = 5
    ) -> list[EnrichedReference]:
        """
        Synchronous wrapper for enrich_studies.
        Use this in sync contexts like background tasks.
        """
        import asyncio

        if not self.enabled or not studies:
            return []

        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.enrich_studies(studies, max_items)
                    )
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(
                    self.enrich_studies(studies, max_items)
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.enrich_studies(studies, max_items))
        except Exception as e:
            print(f"[Exa] Sync enrichment failed: {e}")
            return []
