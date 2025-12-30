# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Video Summarizer is a Python CLI tool that extracts transcripts from YouTube videos and generates Markdown summaries with categorized references (studies, people, books, organizations, scientific terms, URLs).

## Commands

```bash
# Run the tool (shell wrapper)
./summarize "https://www.youtube.com/watch?v=VIDEO_ID"

# Run directly with Python
python3 summarize_video.py "https://www.youtube.com/watch?v=VIDEO_ID"

# With custom output file
python3 summarize_video.py "https://www.youtube.com/watch?v=VIDEO_ID" --output my_summary.md
```

## Requirements

- Python 3.8+
- yt-dlp (installed via `brew install yt-dlp`)

## Architecture

Single-file Python application (`summarize_video.py`) with one class:

**VideoSummarizer** - Main class handling the full pipeline:
- `download_subtitles()` - Uses yt-dlp subprocess to fetch video metadata and VTT captions
- `parse_vtt()` - Parses WebVTT files, deduplicates lines, strips HTML/formatting tags
- `extract_references()` - Regex-based extraction of studies, people, books, orgs, terms, URLs
- `create_output()` - Generates Markdown with collapsible transcript and embedded LLM prompt
- `process_video()` - Orchestrates the full pipeline

**Output files** are written to `~/video-summarizer/` by default:
- `<video_title>.md` - Summary with references, collapsible transcript, and LLM prompt
- `<video_id>_transcript.txt` - Raw cleaned transcript

## Key Implementation Details

- Subprocess calls to yt-dlp with `--dump-json` for metadata and `--write-auto-sub` for captions
- VTT parsing uses line deduplication via `seen_text` set to handle repeated caption lines
- Reference extraction relies on hardcoded regex patterns for specific names and terms (e.g., Lavine, Patrick, Huberman)
- Transcript in output is truncated to 100k chars; LLM prompt truncates to 30k chars
