"""
Redis Client Manager - Connection pooling and cache operations.

Handles:
- Connection pooling
- Session state caching
- Conversation history caching
- Agent response caching
- TTL management
"""

import json
from typing import Any, Dict, List, Optional
import redis
from redis import Redis
from redis.connection import ConnectionPool
import logging

from .logger import get_logger
from .exceptions import MCPServerError

logger = get_logger(__name__)


class RedisClientManager:
    """Manages Redis connections and cache operations."""
    
    # Cache TTLs (in seconds)
    TTL_SESSION = 86400  # 24 hours
    TTL_CONVERSATION = 86400  # 24 hours
    TTL_AGENT_CACHE = 3600  # 1 hour
    TTL_TEMP = 300  # 5 minutes
    
    def __init__(self, redis_url: str):
        """
        Initialize Redis client with connection pooling.
        
        Args:
            redis_url: Redis connection URL (e.g., redis://:password@host:6379/0)
        """
        self.redis_url = redis_url
        self.pool = ConnectionPool.from_url(redis_url)
        self.client: Redis = Redis(connection_pool=self.pool)
        self.logger = get_logger("RedisClient")
        
        try:
            self.client.ping()
            self.logger.info("Redis connection successful")
        except Exception as e:
            self.logger.error(f"Redis connection failed: {e}")
            raise MCPServerError(f"Redis connection error: {e}")
    
    def close(self):
        """Close Redis connection."""
        if self.pool:
            self.pool.disconnect()
            self.logger.info("Redis connection closed")
    
    # ============================================================================
    # SESSION CACHE
    # ============================================================================
    
    async def store_session(self, session_id: str, data: Dict[str, Any]):
        """Store session state in cache."""
        try:
            key = f"session:{session_id}"
            self.client.setex(
                key,
                self.TTL_SESSION,
                json.dumps(data, default=str)
            )
            self.logger.debug(f"Stored session: {session_id}")
        except Exception as e:
            self.logger.error(f"Failed to store session: {e}")
            raise
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session state from cache."""
        try:
            key = f"session:{session_id}"
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get session: {e}")
            return None
    
    async def delete_session(self, session_id: str):
        """Delete session from cache."""
        try:
            key = f"session:{session_id}"
            self.client.delete(key)
            self.logger.debug(f"Deleted session: {session_id}")
        except Exception as e:
            self.logger.error(f"Failed to delete session: {e}")
    
    # ============================================================================
    # CONVERSATION CACHE
    # ============================================================================
    
    async def store_conversation_turn(
        self,
        session_id: str,
        turn_number: int,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """Store conversation turn in Redis list."""
        try:
            key = f"conversation:{session_id}:turns"
            turn_data = {
                "turn_number": turn_number,
                "role": role,
                "content": content,
                "metadata": metadata or {}
            }
            self.client.rpush(key, json.dumps(turn_data, default=str))
            self.client.expire(key, self.TTL_CONVERSATION)
            self.logger.debug(f"Stored turn {turn_number} for session {session_id}")
        except Exception as e:
            self.logger.error(f"Failed to store conversation turn: {e}")
            raise
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent conversation turns."""
        try:
            key = f"conversation:{session_id}:turns"
            # Get last 'limit' items
            data = self.client.lrange(key, -limit, -1)
            turns = [json.loads(item) for item in data]
            self.logger.debug(f"Retrieved {len(turns)} turns for session {session_id}")
            return turns
        except Exception as e:
            self.logger.error(f"Failed to get conversation history: {e}")
            return []
    
    async def clear_conversation(self, session_id: str):
        """Clear all conversation turns for a session."""
        try:
            key = f"conversation:{session_id}:turns"
            self.client.delete(key)
            self.logger.debug(f"Cleared conversation for session {session_id}")
        except Exception as e:
            self.logger.error(f"Failed to clear conversation: {e}")
    
    # ============================================================================
    # AGENT RESPONSE CACHE
    # ============================================================================
    
    async def cache_agent_response(
        self,
        agent_name: str,
        query_hash: str,
        result: str,
        ttl: int = None
    ):
        """Cache agent response for quick retrieval."""
        try:
            key = f"agent_cache:{agent_name}:{query_hash}"
            ttl = ttl or self.TTL_AGENT_CACHE
            self.client.setex(
                key,
                ttl,
                json.dumps({"result": result}, default=str)
            )
            self.logger.debug(f"Cached response for {agent_name}")
        except Exception as e:
            self.logger.error(f"Failed to cache agent response: {e}")
    
    async def get_cached_response(
        self,
        agent_name: str,
        query_hash: str
    ) -> Optional[str]:
        """Get cached agent response."""
        try:
            key = f"agent_cache:{agent_name}:{query_hash}"
            data = self.client.get(key)
            if data:
                return json.loads(data).get("result")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get cached response: {e}")
            return None
    
    # ============================================================================
    # AGENT STATE
    # ============================================================================
    
    async def store_agent_state(
        self,
        session_id: str,
        agent_name: str,
        state: Dict[str, Any]
    ):
        """Store agent-specific state."""
        try:
            key = f"agent_state:{session_id}:{agent_name}"
            self.client.setex(
                key,
                self.TTL_TEMP,
                json.dumps(state, default=str)
            )
            self.logger.debug(f"Stored state for {agent_name}")
        except Exception as e:
            self.logger.error(f"Failed to store agent state: {e}")
    
    async def get_agent_state(
        self,
        session_id: str,
        agent_name: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve agent-specific state."""
        try:
            key = f"agent_state:{session_id}:{agent_name}"
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get agent state: {e}")
            return None
    
    # ============================================================================
    # PUB/SUB FOR REAL-TIME UPDATES
    # ============================================================================
    
    def subscribe_to_session(self, session_id: str) -> redis.client.PubSub:
        """Subscribe to session updates."""
        channel = f"session:{session_id}:updates"
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        self.logger.debug(f"Subscribed to {channel}")
        return pubsub
    
    async def publish_session_update(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any]
    ):
        """Publish session update to subscribers."""
        try:
            channel = f"session:{session_id}:updates"
            message = {
                "event_type": event_type,
                "data": data
            }
            self.client.publish(channel, json.dumps(message, default=str))
            self.logger.debug(f"Published {event_type} to {channel}")
        except Exception as e:
            self.logger.error(f"Failed to publish update: {e}")
    
    # ============================================================================
    # UTILITY
    # ============================================================================
    
    async def health_check(self) -> bool:
        """Check Redis health."""
        try:
            self.client.ping()
            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    async def clear_all_for_session(self, session_id: str):
        """Clear all caches for a session."""
        try:
            patterns = [
                f"session:{session_id}",
                f"conversation:{session_id}:*",
                f"agent_state:{session_id}:*"
            ]
            for pattern in patterns:
                keys = self.client.keys(pattern)
                if keys:
                    self.client.delete(*keys)
            self.logger.info(f"Cleared all caches for session {session_id}")
        except Exception as e:
            self.logger.error(f"Failed to clear caches: {e}")