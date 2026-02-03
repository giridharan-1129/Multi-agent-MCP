"""
PostgreSQL Client Manager - Database operations for conversation storage.

Handles:
- Connection pooling
- Conversation CRUD operations
- Session management
- Agent response logging
- Query execution with error handling
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
import asyncio

from sqlalchemy import create_engine, Column, String, DateTime, Integer, ARRAY, JSON, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship, Session
from sqlalchemy.future import select
import uuid

from .logger import get_logger
from .exceptions import MCPServerError
from .conversation_models import (
    ConversationSession,
    ConversationTurn,
    AgentResponse,
)

logger = get_logger(__name__)

Base = declarative_base()


class SessionModel(Base):
    """SQLAlchemy model for conversation sessions."""
    __tablename__ = "conversation_sessions"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    session_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)
    metadata = Column(JSON, default={})
    
    # Relationships
    turns = relationship("TurnModel", back_populates="session", cascade="all, delete-orphan")


class TurnModel(Base):
    """SQLAlchemy model for conversation turns."""
    __tablename__ = "conversation_turns"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(PG_UUID(as_uuid=True), ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    turn_number = Column(Integer, nullable=False)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    session = relationship("SessionModel", back_populates="turns")
    responses = relationship("ResponseModel", back_populates="turn", cascade="all, delete-orphan")


class ResponseModel(Base):
    """SQLAlchemy model for agent responses."""
    __tablename__ = "agent_responses"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turn_id = Column(PG_UUID(as_uuid=True), ForeignKey("conversation_turns.id"), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False, index=True)
    tools_used = Column(ARRAY(String), default=[])
    result = Column(Text, nullable=False)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    turn = relationship("TurnModel", back_populates="responses")


class PostgreSQLClientManager:
    """Manages PostgreSQL connections and conversation storage."""
    
    def __init__(self, database_url: str):
        """
        Initialize PostgreSQL client with async support.
        
        Args:
            database_url: PostgreSQL connection URL
                (e.g., postgresql+asyncpg://user:pass@host/db)
        """
        self.database_url = database_url
        self.engine = None
        self.async_session_maker = None
        self.logger = get_logger("PostgreSQLClient")
    
    async def initialize(self):
        """Initialize async engine and session maker."""
        try:
            # Convert standard postgres URL to async
            url = self.database_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            self.engine = create_async_engine(
                url,
                echo=False,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True
            )
            
            self.async_session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            self.logger.info("PostgreSQL connection successful")
        except Exception as e:
            self.logger.error(f"PostgreSQL connection failed: {e}")
            raise MCPServerError(f"PostgreSQL connection error: {e}")
    
    async def close(self):
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()
            self.logger.info("PostgreSQL connection closed")
    
    # ============================================================================
    # SESSION OPERATIONS
    # ============================================================================
    
    async def create_session(
        self,
        user_id: str,
        session_name: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> ConversationSession:
        """Create a new conversation session."""
        try:
            async with self.async_session_maker() as session:
                db_session = SessionModel(
                    user_id=user_id,
                    session_name=session_name,
                    metadata=metadata or {}
                )
                session.add(db_session)
                await session.commit()
                await session.refresh(db_session)
                
                self.logger.info(f"Created session {db_session.id} for user {user_id}")
                return self._to_conversation_session(db_session)
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            raise
    
    async def get_session(self, session_id: UUID) -> Optional[ConversationSession]:
        """Retrieve a session by ID."""
        try:
            async with self.async_session_maker() as session:
                result = await session.execute(
                    select(SessionModel).where(SessionModel.id == session_id)
                )
                db_session = result.scalar_one_or_none()
                return self._to_conversation_session(db_session) if db_session else None
        except Exception as e:
            self.logger.error(f"Failed to get session: {e}")
            return None
    
    async def get_user_sessions(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[ConversationSession]:
        """Get all sessions for a user."""
        try:
            async with self.async_session_maker() as session:
                result = await session.execute(
                    select(SessionModel)
                    .where(SessionModel.user_id == user_id)
                    .order_by(SessionModel.created_at.desc())
                    .limit(limit)
                )
                db_sessions = result.scalars().all()
                return [self._to_conversation_session(s) for s in db_sessions]
        except Exception as e:
            self.logger.error(f"Failed to get user sessions: {e}")
            return []
    
    async def close_session(self, session_id: UUID):
        """Close a session."""
        try:
            async with self.async_session_maker() as session:
                result = await session.execute(
                    select(SessionModel).where(SessionModel.id == session_id)
                )
                db_session = result.scalar_one_or_none()
                if db_session:
                    db_session.closed_at = datetime.utcnow()
                    await session.commit()
                    self.logger.info(f"Closed session {session_id}")
        except Exception as e:
            self.logger.error(f"Failed to close session: {e}")
    
    # ============================================================================
    # CONVERSATION TURN OPERATIONS
    # ============================================================================
    
    async def store_turn(
        self,
        session_id: UUID,
        turn_number: int,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> ConversationTurn:
        """Store a conversation turn."""
        try:
            async with self.async_session_maker() as session:
                db_turn = TurnModel(
                    session_id=session_id,
                    turn_number=turn_number,
                    role=role,
                    content=content,
                    metadata=metadata or {}
                )
                session.add(db_turn)
                await session.commit()
                await session.refresh(db_turn)
                
                self.logger.debug(f"Stored turn {turn_number} for session {session_id}")
                return self._to_conversation_turn(db_turn)
        except Exception as e:
            self.logger.error(f"Failed to store turn: {e}")
            raise
    
    async def get_conversation_history(
        self,
        session_id: UUID,
        limit: int = 20
    ) -> List[ConversationTurn]:
        """Get conversation history for a session."""
        try:
            async with self.async_session_maker() as session:
                result = await session.execute(
                    select(TurnModel)
                    .where(TurnModel.session_id == session_id)
                    .order_by(TurnModel.turn_number.desc())
                    .limit(limit)
                )
                db_turns = result.scalars().all()
                # Return in chronological order
                return [self._to_conversation_turn(t) for t in reversed(db_turns)]
        except Exception as e:
            self.logger.error(f"Failed to get conversation history: {e}")
            return []
    
    # ============================================================================
    # AGENT RESPONSE OPERATIONS
    # ============================================================================
    
    async def store_agent_response(
        self,
        turn_id: UUID,
        agent_name: str,
        tools_used: List[str],
        result: str,
        duration_ms: Optional[int] = None
    ) -> AgentResponse:
        """Store agent response for a turn."""
        try:
            async with self.async_session_maker() as session:
                db_response = ResponseModel(
                    turn_id=turn_id,
                    agent_name=agent_name,
                    tools_used=tools_used,
                    result=result,
                    duration_ms=duration_ms
                )
                session.add(db_response)
                await session.commit()
                await session.refresh(db_response)
                
                self.logger.debug(f"Stored response from {agent_name} for turn {turn_id}")
                return self._to_agent_response(db_response)
        except Exception as e:
            self.logger.error(f"Failed to store agent response: {e}")
            raise
    
    async def get_turn_responses(self, turn_id: UUID) -> List[AgentResponse]:
        """Get all agent responses for a turn."""
        try:
            async with self.async_session_maker() as session:
                result = await session.execute(
                    select(ResponseModel).where(ResponseModel.turn_id == turn_id)
                )
                db_responses = result.scalars().all()
                return [self._to_agent_response(r) for r in db_responses]
        except Exception as e:
            self.logger.error(f"Failed to get turn responses: {e}")
            return []
    
    # ============================================================================
    # UTILITY
    # ============================================================================
    
    async def health_check(self) -> bool:
        """Check database health."""
        try:
            async with self.async_session_maker() as session:
                await session.execute(select(1))
            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    async def delete_session_cascade(self, session_id: UUID):
        """Delete session and all related turns/responses."""
        try:
            async with self.async_session_maker() as session:
                await session.execute(
                    select(SessionModel).where(SessionModel.id == session_id)
                )
                # Cascade delete via relationship
                await session.commit()
                self.logger.info(f"Deleted session {session_id} and all related data")
        except Exception as e:
            self.logger.error(f"Failed to delete session: {e}")
    
    # ============================================================================
    # CONVERSION HELPERS
    # ============================================================================
    
    @staticmethod
    def _to_conversation_session(db_session: SessionModel) -> ConversationSession:
        """Convert SQLAlchemy model to Pydantic model."""
        return ConversationSession(
            id=db_session.id,
            user_id=db_session.user_id,
            session_name=db_session.session_name,
            created_at=db_session.created_at,
            closed_at=db_session.closed_at,
            metadata=db_session.metadata
        )
    
    @staticmethod
    def _to_conversation_turn(db_turn: TurnModel) -> ConversationTurn:
        """Convert SQLAlchemy model to Pydantic model."""
        return ConversationTurn(
            id=db_turn.id,
            session_id=db_turn.session_id,
            turn_number=db_turn.turn_number,
            role=db_turn.role,
            content=db_turn.content,
            metadata=db_turn.metadata,
            created_at=db_turn.created_at
        )
    
    @staticmethod
    def _to_agent_response(db_response: ResponseModel) -> AgentResponse:
        """Convert SQLAlchemy model to Pydantic model."""
        return AgentResponse(
            id=db_response.id,
            turn_id=db_response.turn_id,
            agent_name=db_response.agent_name,
            tools_used=db_response.tools_used,
            result=db_response.result,
            duration_ms=db_response.duration_ms,
            created_at=db_response.created_at
        )