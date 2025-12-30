# Video Summarizer Tool

Extract transcripts from YouTube videos and generate summaries with annotated references.

## Features

- 📝 Extracts subtitles/captions from YouTube videos
- 🔍 Automatically identifies and categorizes references:
  - Studies & Papers
  - People mentioned (researchers, experts)
  - Books
  - Organizations
  - Scientific terms & concepts
  - URLs from video description
- 📄 Generates a Markdown summary document
- 🤖 Includes a ready-to-use LLM prompt for detailed summarization

## Requirements

- Python 3.8+
- yt-dlp (`brew install yt-dlp`)

## Usage

### Quick command:
```bash
./summarize "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Python script:
```bash
python3 summarize_video.py "https://www.youtube.com/watch?v=VIDEO_ID"

# With custom output file:
python3 summarize_video.py "https://www.youtube.com/watch?v=VIDEO_ID" --output my_summary.md
```

### As a Python module:
```python
from summarize_video import VideoSummarizer

summarizer = VideoSummarizer()
output_path = summarizer.process_video("https://www.youtube.com/watch?v=VIDEO_ID")
```

## Output

The tool generates:

1. **`<video_title>.md`** - Main summary document with:
   - Video metadata (title, channel, duration, URL)
   - Extracted references by category
   - Full transcript (collapsible)
   - Ready-to-use LLM prompt for further summarization

2. **`<video_id>_transcript.txt`** - Raw cleaned transcript

## Example

```bash
./summarize "https://www.youtube.com/watch?v=QnloZ45PVxQ"
```

Output:
```
🎬 Processing video: https://www.youtube.com/watch?v=QnloZ45PVxQ

📹 Fetching video metadata...
📝 Downloading subtitles...
✅ Video: Why Vigorous Exercise Is 4–10x More Effective Than Moderate
✅ Channel: FoundMyFitness  
✅ Duration: 2h 10m

📄 Parsing transcript...
✅ Extracted 149,647 characters (27,235 words)

🔍 Extracting references...
✅ Found 46 references across 6 categories

📝 Generating summary document...
✅ Summary saved to: ./Why Vigorous Exercise Is 410x More Effective Than .md
```

## Reference Categories

| Category | Examples |
|----------|----------|
| Studies & Papers | Nature Communications, UK Biobank, JAMA |
| People | Dr. Ben Lavine, Dr. Rhonda Patrick |
| Books | V̇O₂ Max Essentials |
| Organizations | WHO, NIH, FDA |
| Scientific Terms | V̇O₂ max, HIIT, Zone 2, Norwegian 4x4 |
| URLs | Links from video description |

## Tips

1. **For best results**, videos should have English captions/subtitles
2. **Auto-generated captions** work but may have transcription errors
3. **Use the LLM prompt** at the end of the summary to get Claude to generate a detailed analysis
4. **The tool works offline** after downloading subtitles - great for batch processing

## Workflow

1. Run the summarizer on an interesting video
2. Open the generated Markdown file
3. Review the extracted references
4. Copy the LLM prompt into Claude for a detailed summary
5. Ask follow-up questions about specific topics

---

Created for quick research and learning from video content.
