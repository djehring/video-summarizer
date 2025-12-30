import subprocess
import re
import json
import tempfile
from pathlib import Path

from app.models import VideoMetadata, References, VideoAnalysis


class VideoSummarizer:
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "video-summarizer"
        self.temp_dir.mkdir(exist_ok=True)

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

    def download_subtitles(self, url: str) -> dict:
        """Download subtitles and video metadata using yt-dlp."""
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {url}")

        # Get video info
        info_cmd = ["yt-dlp", "--dump-json", "--skip-download", url]
        result = subprocess.run(info_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to get video info: {result.stderr}")

        video_info = json.loads(result.stdout)

        # Download subtitles
        subtitle_path = self.temp_dir / f"{video_id}"
        sub_cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "-o", str(subtitle_path),
            url
        ]
        subprocess.run(sub_cmd, capture_output=True, text=True)

        # Find the subtitle file
        vtt_files = list(self.temp_dir.glob(f"{video_id}*.vtt"))
        if not vtt_files:
            raise RuntimeError("No subtitle file found. Video may not have captions.")

        return {
            "video_id": video_id,
            "title": video_info.get("title", "Unknown"),
            "channel": video_info.get("channel", "Unknown"),
            "duration": video_info.get("duration", 0),
            "description": video_info.get("description", ""),
            "url": url,
            "subtitle_file": vtt_files[0]
        }

    def parse_vtt(self, vtt_path: Path) -> str:
        """Parse VTT file to extract clean transcript."""
        with open(vtt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        seen_text = set()
        segments = []

        for line in lines:
            if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                continue
            if '-->' in line:
                continue
            if not line.strip() or 'align:' in line or 'position:' in line:
                continue

            clean = re.sub(r'<[^>]+>', '', line).strip()
            clean = clean.replace('&gt;&gt;', '>>').replace('&amp;', '&')

            if clean and clean not in seen_text:
                seen_text.add(clean)
                segments.append(clean)

        return ' '.join(segments)

    def extract_references(self, transcript: str, description: str = "") -> References:
        """Extract and categorize references from transcript and description."""
        refs = References()
        combined_text = transcript + "\n" + description

        # Studies/papers - require full journal names or specific context
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

        # People
        people_patterns = [
            r'(?:Dr\.?\s+|Professor\s+|Prof\.?\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            r'([A-Z][a-z]+\s+(?:[A-Z][a-z]+\s+)?(?:Lavine|Patrick|Huberman|Attia|Sinclair|Homer|Gabala|Stamatakis))',
            r'(Ben\s+Lavine|Martin\s+Gabala|Rhonda\s+Patrick|Brady\s+Homer)',
        ]
        for pattern in people_patterns:
            for match in re.findall(pattern, combined_text):
                if isinstance(match, str) and len(match) > 3:
                    clean = match.strip()
                    if clean not in refs.people and not any(p in clean for p in refs.people):
                        refs.people.append(clean)

        # Books
        book_patterns = [
            r'(?:book|author of|wrote)\s+(?:called\s+|titled\s+)?["\']?([A-Z][^"\'.,]+(?:Essentials|Guide|Protocol|Way|Method)[^"\'.,]*)',
            r'V2\s*Max\s+Essentials',
        ]
        for pattern in book_patterns:
            for match in re.findall(pattern, combined_text, re.IGNORECASE):
                if isinstance(match, str) and len(match) > 3:
                    clean = match.strip()
                    if clean not in refs.books:
                        refs.books.append(clean)

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
        for pattern in term_patterns:
            for match in re.findall(pattern, combined_text, re.IGNORECASE):
                if isinstance(match, str):
                    clean = match.strip()
                    if 'vo2' in clean.lower() or 'v2' in clean.lower():
                        clean = "VO2 max"
                    if clean not in refs.terms:
                        refs.terms.append(clean)

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
        # Download and parse
        info = self.download_subtitles(url)
        transcript = self.parse_vtt(info['subtitle_file'])
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
