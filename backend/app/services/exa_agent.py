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
import json
import json


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
        "skip to main content",
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

def _strip_markdown_link(text: str) -> str:
    """
    Convert Markdown link like "[label](url)" to "label".
    If it doesn't look like a markdown link, return unchanged.
    """
    if not text:
        return text
    t = text.strip()
    if t.startswith("[") and "](" in t and t.endswith(")"):
        try:
            label = t[1:t.index("](")]
            return label.strip() or t
        except Exception:
            return t
    return t

def is_garbage_title(title: str) -> bool:
    """Detect navigation/boilerplate titles that should never be used as paper titles."""
    if not title:
        return True
    t = _strip_markdown_link(title).strip().lower()
    if not t:
        return True
    garbage_patterns = [
        "skip to main content",
        "skip to content",
        "skip to navigation",
        "skip to search",
        "home",
        "search",
        "browse",
    ]
    if any(p == t for p in garbage_patterns):
        return True
    if "skip to main content" in t:
        return True
    return False

def clean_title_and_journal(title: str) -> tuple[str, Optional[str]]:
    """Clean up article titles from Exa results and extract journal/source when present."""
    if not title:
        return title, None

    # Exa 'text' sometimes yields markdown links like "[Skip to main content](...)"
    title = _strip_markdown_link(title)

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

    def _refine_chat_queries(
        self,
        user_message: str,
        video_title: str = "",
        studies_hint: Optional[list[str]] = None,
        keywords_hint: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Turn a long user instruction ("summarise X and use exa.ai to find refs")
        into a small set of focused academic search queries suitable for Exa.
        """
        msg = (user_message or "").strip()
        if not msg:
            return []

        # Without OpenAI we can't reliably extract multiple focused sub-queries.
        if not self.openai_client:
            # Heuristic: strip common instruction phrases and keep first chunk.
            lowered = msg.lower()
            for needle in ["use exa.ai", "use exa", "exa.ai", "exa"]:
                lowered = lowered.replace(needle, "")
            cleaned = " ".join(lowered.split())
            return [cleaned[:120] or msg[:120]]

        try:
            studies_hint = studies_hint or []
            studies_hint = [s for s in studies_hint if s and len(s.strip()) > 6][:12]
            keywords_hint = keywords_hint or []
            keywords_hint = [k for k in keywords_hint if k and len(k.strip()) > 2][:20]

            prompt = {
                "user_message": msg,
                "video_title": (video_title or "").strip(),
                "studies_hint": studies_hint,
                "keywords_hint": keywords_hint,
            }

            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate academic paper search queries.\n"
                            "Given a user request about a video, output a JSON array (3-5 items) of short search queries.\n"
                            "Rules:\n"
                            "- Each query should target a single claim/topic (max 10-12 words)\n"
                            "- Remove instruction words like 'summarise', 'headlines', 'use exa'\n"
                            "- Prefer terms that identify the study/cohort/trial (e.g., 'Framingham omega-3 index mortality')\n"
                            "- If the user asks for 'lifestyle changes with significant benefit', pick 3-5 likely headline claims.\n"
                            "- Prefer to incorporate any provided keywords_hint when relevant (e.g. 'sulforaphane', 'COSMOS multivitamin').\n"
                            "- Output ONLY valid JSON (an array of strings), nothing else."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                temperature=0.2,
            )

            raw = response.choices[0].message.content.strip()
            queries = json.loads(raw)
            if not isinstance(queries, list):
                return []
            cleaned_queries: list[str] = []
            for q in queries:
                if not isinstance(q, str):
                    continue
                q2 = " ".join(q.split()).strip()
                if len(q2) < 6:
                    continue
                cleaned_queries.append(q2[:160])
            # Dedup while preserving order
            seen = set()
            out: list[str] = []
            for q in cleaned_queries:
                k = q.lower()
                if k in seen:
                    continue
                seen.add(k)
                out.append(q)
            return out[:5]
        except Exception as e:
            print(f"[Exa/AI] Chat query refinement failed: {e}")
            return []

    async def _search_exa(
        self,
        query: str,
        num_results: int = 8,
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
    ) -> list[dict]:
        """Raw Exa search returning result dicts (url/title/text/score)."""
        if not self.enabled or not query:
            return []
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/search",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=(
                    {
                        "query": query,
                        "numResults": num_results,
                        "type": "auto",
                        "contents": {"text": {"maxCharacters": 2000}},
                        **({"includeDomains": include_domains} if include_domains else {}),
                        **({"excludeDomains": exclude_domains} if exclude_domains else {}),
                    }
                ),
            )
            if response.status_code != 200:
                print(f"[Exa] Search failed {response.status_code}: {response.text[:200]}")
                return []
            data = response.json()
            return data.get("results", []) or []

    def _results_to_papers(self, user_query: str, results: list[dict], max_items: int) -> list[EnrichedReference]:
        """Convert Exa results into EnrichedReference list using our filtering/cleanups."""
        candidates: list[EnrichedReference] = []
        for result in results:
            url = result.get("url", "")
            title = result.get("title", "")
            text_content = result.get("text", "")

            if not url or _is_google_url(url):
                continue
            if not is_specific_article(url, title):
                continue

            candidate_title = title
            if (("..." in title) or ("…" in title)) and text_content:
                first_line = text_content.split('\n')[0].strip()
                if first_line and len(first_line) < 240 and not is_garbage_title(first_line):
                    candidate_title = first_line

            cleaned, journal = clean_title_and_journal(candidate_title)
            if is_garbage_title(cleaned):
                continue

            candidates.append(
                EnrichedReference(
                    original_text=user_query,
                    enriched_url=url,
                    enriched_title=cleaned,
                    enriched_journal=journal or infer_source_from_url(url),
                    confidence=min(result.get("score", 0.5), 1.0),
                    source="exa",
                )
            )
            if len(candidates) >= max_items:
                break

        return candidates

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
                                    # Only use text-derived titles if they don't look like navigation/boilerplate.
                                    if not is_garbage_title(first_line):
                                        candidate_title = first_line

                        # Clean up the title + extract journal/source
                        cleaned, journal = clean_title_and_journal(candidate_title)

                        # If title looks truncated, try to extract from text content
                        if cleaned.endswith('...') or cleaned.endswith('…') or len(cleaned) < 20:
                            # Try to get better title from text content (first line often has title)
                            if text_content:
                                first_line = text_content.split('\n')[0].strip()
                                if (
                                    len(first_line) > len(cleaned)
                                    and len(first_line) < 200
                                    and not is_garbage_title(first_line)
                                ):
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

    async def search_papers(self, query: str, max_items: int = 3) -> list[EnrichedReference]:
        """
        Search Exa for likely academic papers for an arbitrary query.
        Intended for chat-time citation lookup ("which paper is that?").
        """
        if not self.enabled or not query:
            return []

        q = query.strip()
        if len(q) > 240:
            q = q[:240]

        # Bias toward academic intent without mangling user query too much
        search_query = q if any(tok in q.lower() for tok in ["pmid", "doi", "randomized", "randomised", "trial", "cohort"]) else f"{q} study"
        print(f"[Exa] Chat-searching: '{search_query}'")

        try:
            results = await self._search_exa(search_query, num_results=10)
            # If Exa returns nothing at all, continue to PubMed fallback (and other fallbacks below)
            # instead of bailing out early.

            candidates = self._results_to_papers(query, results or [], max_items=max_items)

            # If nothing, try Exa's native domain filtering (more reliable than "site:" operators).
            # See: https://docs.exa.ai/changelog/domain-path-filter
            if not candidates:
                focused_results = await self._search_exa(
                    q,
                    num_results=12,
                    include_domains=[
                        "https://pubmed.ncbi.nlm.nih.gov",
                        "https://pmc.ncbi.nlm.nih.gov",
                        "https://ncbi.nlm.nih.gov",
                        "https://www.sciencedirect.com",
                    ],
                )
                candidates.extend(self._results_to_papers(query, focused_results, max_items=max_items))

            # Last resort: relax domain restriction but keep non-Google + specific-article checks.
            if not candidates:
                relaxed: list[EnrichedReference] = []
                for r in results:
                    url = r.get("url", "")
                    title = r.get("title", "")
                    if not url or _is_google_url(url) or not is_specific_article(url, title):
                        continue
                    cleaned, journal = clean_title_and_journal(title)
                    if is_garbage_title(cleaned):
                        continue
                    relaxed.append(
                        EnrichedReference(
                            original_text=query,
                            enriched_url=url,
                            enriched_title=cleaned,
                            enriched_journal=journal or infer_source_from_url(url),
                            confidence=min(r.get("score", 0.2), 1.0),
                            source="exa",
                        )
                    )
                    if len(relaxed) >= max_items:
                        break
                candidates = relaxed

            # PubMed fallback: for biomedical claims Exa can return 0 even when PubMed can resolve it.
            if not candidates:
                pubmed = await self._search_pubmed(q, max_items=max_items)
                if pubmed:
                    candidates = pubmed

            print(f"[Exa] Chat-search enriched {len(candidates)} source(s)")
            return candidates[:max_items]

        except httpx.TimeoutException:
            print(f"[Exa] Chat-search timeout: {query[:80]}")
            return []
        except Exception as e:
            print(f"[Exa] Chat-search error: {e}")
            return []

    async def _search_pubmed(self, query: str, max_items: int = 3) -> list[EnrichedReference]:
        """
        PubMed E-utilities fallback for biomedical queries.
        Returns PubMed landing-page URLs with titles/journals when found.
        """
        q = (query or "").strip()
        if not q:
            return []
        if len(q) > 240:
            q = q[:240]

        try:
            # NCBI recommends identifying your tool; also helps with rate-limiting behaviour.
            params_base = {"tool": "video-summarizer", "email": "local@video-summarizer"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                esearch = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={
                        "db": "pubmed",
                        "retmode": "json",
                        "retmax": str(max_items),
                        "term": q,
                        **params_base,
                    },
                )
                if esearch.status_code != 200:
                    return []
                data = esearch.json()
                idlist = (((data or {}).get("esearchresult") or {}).get("idlist") or [])
                pmids = [pid for pid in idlist if isinstance(pid, str) and pid.isdigit()]
                if not pmids:
                    return []

                # Small delay to reduce 429s on bursty traffic
                import asyncio
                await asyncio.sleep(0.35)

                async def fetch_summary():
                    return await client.get(
                        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                        params={
                            "db": "pubmed",
                            "retmode": "json",
                            "id": ",".join(pmids),
                            **params_base,
                        },
                    )

                esummary = await fetch_summary()
                if esummary.status_code == 429:
                    await asyncio.sleep(0.8)
                    esummary = await fetch_summary()
                if esummary.status_code != 200:
                    return []
                sdata = esummary.json()
                result = (sdata or {}).get("result") or {}

                out: list[EnrichedReference] = []
                for pmid in pmids:
                    item = result.get(pmid) or {}
                    title = (item.get("title") or "").strip().rstrip(".")
                    source = (item.get("source") or "").strip()
                    if is_garbage_title(title):
                        continue
                    out.append(
                        EnrichedReference(
                            original_text=query,
                            enriched_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                            enriched_title=title or None,
                            enriched_journal=source or "PubMed",
                            confidence=0.55,
                            source="pubmed",
                        )
                    )
                return out[:max_items]
        except Exception as e:
            print(f"[PubMed] Fallback search error: {e}")
            return []

    def search_papers_sync(self, query: str, max_items: int = 3) -> list[EnrichedReference]:
        """Sync wrapper for search_papers (safe to call from FastAPI endpoints)."""
        import asyncio

        if not self.enabled or not query:
            return []

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.search_papers(query, max_items=max_items))
                    return future.result(timeout=30)
            return loop.run_until_complete(self.search_papers(query, max_items=max_items))
        except RuntimeError:
            return asyncio.run(self.search_papers(query, max_items=max_items))
        except Exception as e:
            print(f"[Exa] Chat-search sync failed: {e}")
            return []

    def refine_chat_queries_sync(
        self,
        user_message: str,
        video_title: str = "",
        studies_hint: Optional[list[str]] = None,
        keywords_hint: Optional[list[str]] = None,
    ) -> list[str]:
        """Sync wrapper around _refine_chat_queries (kept sync to avoid event loop issues)."""
        return self._refine_chat_queries(
            user_message=user_message,
            video_title=video_title,
            studies_hint=studies_hint,
            keywords_hint=keywords_hint,
        )

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
