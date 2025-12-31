# Video/Chat History - Feature Spec

## Overview

Allow users to access their previously analyzed videos and continue chat conversations. History is stored per-user based on their authenticated email address.

## Data Model

```
User History Entry:
├── user_email (string)
├── video_id (string, YouTube ID)
├── job_id (string, unique)
├── created_at (timestamp)
├── video_metadata
│   ├── title
│   ├── channel
│   ├── duration
│   └── url
├── analysis_result
│   ├── references
│   ├── transcript (truncated for storage?)
│   └── llm_prompt
└── chat_messages[]
    ├── role (user/assistant)
    ├── content
    └── timestamp
```

### Database Schema (PostgreSQL)

```sql
CREATE TABLE video_history (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    job_id VARCHAR(64) UNIQUE NOT NULL,
    video_id VARCHAR(32) NOT NULL,
    title VARCHAR(500),
    channel VARCHAR(255),
    duration INTEGER,
    url VARCHAR(500),
    references JSONB,
    transcript TEXT,
    llm_prompt TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) REFERENCES video_history(job_id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_video_history_user ON video_history(user_email);
CREATE INDEX idx_video_history_created ON video_history(created_at DESC);
CREATE INDEX idx_chat_messages_job ON chat_messages(job_id);
```

## Storage Options

| Option | Pros | Cons |
|--------|------|------|
| **SQLite** | Simple, no extra service, file-based | Single instance only, not ideal for Railway |
| **PostgreSQL** | Scalable, Railway add-on available | More complex, ~$5/month on Railway |
| **Redis** | Fast, good for sessions | Data persistence config needed |
| **Supabase** | Free tier, managed Postgres | External dependency |

**Recommendation:** PostgreSQL via Railway add-on (simple integration, reliable)

## API Endpoints

### List User's History
```
GET /api/history
Authorization: Bearer <token> (or session cookie)

Response:
{
  "items": [
    {
      "job_id": "abc123",
      "video_id": "dQw4w9WgXcQ",
      "title": "Video Title",
      "channel": "Channel Name",
      "duration": 3600,
      "url": "https://youtube.com/watch?v=...",
      "created_at": "2025-12-30T10:00:00Z",
      "message_count": 5
    }
  ],
  "total": 15,
  "page": 1,
  "per_page": 20
}
```

### Get Full Analysis + Chat
```
GET /api/history/{job_id}
Authorization: Bearer <token>

Response:
{
  "job_id": "abc123",
  "video": { ... },
  "references": { ... },
  "transcript": "...",
  "llm_prompt": "...",
  "chat_messages": [
    { "role": "user", "content": "...", "created_at": "..." },
    { "role": "assistant", "content": "...", "created_at": "..." }
  ],
  "created_at": "2025-12-30T10:00:00Z"
}
```

### Delete History Entry
```
DELETE /api/history/{job_id}
Authorization: Bearer <token>

Response:
{ "success": true }
```

### Existing Endpoints (Modified)
```
POST /api/videos/analyze
- After successful analysis, auto-save to history

POST /api/chat/message
- After successful response, append to chat_messages table
```

## Frontend Changes

### 1. History Sidebar

```
┌─────────────────────────────────────────────────────┐
│ Video Summariser                    [user] [logout] │
├──────────────┬──────────────────────────────────────┤
│ History      │                                      │
│ ───────────  │     [Current video analysis]        │
│ Today        │                                      │
│  • Video 1   │                                      │
│  • Video 2   │                                      │
│              │                                      │
│ Yesterday    │     [AI Assistant panel]            │
│  • Video 3   │                                      │
│              │                                      │
│ Last Week    │                                      │
│  • Video 4   │                                      │
│  • Video 5   │                                      │
└──────────────┴──────────────────────────────────────┘
```

- Collapsible on mobile (hamburger menu)
- Grouped by date (Today, Yesterday, Last 7 Days, Older)
- Each entry shows: video title (truncated), channel name
- Hover/click reveals delete button
- Click loads the full analysis and chat history

### 2. History Entry Component

```tsx
interface HistoryEntry {
  job_id: string;
  video_id: string;
  title: string;
  channel: string;
  duration: number;
  created_at: string;
  message_count: number;
}
```

### 3. State Management

- Add `selectedHistoryId` state
- When loading from history, populate `analysis` and `messages` from API
- Clear URL input when viewing history
- Show "New Analysis" button to return to fresh state

### 4. Mobile Considerations

- History as a dropdown or slide-out drawer
- Swipe to delete on touch devices
- Compact list view

## Implementation Phases

### Phase 1 - Basic History (3-4 hours)
- [x] Add PostgreSQL to Railway project
- [x] Create database schema
- [x] Add SQLAlchemy or asyncpg to backend
- [x] Create history router with list/get/delete endpoints
- [x] Auto-save analyses to database
- [x] Basic history list in frontend
- [x] Load analysis from history

### Phase 2 - Chat Persistence (2 hours)
- [x] Save chat messages to database on send
- [x] Load chat history when selecting from history
- [x] Resume conversations seamlessly

### Phase 3 - Polish (2-3 hours)
- [ ] Search history by title/channel
- [ ] Sort options (date, title)
- [ ] Bulk delete / clear all
- [ ] Export history as JSON
- [ ] Storage limits (e.g., 50 videos per user)
- [ ] Auto-delete after 90 days (optional)

## Configuration

### Environment Variables

```
DATABASE_URL=postgresql://user:pass@host:5432/dbname
HISTORY_ENABLED=true
HISTORY_MAX_ENTRIES=50
HISTORY_RETENTION_DAYS=90
```

## Security Considerations

- Users can only access their own history (enforce via user_email filter)
- Validate job_id ownership before returning data
- Rate limit history endpoints
- Consider encrypting transcript/chat content at rest

## Estimated Costs

- Railway PostgreSQL: ~$5/month (hobby tier)
- Storage: Minimal (text data, ~1KB per message, ~50KB per video entry)
- 1000 users x 50 videos = 50,000 entries = ~2.5GB max

## Future Enhancements

- Share video analysis via public link
- Collaborative annotations
- Video collections/folders
- Favorite/star videos
- Import/export history
