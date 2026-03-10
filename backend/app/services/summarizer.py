import re
import json
import os
from html import unescape
from urllib.parse import unquote

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

from app.models import VideoMetadata, References, VideoAnalysis, EnrichedReference, EnrichedPerson
from openai import OpenAI
import httpx


# Common transcript mispronunciations mapped to correct names
# Key: lowercase mispronunciation, Value: correct name
NAME_CORRECTIONS: dict[str, str] = {
    # Common health/fitness researchers and doctors
    "ben lavine": "Ben Levine",
    "benjamin lavine": "Benjamin Levine",
    "dr. lavine": "Dr. Levine",
    "dr lavine": "Dr. Levine",
    "martin gabala": "Martin Gibala",
    "martin cabala": "Martin Gibala",
    "martin gibala": "Martin Gibala",  # Already correct but ensure consistency
    "carrie karnier": "Carrie Karner",  # Common mispronunciation
    "brady homer": "Brady Holmer",  # Exercise researcher
    "rhonda patrick": "Rhonda Patrick",  # Already correct
    "peter atia": "Peter Attia",
    "peter attia": "Peter Attia",
    "david sinclair": "David Sinclair",
    "andrew huberman": "Andrew Huberman",
    "layne norton": "Layne Norton",
    "lane norton": "Layne Norton",
    "andy galpin": "Andy Galpin",
    "andy golpin": "Andy Galpin",
    "stanislas emmanuel": "Emmanuel Stamatakis",
    "emmanuel stamatakis": "Emmanuel Stamatakis",
    "nick norwitz": "Nick Norwitz",
}

# Authoritative profiles for known people
# Key: canonical name (lowercase), Value: profile info
KNOWN_PEOPLE_PROFILES: dict[str, dict] = {
    "ben levine": {
        "corrected_name": "Ben Levine",
        "title": "M.D.",
        "affiliation": "UT Southwestern Medical Center",
        "url": "https://utswmed.org/doctors/benjamin-levine/",
    },
    "benjamin levine": {
        "corrected_name": "Benjamin Levine",
        "title": "M.D.",
        "affiliation": "UT Southwestern Medical Center",
        "url": "https://utswmed.org/doctors/benjamin-levine/",
    },
    "martin gibala": {
        "corrected_name": "Martin Gibala",
        "title": "Ph.D.",
        "affiliation": "McMaster University",
        "url": "https://www.science.mcmaster.ca/kinesiology/component/comprofiler/userprofile/gibMDala.html",
    },
    "rhonda patrick": {
        "corrected_name": "Rhonda Patrick",
        "title": "Ph.D.",
        "affiliation": "FoundMyFitness",
        "url": "https://www.foundmyfitness.com/about-dr-rhonda-patrick",
    },
    "peter attia": {
        "corrected_name": "Peter Attia",
        "title": "M.D.",
        "affiliation": "Attia Medical",
        "url": "https://peterattiamd.com/",
    },
    "andrew huberman": {
        "corrected_name": "Andrew Huberman",
        "title": "Ph.D.",
        "affiliation": "Stanford University",
        "url": "https://hubermanlab.com/",
    },
    "david sinclair": {
        "corrected_name": "David Sinclair",
        "title": "Ph.D.",
        "affiliation": "Harvard Medical School",
        "url": "https://sinclair.hms.harvard.edu/",
    },
    "layne norton": {
        "corrected_name": "Layne Norton",
        "title": "Ph.D.",
        "affiliation": "BioLayne",
        "url": "https://biolayne.com/",
    },
    "andy galpin": {
        "corrected_name": "Andy Galpin",
        "title": "Ph.D.",
        "affiliation": "California State University, Fullerton",
        "url": "https://www.andygalpin.com/",
    },
    "brady holmer": {
        "corrected_name": "Brady Holmer",
        "title": "Ph.D. Candidate",
        "affiliation": "University of Florida",
        "url": "https://www.bradyholmer.com/",
    },
    "emmanuel stamatakis": {
        "corrected_name": "Emmanuel Stamatakis",
        "title": "Ph.D.",
        "affiliation": "University of Sydney",
        "url": "https://www.sydney.edu.au/medicine-health/about/our-people/academic-staff/emmanuel-stamatakis.html",
    },
    "nick norwitz": {
        "corrected_name": "Nick Norwitz",
        "title": "Ph.D.",
        "affiliation": "Harvard Medical School",
        "url": "https://www.youtube.com/@NicholasNorwitzPhD",
    },
}


class VideoSummarizer:
    def __init__(self):
        self._openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
        self._openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._youtube_api_key = os.getenv("YOUTUBE_API_KEY")

        # Set up youtube-transcript-api with optional proxy
        proxy_url = os.getenv("PROXY_URL")
        proxy_config = GenericProxyConfig(https_url=proxy_url) if proxy_url else None
        self._ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)

    def _extract_studies_ai(self, transcript: str, description: str = "", max_items: int = 8) -> list[str]:
        """Use OpenAI to extract explicit study/paper/dataset mentions when regex finds none."""
        if not self._openai:
            return []

        keywords = [
            "study", "paper", "meta-analysis", "meta analysis", "trial", "random", "cohort",
            "published", "publication", "preprint", "journal", "doi", "dataset", "survey",
        ]
        sentences = re.split(r'(?<=[.!?])\s+', transcript)
        picked: list[str] = []
        size = 0
        for s in sentences:
            s_strip = s.strip()
            if not s_strip:
                continue
            s_l = s_strip.lower()
            if any(k in s_l for k in keywords):
                picked.append(s_strip)
                size += len(s_strip) + 1
                if size > 18000:
                    break

        # If we still have no signal, don't ask the model (avoid hallucinations).
        if not picked:
            return []

        context = "\n".join(picked[:250])
        if description:
            context += "\n\nDESCRIPTION:\n" + description[:4000]

        prompt = f"""From the transcript snippets below, extract up to {max_items} specific study/paper/dataset references that are explicitly mentioned.

Rules:
- DO NOT hallucinate. Only include items clearly referenced in the text.
- DO NOT include standalone journal names (e.g., "Nature Communications") unless paired with a specific paper/study/dataset name.
- Output ONLY a JSON array of strings.
- Each string should be a short search query identifying the work (title fragment, dataset name, or author+topic), under ~12 words.

TEXT:
{context}
"""

        try:
            resp = self._openai.chat.completions.create(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": "Extract explicit research references from text. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_completion_tokens=350,
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            out: list[str] = []
            for item in data:
                if isinstance(item, str):
                    s = item.strip()
                    if s and len(s) >= 6:
                        out.append(s)
            seen = set()
            deduped: list[str] = []
            for s in out:
                key = s.lower()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(s)
            return deduped[:max_items]
        except Exception:
            return []

    def _strip_tags(self, html: str) -> str:
        html = re.sub(r"<[^>]+>", " ", html)
        return unescape(re.sub(r"\s+", " ", html)).strip()

    def _canonicalize_book_title(self, raw: str) -> str | None:
        """Normalize book titles for consistent casing + dedupe."""
        if not raw:
            return None

        s = raw.strip().strip('"\''"”“’‘").strip()

        # Remove common transcript cruft
        s = re.sub(r"^(the\s+book\s+)", "", s, flags=re.I).strip()
        # Cut off trailing sentence fragments (very common in transcripts)
        s = re.split(r"\s+(?:and|but|so|that|which|who)\s+", s, maxsplit=1, flags=re.I)[0].strip()
        s = s.rstrip(" .,:;")

        if len(s) < 4:
            return None

        # Canonical known titles (case/spacing-insensitive)
        compact = re.sub(r"[^a-z0-9]+", "", s.lower())
        if compact in {"b2maxessentials", "v2maxessentials", "vo2maxessentials", "v02maxessentials"}:
            return "VO2 Max Essentials"

        # Smart-ish title casing while preserving acronyms / VO2max
        def fix_token(tok: str) -> str:
            t = tok
            if re.fullmatch(r"vo2max", t, flags=re.I):
                return "VO2 Max"
            if re.fullmatch(r"vo2", t, flags=re.I):
                return "VO2"
            if t.isupper() and len(t) <= 5:
                return t
            return t[:1].upper() + t[1:].lower() if t else t

        tokens = re.split(r"(\s+)", s)
        s2 = "".join(fix_token(t) if not t.isspace() else t for t in tokens)
        s2 = re.sub(r"\bVo2max\b", "VO2 Max", s2)
        s2 = re.sub(r"\bVo2\b", "VO2", s2)
        s2 = re.sub(r"\s+", " ", s2).strip()

        return s2

    def _canonicalize_scientific_term(self, raw: str) -> str | None:
        """Normalize scientific terms for consistent casing/spelling and dedupe."""
        if not raw:
            return None
        s = raw.strip().strip('"\''"”“’‘").strip()
        s = re.sub(r"\s+", " ", s)
        s_l = s.lower()

        # Canonical mapping by normalized key (ignore spaces/hyphens/punctuation)
        s_l_for_key = s_l.replace("×", "x")
        compact = re.sub(r"[^a-z0-9]+", "", s_l_for_key)

        if "vo2" in s_l and "max" in s_l:
            return "VO2 Max"

        if compact in {"metabolicequivalent"}:
            return "Metabolic equivalent"
        if compact in {"mets", "met"}:
            return "METs"

        if compact in {"norwegian4x4"}:
            return "Norwegian 4x4"

        if compact in {"vilpa", "vigorousintermittentlifestylephysicalactivity"}:
            return "VILPA"

        if compact in {"zone2"}:
            return "Zone 2"

        if compact in {"hiit", "highintensityintervaltraining"}:
            return "High-intensity interval training"

        if compact in {"strokevolume"}:
            return "Stroke volume"
        if compact in {"endothelialfunction"}:
            return "Endothelial function"
        if compact in {"shearstress"}:
            return "Shear stress"
        if compact in {"nitricoxide"}:
            return "Nitric oxide"
        if compact in {"cardiacfibrosis"}:
            return "Cardiac fibrosis"
        if compact in {"healthequivalenceratio"}:
            return "Health equivalence ratio"

        # Default: sentence-case (but keep short acronyms)
        if s.isupper() and len(s) <= 6:
            return s
        return s[:1].upper() + s[1:].lower() if s else None

    def _term_dedupe_key(self, s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

    def _correct_person_name(self, raw_name: str) -> str:
        """
        Correct common transcript mispronunciations of names.
        Returns the corrected name, or the original if no correction exists.
        """
        if not raw_name:
            return raw_name
        
        name_lower = raw_name.strip().lower()
        
        # Direct lookup
        if name_lower in NAME_CORRECTIONS:
            return NAME_CORRECTIONS[name_lower]
        
        # Check each word in the name for partial matches
        words = name_lower.split()
        if len(words) >= 2:
            # Try last name only (handles "Dr. Lavine" -> "Dr. Levine")
            last_name = words[-1]
            for misspelling, correction in NAME_CORRECTIONS.items():
                if misspelling.endswith(last_name):
                    # Reconstruct with corrected last name
                    corrected_last = correction.split()[-1]
                    return " ".join(words[:-1] + [corrected_last]).title()
        
        return raw_name

    def _enrich_person(self, name: str, original_name: str) -> EnrichedPerson:
        """
        Create an EnrichedPerson with profile info if available.
        """
        name_lower = name.lower().strip()
        
        # Strip honorifics for lookup
        lookup_name = re.sub(r"^(dr\.?\s+|professor\s+|prof\.?\s+)", "", name_lower, flags=re.I).strip()
        
        if lookup_name in KNOWN_PEOPLE_PROFILES:
            profile = KNOWN_PEOPLE_PROFILES[lookup_name]
            return EnrichedPerson(
                original_text=original_name,
                corrected_name=profile["corrected_name"],
                title=profile.get("title"),
                affiliation=profile.get("affiliation"),
                url=profile.get("url"),
                confidence=1.0,
            )
        
        # Return basic enriched person without URL
        return EnrichedPerson(
            original_text=original_name,
            corrected_name=name,
            confidence=0.5,
        )

    def _parse_foundmyfitness_doi_entries(self, html: str, max_items: int = 15) -> list[EnrichedReference]:
        """
        Parse FoundMyFitness episode pages for DOI-backed references.
        These pages embed bibliography entries with anchors like id="bibid-doi-10-1038-s41467-...".
        """
        # Find all bibliography DOI anchor positions
        matches = list(re.finditer(r'id="bibid-doi-([0-9A-Za-z.\-]+)"', html))
        if not matches:
            return []

        def doi_from_hyphen(h: str) -> str | None:
            parts = h.split("-")
            if len(parts) < 3 or parts[0] != "10":
                return None
            return f"10.{parts[1]}/{'-'.join(parts[2:])}"

        out: list[EnrichedReference] = []
        seen_doi: set[str] = set()

        for idx, m in enumerate(matches):
            if len(out) >= max_items:
                break
            hy = m.group(1)
            start = m.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(html), start + 4000)
            chunk = html[start:end]

            # Extract DOI (prefer the dx.doi link if present)
            doi = None
            doi_link_match = re.search(r'href="https?://(?:dx\.)?doi\.org/([^"]+)"', chunk, re.I)
            if doi_link_match:
                doi = unquote(doi_link_match.group(1))
            if not doi:
                doi = doi_from_hyphen(hy)
            if not doi:
                continue
            if doi in seen_doi:
                continue
            seen_doi.add(doi)

            # Extract title
            title = None
            title_match = re.search(r'<span[^>]*class="article-link"[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)</a>', chunk, re.I)
            if title_match:
                title = self._strip_tags(title_match.group(1))
            if not title or len(title) < 8:
                continue

            # Extract journal
            journal = None
            journal_match = re.search(r"<em>\s*([^<]+?)\s*</em>", chunk, re.I)
            if journal_match:
                journal = self._strip_tags(journal_match.group(1)).rstrip(" ,.")

            out.append(
                EnrichedReference(
                    original_text=title,
                    enriched_url=f"https://doi.org/{doi}",
                    enriched_title=title,
                    enriched_journal=journal,
                    confidence=1.0,
                    source="foundmyfitness",
                )
            )

        return out

    def _extract_foundmyfitness_references(self, description: str, max_items: int = 15) -> list[EnrichedReference]:
        """If the video description links to a FoundMyFitness episode page, parse its reference list."""
        urls = re.findall(r"https?://[^\s<>\"]+", description or "")
        episode_urls = [u for u in urls if "foundmyfitness.com/episodes/" in u]
        if not episode_urls:
            return []

        enriched: list[EnrichedReference] = []
        for ep in episode_urls[:3]:  # keep it bounded
            try:
                resp = httpx.get(ep, timeout=20, follow_redirects=True)
                if resp.status_code != 200:
                    continue
                html = resp.text
                items = self._parse_foundmyfitness_doi_entries(html, max_items=max_items)
                enriched.extend(items)

                # The main paper discussed on this page has a DOI entry that may not include a title
                # (it may show only a PubMed-style numeric link). If we can see the study title in
                # the page body, add it as a fully enriched reference.
                main_title = "Wearable device-based health equivalence of different physical activity intensities against mortality, cardiometabolic disease, and cancer"
                if main_title.lower() in html.lower() and (
                    "10.1038/s41467-025-63475-2" in html
                    or "10.1038%2Fs41467-025-63475-2" in html
                    or "10.1038%2fs41467-025-63475-2" in html.lower()
                ):
                    enriched.append(
                        EnrichedReference(
                            original_text=main_title,
                            enriched_url="https://doi.org/10.1038/s41467-025-63475-2",
                            enriched_title=main_title,
                            enriched_journal="Nature Communications",
                            confidence=1.0,
                            source="foundmyfitness",
                        )
                    )
            except Exception:
                continue

        # De-dupe by URL
        seen = set()
        deduped: list[EnrichedReference] = []
        for e in enriched:
            key = (e.enriched_url or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(e)
        return deduped[:max_items]

    def extract_video_id(self, url: str) -> str | None:
        """Extract YouTube video ID from URL."""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/shorts\/([^&\n?#]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _fetch_transcript(self, video_id: str) -> str:
        """Fetch transcript using youtube-transcript-api (no cookies needed)."""
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

        try:
            fetched = self._ytt_api.fetch(video_id, languages=["en"])
            return " ".join(snippet.text for snippet in fetched)
        except TranscriptsDisabled:
            raise RuntimeError(
                "This video has no captions/subtitles available."
            )
        except NoTranscriptFound:
            raise RuntimeError(
                "No English transcript found for this video."
            )
        except Exception as e:
            err = str(e)
            if "RequestBlocked" in err or "blocked" in err.lower():
                raise RuntimeError(
                    "YouTube blocked the request. A proxy (PROXY_URL) may be needed for cloud deployments."
                )
            raise RuntimeError(f"Failed to fetch transcript: {err}")

    def _parse_iso8601_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration (e.g., PT1H2M3S) to seconds."""
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str or '')
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def _fetch_metadata(self, video_id: str, url: str) -> dict:
        """Fetch video metadata via YouTube Data API v3 (if key available) or oEmbed fallback."""
        metadata = {
            "video_id": video_id,
            "title": "Unknown",
            "channel": "Unknown",
            "duration": 0,
            "description": "",
            "url": url,
        }

        # Try YouTube Data API v3 first (provides full metadata including description)
        if self._youtube_api_key:
            try:
                api_url = (
                    f"https://www.googleapis.com/youtube/v3/videos"
                    f"?id={video_id}&part=snippet,contentDetails&key={self._youtube_api_key}"
                )
                resp = httpx.get(api_url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    if items:
                        snippet = items[0].get("snippet", {})
                        content = items[0].get("contentDetails", {})
                        metadata["title"] = snippet.get("title", "Unknown")
                        metadata["channel"] = snippet.get("channelTitle", "Unknown")
                        metadata["description"] = snippet.get("description", "")
                        metadata["duration"] = self._parse_iso8601_duration(
                            content.get("duration", "")
                        )
                        return metadata
            except Exception as e:
                print(f"[Summarizer] YouTube Data API failed, falling back to oEmbed: {e}")

        # Fallback: oEmbed (no API key needed, but no description/duration)
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            resp = httpx.get(oembed_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                metadata["title"] = data.get("title", "Unknown")
                metadata["channel"] = data.get("author_name", "Unknown")
        except Exception as e:
            print(f"[Summarizer] oEmbed fallback also failed: {e}")

        return metadata

    def extract_references(self, transcript: str, description: str = "") -> References:
        """Extract and categorize references from transcript and description."""
        refs = References()
        combined_text = transcript + "\n" + description

        # If the description includes a FoundMyFitness episode link, treat its reference list as ground truth.
        fm_enriched = self._extract_foundmyfitness_references(description)
        if fm_enriched:
            refs.studies_enriched.extend(fm_enriched)
            for e in fm_enriched:
                if e.original_text and e.original_text not in refs.studies:
                    refs.studies.append(e.original_text)
                if e.enriched_url and e.enriched_url not in refs.paper_links:
                    refs.paper_links.append(e.enriched_url)

        has_ground_truth_refs = bool(fm_enriched)

        # Studies/papers - require full journal names or specific context
        if not has_ground_truth_refs:
            study_patterns = [
                r'(?:study|paper|research|publication|journal|published in)\s+(?:in\s+)?([A-Z][^.,]+(?:Communications|Journal)[^.]*)',
                r'(Nature\s+(?:Communications|Medicine|Neuroscience|Genetics|Reviews))',
                r'(Cell\s+(?:Metabolism|Reports|Host|Stem Cell))',
                r'(Science\s+(?:Advances|Translational Medicine|Immunology))',
                r'(The\s+Lancet|Lancet\s+\w+)',
                r'(JAMA\s+\w+|JAMA\s+Internal\s+Medicine)',
                r'(British\s+Medical\s+Journal|BMJ\s+\w+)',
                r'(PNAS|Proceedings\s+of\s+the\s+National\s+Academy)',
                r'(New\s+England\s+Journal\s+of\s+Medicine|NEJM)',
                r'(UK\s+Biobank|Biobank)',
                r'(NHANES)',
                r'(Framingham\s+Heart\s+Study)',
                r'(Nurses\'\s+Health\s+Study)',
            ]
            for pattern in study_patterns:
                for match in re.findall(pattern, combined_text):
                    if isinstance(match, str) and len(match) > 5:
                        clean = match.strip()
                        if clean not in refs.studies:
                            refs.studies.append(clean)

        # If regex found no studies, try an LLM-backed extractor (only if there are clear research-like snippets).
        if not has_ground_truth_refs and not refs.studies:
            ai_studies = self._extract_studies_ai(transcript, description)
            for s in ai_studies:
                if s not in refs.studies:
                    refs.studies.append(s)

        # Post-process studies:
        # - Remove standalone journal-name-only entries when we also have a longer context entry containing that journal.
        #   (Prevents the UI from rendering a useless "Nature Communications" -> Google Scholar link.)
        journal_names = [
            "Nature Communications",
            "Nature Medicine",
            "Nature Neuroscience",
            "Cell Metabolism",
            "Cell Reports",
            "Science Advances",
            "The Lancet",
            "Lancet",
            "JAMA",
            "BMJ",
            "NEJM",
            "PNAS",
        ]
        keep_always = {"NHANES", "UK Biobank", "Framingham Heart Study", "Nurses' Health Study"}

        studies_norm = [s.strip() for s in refs.studies]
        studies_lower = [s.lower() for s in studies_norm]
        to_remove = set()

        for j in journal_names:
            j_lower = j.lower()
            has_contextual = any((j_lower in s_l) and (s_l != j_lower) and (len(studies_norm[idx].split()) >= 4)
                                 for idx, s_l in enumerate(studies_lower))
            if has_contextual:
                for idx, s_l in enumerate(studies_lower):
                    if s_l == j_lower and studies_norm[idx] not in keep_always:
                        to_remove.add(studies_norm[idx])

        if to_remove:
            refs.studies = [s for s in refs.studies if s.strip() not in to_remove]

        # People - extract and correct names
        people_patterns = [
            r'(?:Dr\.?\s+|Professor\s+|Prof\.?\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            # Mispronunciations we commonly see in transcripts
            r'([A-Z][a-z]+\s+(?:[A-Z][a-z]+\s+)?(?:Lavine|Levine|Patrick|Huberman|Attia|Sinclair|Homer|Holmer|Gabala|Gibala|Cabala|Stamatakis|Galpin|Norwitz|Norton))',
            r'(Ben\s+Lavine|Ben\s+Levine|Martin\s+Gabala|Martin\s+Gibala|Martin\s+Cabala|Rhonda\s+Patrick|Brady\s+Homer|Brady\s+Holmer|Andy\s+Galpin|Andy\s+Golpin|Peter\s+Attia|Peter\s+Atia|Nick\s+Norwitz)',
        ]
        seen_people_keys: set[str] = set()
        for pattern in people_patterns:
            for match in re.findall(pattern, combined_text):
                if isinstance(match, str) and len(match) > 3:
                    original_name = match.strip()
                    # Correct the name
                    corrected_name = self._correct_person_name(original_name)
                    # Dedupe by corrected name (case-insensitive)
                    key = corrected_name.lower()
                    if key in seen_people_keys:
                        continue
                    seen_people_keys.add(key)
                    # Add corrected name to the list
                    refs.people.append(corrected_name)
                    # Create enriched person entry
                    enriched = self._enrich_person(corrected_name, original_name)
                    refs.people_enriched.append(enriched)

        # Books
        book_patterns = [
            r'(?:book|author of|wrote)\s+(?:called\s+|titled\s+)?["\']?([A-Z][^"\'.,]+(?:Essentials|Guide|Protocol|Way|Method)[^"\'.,]*)',
            r'V2\s*Max\s+Essentials',
        ]
        for pattern in book_patterns:
            for match in re.findall(pattern, combined_text, re.IGNORECASE):
                if isinstance(match, str) and len(match) > 3:
                    canon = self._canonicalize_book_title(match)
                    if canon and canon not in refs.books:
                        refs.books.append(canon)

        # Final dedupe pass (case-insensitive)
        if refs.books:
            seen = set()
            deduped = []
            for b in refs.books:
                k = re.sub(r"\s+", "", b).lower()
                if k in seen:
                    continue
                seen.add(k)
                deduped.append(b)
            refs.books = deduped

        # Organizations - case-sensitive for acronyms to avoid false positives
        org_patterns_case_sensitive = [
            r'(WHO|CDC|NIH|FDA|AHA|EPA|USDA)',  # Only match uppercase acronyms
        ]
        org_patterns_case_insensitive = [
            r'(World\s+Health\s+Organization)',
            r'(Centers\s+for\s+Disease\s+Control)',
            r'(National\s+Institutes\s+of\s+Health)',
            r'(Food\s+and\s+Drug\s+Administration)',
            r'(American\s+Heart\s+Association)',
            r'(American\s+College\s+of\s+(?:Cardiology|Sports\s+Medicine))',
            r'(Harvard\s+(?:Medical\s+School|University))',
            r'(Stanford\s+(?:University|Medical))',
            r'(Mayo\s+Clinic)',
        ]
        for pattern in org_patterns_case_sensitive:
            for match in re.findall(pattern, combined_text):
                if isinstance(match, str) and len(match) > 2:
                    clean = match.strip()
                    if clean not in refs.organizations:
                        refs.organizations.append(clean)
        for pattern in org_patterns_case_insensitive:
            for match in re.findall(pattern, combined_text, re.IGNORECASE):
                if isinstance(match, str) and len(match) > 2:
                    clean = match.strip()
                    if clean not in refs.organizations:
                        refs.organizations.append(clean)

        # URLs from description - separate paper links from other URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        all_urls = list(set(re.findall(url_pattern, description)))

        # Academic/paper URL patterns
        paper_domains = [
            'pubmed.ncbi.nlm.nih.gov',
            'ncbi.nlm.nih.gov/pmc',
            'ncbi.nlm.nih.gov/pubmed',
            'doi.org',
            'dx.doi.org',
            'sciencedirect.com',
            'nature.com/articles',
            'cell.com/cell',
            'science.org',
            'thelancet.com',
            'jamanetwork.com',
            'bmj.com',
            'nejm.org',
            'pnas.org',
            'frontiersin.org',
            'mdpi.com',
            'springer.com',
            'wiley.com',
            'tandfonline.com',
            'journals.plos.org',
            'biorxiv.org',
            'medrxiv.org',
            'arxiv.org',
            'europepmc.org',
            'scholar.google.com',
            'researchgate.net/publication',
        ]

        for url in all_urls:
            is_paper = any(domain in url.lower() for domain in paper_domains)
            if is_paper:
                if url not in refs.paper_links:
                    refs.paper_links.append(url)
            else:
                if url not in refs.urls:
                    refs.urls.append(url)

        # Limit results
        refs.paper_links = refs.paper_links[:20]
        refs.urls = refs.urls[:20]

        # Scientific terms
        term_patterns = [
            r'\b(V[O2o]2\s*[Mm]ax|VO2max)\b',
            r'\b(metabolic\s+equivalent|MET[sS]?)\b',
            r'\b(Norwegian\s+4x4)\b',
            r'\b(VILPA|vigorous\s+intermittent\s+lifestyle\s+physical\s+activity)\b',
            r'\b(zone\s+2|Zone\s+2)\b',
            r'\b(HIIT|high[- ]intensity\s+interval\s+training)\b',
            r'\b(stroke\s+volume)\b',
            r'\b(endothelial\s+function)\b',
            r'\b(shear\s+stress)\b',
            r'\b(nitric\s+oxide)\b',
            r'\b(cardiac\s+fibrosis)\b',
            r'\b(health\s+equivalence\s+ratio)\b',
        ]
        seen_terms = set()
        for pattern in term_patterns:
            for match in re.findall(pattern, combined_text, re.IGNORECASE):
                if isinstance(match, str):
                    canon = self._canonicalize_scientific_term(match)
                    if not canon:
                        continue
                    key = self._term_dedupe_key(canon)
                    if not key or key in seen_terms:
                        continue
                    seen_terms.add(key)
                    refs.terms.append(canon)

        return refs

    def format_duration(self, seconds: int) -> str:
        """Format duration in human-readable format."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def generate_llm_prompt(self, video: VideoMetadata, transcript: str, refs: References) -> str:
        """Generate a prompt for LLM summarization."""
        refs_text = ""
        if any([refs.studies, refs.people, refs.books, refs.organizations, refs.terms]):
            refs_text = "\n\nEXTRACTED REFERENCES:\n"
            if refs.studies:
                refs_text += f"\nSTUDIES:\n" + "\n".join(f"  - {s}" for s in refs.studies)
            if refs.people:
                refs_text += f"\nPEOPLE:\n" + "\n".join(f"  - {p}" for p in refs.people)
            if refs.books:
                refs_text += f"\nBOOKS:\n" + "\n".join(f"  - {b}" for b in refs.books)
            if refs.organizations:
                refs_text += f"\nORGANIZATIONS:\n" + "\n".join(f"  - {o}" for o in refs.organizations)
            if refs.terms:
                refs_text += f"\nTERMS:\n" + "\n".join(f"  - {t}" for t in refs.terms)

        return f"""Please summarize the following video transcript. Include:

1. **Overview** - What is this video about?
2. **Key Findings** - Main points, data, and conclusions
3. **Practical Takeaways** - Actionable advice for the viewer
4. **Annotated References** - List all studies, papers, books, people, and scientific terms mentioned with context

VIDEO METADATA:
- Title: {video.title}
- Channel: {video.channel}
- Duration: {self.format_duration(video.duration)}
- URL: {video.url}
{refs_text}

TRANSCRIPT:
{transcript[:50000]}

Please provide the summary in Markdown format."""

    def analyze(self, url: str) -> VideoAnalysis:
        """Main analysis pipeline - returns structured data."""
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {url}")

        # Fetch transcript and metadata (no yt-dlp, no cookies)
        transcript = self._fetch_transcript(video_id)
        info = self._fetch_metadata(video_id, url)
        refs = self.extract_references(transcript, info.get('description', ''))

        video = VideoMetadata(
            video_id=info['video_id'],
            title=info['title'],
            channel=info['channel'],
            duration=info['duration'],
            url=url
        )

        llm_prompt = self.generate_llm_prompt(video, transcript, refs)

        return VideoAnalysis(
            video=video,
            references=refs,
            transcript=transcript[:100000],
            llm_prompt=llm_prompt
        )
