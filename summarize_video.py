#!/usr/bin/env python3
"""
Video Summarizer Tool
Extracts transcripts from YouTube videos and generates summaries with annotated references.

Usage:
    python summarize_video.py <youtube_url>
    python summarize_video.py <youtube_url> --output summary.md
"""

import subprocess
import sys
import re
import json
import os
from pathlib import Path
from datetime import datetime

class VideoSummarizer:
    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "video-summarizer"
        self.output_dir.mkdir(exist_ok=True)
        
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
    
    def download_subtitles(self, url: str) -> dict:
        """Download subtitles and video metadata using yt-dlp."""
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {url}")
        
        # Get video info first
        info_cmd = [
            "yt-dlp",
            "--dump-json",
            "--skip-download",
            url
        ]
        
        print("📹 Fetching video metadata...")
        result = subprocess.run(info_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to get video info: {result.stderr}")
        
        video_info = json.loads(result.stdout)
        
        # Download subtitles
        subtitle_path = self.output_dir / f"{video_id}"
        sub_cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "-o", str(subtitle_path),
            url
        ]
        
        print("📝 Downloading subtitles...")
        result = subprocess.run(sub_cmd, capture_output=True, text=True)
        
        # Find the subtitle file
        vtt_files = list(self.output_dir.glob(f"{video_id}*.vtt"))
        if not vtt_files:
            raise RuntimeError("No subtitle file found. Video may not have captions.")
        
        return {
            "video_id": video_id,
            "title": video_info.get("title", "Unknown"),
            "channel": video_info.get("channel", "Unknown"),
            "upload_date": video_info.get("upload_date", "Unknown"),
            "duration": video_info.get("duration", 0),
            "description": video_info.get("description", ""),
            "url": url,
            "subtitle_file": vtt_files[0]
        }
    
    def parse_vtt(self, vtt_path: Path) -> tuple[str, list[dict]]:
        """Parse VTT file to extract clean transcript with timestamps."""
        with open(vtt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        segments = []
        current_time = None
        seen_text = set()
        
        for line in lines:
            # Skip metadata
            if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                continue
            
            # Capture timestamp
            if '-->' in line:
                time_match = re.match(r'(\d{2}:\d{2}:\d{2}\.\d{3})', line)
                if time_match:
                    current_time = time_match.group(1)
                continue
            
            # Skip empty lines and position markers
            if not line.strip() or 'align:' in line or 'position:' in line:
                continue
            
            # Clean the line
            clean = re.sub(r'<[^>]+>', '', line).strip()
            clean = clean.replace('&gt;&gt;', '>>').replace('&amp;', '&')
            
            if clean and clean not in seen_text:
                seen_text.add(clean)
                segments.append({
                    "timestamp": current_time,
                    "text": clean
                })
        
        full_text = ' '.join(s['text'] for s in segments)
        return full_text, segments
    
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
        print(f"\n🎬 Processing video: {url}\n")
        
        # Download subtitles and get metadata
        video_info = self.download_subtitles(url)
        print(f"✅ Video: {video_info['title']}")
        print(f"✅ Channel: {video_info['channel']}")
        print(f"✅ Duration: {self.format_duration(video_info['duration'])}")
        
        # Parse transcript
        print("\n📄 Parsing transcript...")
        transcript, segments = self.parse_vtt(video_info['subtitle_file'])
        print(f"✅ Extracted {len(transcript):,} characters ({len(transcript.split()):,} words)")
        
        # Extract references
        print("\n🔍 Extracting references...")
        references = self.extract_references(transcript, video_info.get('description', ''))
        total_refs = sum(len(v) for v in references.values())
        print(f"✅ Found {total_refs} references across {len(references)} categories")
        
        # Generate output
        print("\n📝 Generating summary document...")
        output_content = self.create_output(video_info, transcript, references)
        
        # Save output
        if output_file:
            output_path = Path(output_file)
        else:
            safe_title = re.sub(r'[^\w\s-]', '', video_info['title'])[:50]
            output_path = self.output_dir / f"{safe_title}.md"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_content)
        
        print(f"\n✅ Summary saved to: {output_path}")
        
        # Also save raw transcript
        transcript_path = self.output_dir / f"{video_info['video_id']}_transcript.txt"
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(transcript)
        print(f"✅ Raw transcript saved to: {transcript_path}")
        
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
        print(f"\n🎉 Done! Open {output_path} to see the summary.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
