import os
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship

DATABASE_URL = os.getenv('DATABASE_URL', '')

# Convert postgres:// to postgresql+asyncpg:// for async support
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+asyncpg://', 1)
elif DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://', 1)

Base = declarative_base()


class VideoHistory(Base):
    __tablename__ = 'video_history'

    id = Column(Integer, primary_key=True)
    user_email = Column(String(255), nullable=False, index=True)
    job_id = Column(String(64), unique=True, nullable=False)
    video_id = Column(String(32), nullable=False)
    title = Column(String(500))
    channel = Column(String(255))
    duration = Column(Integer)
    url = Column(String(500))
    references = Column(JSON)
    transcript = Column(Text)
    llm_prompt = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chat_messages = relationship('ChatMessageDB', back_populates='video_history', cascade='all, delete-orphan')


class ChatMessageDB(Base):
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True)
    job_id = Column(String(64), ForeignKey('video_history.job_id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    video_history = relationship('VideoHistory', back_populates='chat_messages')


# Engine and session factory - only created if DATABASE_URL is set
engine = None
async_session_factory = None


def is_database_configured() -> bool:
    """Check if database is configured."""
    return bool(DATABASE_URL)


async def init_db():
    """Initialize database and create tables."""
    global engine, async_session_factory

    if not DATABASE_URL:
        print("[DB] No DATABASE_URL configured, history feature disabled")
        return

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("[DB] Database initialized")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    if async_session_factory is None:
        raise RuntimeError("Database not initialized")
    async with async_session_factory() as session:
        yield session
