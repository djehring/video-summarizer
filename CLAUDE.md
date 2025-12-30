# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Video Summarizer extracts transcripts from YouTube videos and generates summaries with categorized references. Available as both a CLI tool and web application.

## Commands

```bash
# Docker (full stack)
docker-compose up --build           # http://localhost:3000

# Backend development
cd backend && uvicorn app.main:app --reload   # http://localhost:8000

# Frontend development
cd frontend && npm run dev          # http://localhost:5173

# CLI (original)
./summarize "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Architecture

```
video-summarizer/
├── backend/                    # FastAPI backend
│   └── app/
│       ├── main.py             # FastAPI app, CORS config
│       ├── models.py           # Pydantic schemas
│       ├── routers/videos.py   # POST /api/videos/analyze, GET /api/videos/{job_id}
│       └── services/summarizer.py  # Core VideoSummarizer logic
├── frontend/                   # React + Vite + Tailwind
│   └── src/
│       ├── App.tsx             # Main app with state management
│       ├── api/client.ts       # API client with polling
│       └── components/
│           ├── VideoForm.tsx   # URL input form
│           └── SummaryView.tsx # Results display
├── summarize_video.py          # Original CLI tool
└── docker-compose.yml
```

## API

- `POST /api/videos/analyze` - Submit URL, returns `{ job_id, status }`
- `GET /api/videos/{job_id}` - Poll for results (pending → processing → completed/failed)

Jobs run in background (yt-dlp takes 10-30s). Frontend polls until complete.

## Key Implementation Details

- **yt-dlp subprocess**: `--dump-json` for metadata, `--write-auto-sub` for captions
- **VTT parsing**: Deduplicates lines via `seen_text` set, strips HTML tags
- **Reference extraction**: Hardcoded regex patterns for studies, people, terms
- **Job storage**: In-memory dict (use Redis for production)
- **Transcript limits**: 100k chars in response, 50k in LLM prompt
