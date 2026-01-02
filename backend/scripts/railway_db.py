#!/usr/bin/env python3
"""
Railway Database Connection & Debug Script

Usage:
    # Set DATABASE_URL from Railway (get from Railway Dashboard → PostgreSQL → Connect)
    export DATABASE_URL="postgresql://postgres:PASSWORD@HOST:PORT/railway"

    # Or use Railway CLI to get variables
    eval $(railway variables --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'export DATABASE_URL=\"{d.get(\"DATABASE_URL\", \"\")}\"')")

    # Run the script
    python3 backend/scripts/railway_db.py [command]

Commands:
    status      Check database connection and table status (default)
    history     List video history entries
    chats       List chat messages
    check JOB   Check specific job's chat messages
    fix         Attempt to fix common issues
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    """Get database connection from DATABASE_URL."""
    url = os.getenv('DATABASE_URL', '')

    if not url:
        print("❌ DATABASE_URL not set")
        print("\nTo connect to Railway database:")
        print("  1. Go to Railway Dashboard → Your Project → PostgreSQL service")
        print("  2. Click 'Connect' tab → Copy connection string")
        print("  3. Run: export DATABASE_URL='your-connection-string'")
        print("\nOr use Railway CLI:")
        print("  railway login && railway link")
        print("  eval $(railway variables --shell)")
        sys.exit(1)

    # Convert async URL back to sync for psycopg2
    if '+asyncpg' in url:
        url = url.replace('postgresql+asyncpg://', 'postgresql://')

    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def cmd_status():
    """Check database connection and table status."""
    print("🔍 Checking Railway database connection...\n")

    try:
        conn = get_connection()
        cur = conn.cursor()

        print("✅ Connected to database\n")

        # Check tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row['table_name'] for row in cur.fetchall()]

        print(f"📋 Tables found: {tables}\n")

        expected = ['video_history', 'chat_messages']
        missing = [t for t in expected if t not in tables]
        if missing:
            print(f"⚠️  Missing tables: {missing}")
            print("   Run the backend once to auto-create tables, or run: python3 railway_db.py fix")

        # Check row counts
        for table in expected:
            if table in tables:
                cur.execute(f"SELECT COUNT(*) as count FROM {table}")
                count = cur.fetchone()['count']
                print(f"   {table}: {count} rows")

        # Check foreign key constraint
        if 'chat_messages' in tables:
            cur.execute("""
                SELECT COUNT(*) as orphaned
                FROM chat_messages cm
                LEFT JOIN video_history vh ON cm.job_id = vh.job_id
                WHERE vh.job_id IS NULL
            """)
            orphaned = cur.fetchone()['orphaned']
            if orphaned > 0:
                print(f"\n⚠️  Found {orphaned} orphaned chat messages (no matching video_history)")

        conn.close()
        print("\n✅ Database check complete")

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)


def cmd_history():
    """List video history entries."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT vh.job_id, vh.user_email, vh.title, vh.created_at,
               COUNT(cm.id) as chat_count
        FROM video_history vh
        LEFT JOIN chat_messages cm ON vh.job_id = cm.job_id
        GROUP BY vh.id
        ORDER BY vh.created_at DESC
        LIMIT 20
    """)

    rows = cur.fetchall()

    if not rows:
        print("No video history entries found")
        return

    print(f"{'Job ID':<20} {'User':<30} {'Chats':<6} {'Title':<40}")
    print("-" * 100)

    for row in rows:
        title = (row['title'] or '')[:40]
        print(f"{row['job_id']:<20} {row['user_email']:<30} {row['chat_count']:<6} {title}")

    conn.close()


def cmd_chats():
    """List recent chat messages."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT cm.job_id, cm.role, LEFT(cm.content, 80) as content_preview, cm.created_at
        FROM chat_messages cm
        ORDER BY cm.created_at DESC
        LIMIT 30
    """)

    rows = cur.fetchall()

    if not rows:
        print("No chat messages found")
        print("\nThis could mean:")
        print("  1. No one has used the chat feature yet")
        print("  2. Chat messages aren't being saved (check backend logs)")
        print("  3. save_chat_messages() is failing silently")
        return

    print(f"{'Job ID':<20} {'Role':<10} {'Created':<20} {'Content Preview'}")
    print("-" * 120)

    for row in rows:
        created = row['created_at'].strftime('%Y-%m-%d %H:%M') if row['created_at'] else 'N/A'
        content = (row['content_preview'] or '').replace('\n', ' ')
        print(f"{row['job_id']:<20} {row['role']:<10} {created:<20} {content}")

    conn.close()


def cmd_check(job_id: str):
    """Check specific job's data and chat messages."""
    conn = get_connection()
    cur = conn.cursor()

    # Get video history
    cur.execute("SELECT * FROM video_history WHERE job_id = %s", (job_id,))
    history = cur.fetchone()

    if not history:
        print(f"❌ No video_history found for job_id: {job_id}")
        conn.close()
        return

    print(f"📹 Video History for {job_id}")
    print(f"   User: {history['user_email']}")
    print(f"   Title: {history['title']}")
    print(f"   Created: {history['created_at']}")
    print(f"   Has transcript: {'Yes' if history['transcript'] else 'No'}")
    print(f"   Has references: {'Yes' if history['references'] else 'No'}")

    # Get chat messages
    cur.execute("""
        SELECT role, content, created_at
        FROM chat_messages
        WHERE job_id = %s
        ORDER BY created_at
    """, (job_id,))

    messages = cur.fetchall()

    print(f"\n💬 Chat Messages: {len(messages)}")

    for i, msg in enumerate(messages):
        created = msg['created_at'].strftime('%H:%M:%S') if msg['created_at'] else 'N/A'
        content = msg['content'][:100] + '...' if len(msg['content']) > 100 else msg['content']
        print(f"   [{created}] {msg['role']}: {content}")

    conn.close()


def cmd_fix():
    """Attempt to fix common issues."""
    print("🔧 Attempting to fix database issues...\n")

    conn = get_connection()
    cur = conn.cursor()

    # Create tables if missing
    print("Creating tables if they don't exist...")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_history (
            id SERIAL PRIMARY KEY,
            user_email VARCHAR(255) NOT NULL,
            job_id VARCHAR(64) UNIQUE NOT NULL,
            video_id VARCHAR(32) NOT NULL,
            title VARCHAR(500),
            channel VARCHAR(255),
            duration INTEGER,
            url VARCHAR(500),
            references JSON,
            transcript TEXT,
            llm_prompt TEXT,
            synopsis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            job_id VARCHAR(64) NOT NULL REFERENCES video_history(job_id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes if missing
    cur.execute("CREATE INDEX IF NOT EXISTS idx_video_history_user_email ON video_history(user_email)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_video_history_created_at ON video_history(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_job_id ON chat_messages(job_id)")

    conn.commit()
    print("✅ Tables and indexes created/verified")

    # Clean up orphaned messages
    cur.execute("""
        DELETE FROM chat_messages
        WHERE job_id NOT IN (SELECT job_id FROM video_history)
    """)
    deleted = cur.rowcount
    if deleted > 0:
        print(f"🧹 Deleted {deleted} orphaned chat messages")

    conn.commit()
    conn.close()

    print("\n✅ Fix complete")


def main():
    if len(sys.argv) < 2:
        cmd_status()
        return

    command = sys.argv[1].lower()

    if command == 'status':
        cmd_status()
    elif command == 'history':
        cmd_history()
    elif command == 'chats':
        cmd_chats()
    elif command == 'check' and len(sys.argv) > 2:
        cmd_check(sys.argv[2])
    elif command == 'fix':
        cmd_fix()
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
