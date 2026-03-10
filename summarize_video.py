#!/usr/bin/env python3
"""
Video Summarizer Tool
Extracts transcripts from YouTube videos and generates summaries with annotated references.

Usage:
    python summarize_video.py <youtube_url>
    python summarize_video.py <youtube_url> --output summary.md
"""

import sys
import re
import json
import os
from pathlib import Path
from datetime import datetime

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("Error: youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
    sys.exit(1)

try:
    import httpx
except ImportError:
    httpx = None

class VideoSummarizer:
    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "video-summarizer"
        self.output_dir.mkdir(exist_ok=True)
        self._ytt_api = YouTubeTranscriptApi()
        self._youtube_api_key = os.getenv("YOUTUBE_API_KEY")

    def extract_video_id(self, url: str) -> str:
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

    def _parse_iso8601_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration (e.g., PT1H2M3S) to seconds."""
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str or '')
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def fetch_video_info(self, url: str) -> dict:
        """Fetch transcript and metadata for a YouTube video."""
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {url}")

        # Fetch transcript
        print("Fetching transcript...")
        fetched = self._ytt_api.fetch(video_id, languages=["en"])
        transcript = " ".join(snippet.text for snippet in fetched)

        # Fetch metadata
        print("Fetching metadata...")
        metadata = {"title": "Unknown", "channel": "Unknown", "duration": 0, "description": ""}

        if self._youtube_api_key and httpx:
            try:
                api_url = (
                    f"https://www.googleapis.com/youtube/v3/videos"
                    f"?id={video_id}&part=snippet,contentDetails&key={self._youtube_api_key}"
                )
                resp = httpx.get(api_url, timeout=10)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if items:
                        snippet = items[0].get("snippet", {})
                        content = items[0].get("contentDetails", {})
                        metadata["title"] = snippet.get("title", "Unknown")
                        metadata["channel"] = snippet.get("channelTitle", "Unknown")
                        metadata["description"] = snippet.get("description", "")
                        metadata["duration"] = self._parse_iso8601_duration(content.get("duration", ""))
            except Exception as e:
                print(f"YouTube Data API failed, trying oEmbed: {e}")

        if metadata["title"] == "Unknown" and httpx:
            try:
                oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                resp = httpx.get(oembed_url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    metadata["title"] = data.get("title", "Unknown")
                    metadata["channel"] = data.get("author_name", "Unknown")
            except Exception:
                pass

        return {
            "video_id": video_id,
            "title": metadata["title"],
            "channel": metadata["channel"],
            "duration": metadata["duration"],
            "description": metadata["description"],
            "url": url,
            "transcript": transcript,
        }
    
    def extract_references(self, transcript: str, description: str = "") -> dict:
        """Extract and categorize references from transcript and description."""
        references = {
            "studies": [],
            "people": [],
            "books": [],
            "organizations": [],
            "urls": [],
            "terms": []
        }
        
        combined_text = transcript + "\n" + description
        
        # Extract studies/papers
        study_patterns = [
            r'(?:study|paper|research|publication|journal|published in)\s+(?:in\s+)?([A-Z][^.,]+(?:Communications|Journal|Nature|Science|JAMA|Lancet|BMJ|Cell|PNAS)[^.]*)',
            r'(Nature\s+Communications|Nature\s+Medicine|JAMA|The\s+Lancet|BMJ|Cell|Science|PNAS)[^.]*',
            r'(?:UK\s+)?[Bb]io\s*[Bb]ank',
            r'NHANES',
        ]
        for pattern in study_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and len(match) > 3:
                    clean_match = match.strip()
                    if clean_match not in references["studies"]:
                        references["studies"].append(clean_match)
        
        # Extract people (Dr., PhD, researcher names)
        people_patterns = [
            r'(?:Dr\.?\s+|Professor\s+|Prof\.?\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            r'([A-Z][a-z]+\s+(?:[A-Z][a-z]+\s+)?(?:Lavine|Patrick|Huberman|Attia|Sinclair|Homer|Gabala|Stamatakis))',
            r'(Ben\s+Lavine|Martin\s+Gabala|Rhonda\s+Patrick|Brady\s+Homer)',
        ]
        for pattern in people_patterns:
            matches = re.findall(pattern, combined_text)
            for match in matches:
                if isinstance(match, str) and len(match) > 3:
                    clean_match = match.strip()
                    if clean_match not in references["people"] and not any(p in clean_match for p in references["people"]):
                        references["people"].append(clean_match)
        
        # Extract books
        book_patterns = [
            r'(?:book|author of|wrote)\s+(?:called\s+|titled\s+)?["\']?([A-Z][^"\'.,]+(?:Essentials|Guide|Protocol|Way|Method)[^"\'.,]*)',
            r'V2\s*Max\s+Essentials',
        ]
        for pattern in book_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and len(match) > 3:
                    clean_match = match.strip()
                    if clean_match not in references["books"]:
                        references["books"].append(clean_match)
        
        # Extract organizations
        org_patterns = [
            r'(World\s+Health\s+Organization|WHO|CDC|NIH|FDA|American\s+Heart\s+Association|AHA)',
            r'(UK\s+[Bb]io\s*[Bb]ank|Biobank)',
        ]
        for pattern in org_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and len(match) > 2:
                    clean_match = match.strip()
                    if clean_match not in references["organizations"]:
                        references["organizations"].append(clean_match)
        
        # Extract URLs from description
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, description)
        references["urls"] = list(set(urls))
        
        # Extract key scientific terms
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
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str):
                    clean_match = match.strip()
                    # Normalize V̇O₂ max variations
                    if 'vo2' in clean_match.lower() or 'v2' in clean_match.lower():
                        clean_match = "V̇O₂ max"
                    if clean_match not in references["terms"]:
                        references["terms"].append(clean_match)
        
        # Clean up empty categories
        references = {k: v for k, v in references.items() if v}
        
        return references
    
    def format_duration(self, seconds: int) -> str:
        """Format duration in human-readable format."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    
    def generate_summary_prompt(self, video_info: dict, transcript: str, references: dict) -> str:
        """Generate a prompt for LLM summarization."""
        refs_text = ""
        if references:
            refs_text = "\n\nEXTRACTED REFERENCES:\n"
            for category, items in references.items():
                if items:
                    refs_text += f"\n{category.upper()}:\n"
                    for item in items:
                        refs_text += f"  - {item}\n"
        
        return f"""Please summarize the following video transcript. Include:

1. **Overview** - What is this video about?
2. **Key Findings** - Main points, data, and conclusions
3. **Practical Takeaways** - Actionable advice for the viewer
4. **Annotated References** - List all studies, papers, books, people, and scientific terms mentioned with context

VIDEO METADATA:
- Title: {video_info['title']}
- Channel: {video_info['channel']}
- Duration: {self.format_duration(video_info['duration'])}
- URL: {video_info['url']}
{refs_text}

TRANSCRIPT:
{transcript[:50000]}  # Truncate if too long

Please provide the summary in Markdown format."""

    def create_output(self, video_info: dict, transcript: str, references: dict) -> str:
        """Create the final output document."""
        output = f"""# Video Summary: {video_info['title']}

**Channel:** {video_info['channel']}  
**Duration:** {self.format_duration(video_info['duration'])}  
**URL:** {video_info['url']}  
**Processed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## Extracted References

"""
        
        if references.get("studies"):
            output += "### 📚 Studies & Papers\n"
            for study in references["studies"]:
                output += f"- {study}\n"
            output += "\n"
        
        if references.get("people"):
            output += "### 👤 People Mentioned\n"
            for person in references["people"]:
                output += f"- {person}\n"
            output += "\n"
        
        if references.get("books"):
            output += "### 📖 Books\n"
            for book in references["books"]:
                output += f"- {book}\n"
            output += "\n"
        
        if references.get("organizations"):
            output += "### 🏛️ Organizations\n"
            for org in references["organizations"]:
                output += f"- {org}\n"
            output += "\n"
        
        if references.get("terms"):
            output += "### 🔬 Key Scientific Terms\n"
            for term in references["terms"]:
                output += f"- **{term}**\n"
            output += "\n"
        
        if references.get("urls"):
            output += "### 🔗 Links from Description\n"
            for url in references["urls"][:20]:  # Limit to 20 URLs
                output += f"- {url}\n"
            output += "\n"
        
        output += """---

## Full Transcript

<details>
<summary>Click to expand full transcript</summary>

"""
        output += transcript[:100000]  # Truncate very long transcripts
        output += """

</details>

---

## LLM Summary Prompt

Use this prompt with Claude or another LLM to generate a detailed summary:

```
"""
        output += self.generate_summary_prompt(video_info, transcript[:30000], references)
        output += """
```
"""
        
        return output

    def process_video(self, url: str, output_file: str = None) -> Path:
        """Main processing pipeline."""
        print(f"\nProcessing video: {url}\n")

        # Fetch transcript and metadata
        video_info = self.fetch_video_info(url)
        transcript = video_info["transcript"]
        print(f"Video: {video_info['title']}")
        print(f"Channel: {video_info['channel']}")
        print(f"Duration: {self.format_duration(video_info['duration'])}")
        print(f"Extracted {len(transcript):,} characters ({len(transcript.split()):,} words)")
        
        # Extract references
        print("\nExtracting references...")
        references = self.extract_references(transcript, video_info.get('description', ''))
        total_refs = sum(len(v) for v in references.values())
        print(f"Found {total_refs} references across {len(references)} categories")

        # Generate output
        print("\nGenerating summary document...")
        output_content = self.create_output(video_info, transcript, references)
        
        # Save output
        if output_file:
            output_path = Path(output_file)
        else:
            safe_title = re.sub(r'[^\w\s-]', '', video_info['title'])[:50]
            output_path = self.output_dir / f"{safe_title}.md"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_content)
        
        print(f"\nSummary saved to: {output_path}")

        # Also save raw transcript
        transcript_path = self.output_dir / f"{video_info['video_id']}_transcript.txt"
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(transcript)
        print(f"Raw transcript saved to: {transcript_path}")
        
        return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python summarize_video.py <youtube_url> [--output <file.md>]")
        sys.exit(1)
    
    url = sys.argv[1]
    output_file = None
    
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]
    
    summarizer = VideoSummarizer()
    
    try:
        output_path = summarizer.process_video(url, output_file)
        print(f"\nDone! Open {output_path} to see the summary.")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
