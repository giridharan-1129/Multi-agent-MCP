"""Parallel search handler - executes entity search + semantic search in parallel."""

import asyncio
from typing import Any, Dict, Optional
from ....shared.mcp_server import ToolResult
from ....shared.logger import get_logger
from .agent_calls import call_agent_tool

logger = get_logger(__name__)


async def parallel_entity_and_semantic_search(
    query: str,
    entity_name: str,
    openai_api_key: str,
    http_client: Any,
    postgres_client: Any,
    agent_urls: Dict[str, str]
) -> ToolResult:
    """
    Execute Neo4j entity search + Pinecone semantic search IN PARALLEL.
    ...
    """
    try:
        logger.info("🔄 PARALLEL_SEARCH: Starting parallel entity + semantic search...")
        logger.info(f"   📝 Query: {query[:80]}...")
        logger.info(f"   🎯 Entity name: '{entity_name}'")
        
        # Check if entity_name is valid (not "unknown" or empty)
        has_valid_entity = entity_name and entity_name.lower() != "unknown"
        logger.info(f"   ✓ Valid entity: {has_valid_entity}")
        
        # Create both tasks in parallel
        # TASK 1: Neo4j entity search (skip if no valid entity)
        if has_valid_entity:
            logger.info(f"   📍 Task 1: Neo4j entity search for '{entity_name}'")
            neo4j_task = call_agent_tool(
                agent="graph_query",
                tool="find_entity",
                input_params={"name": entity_name},
                http_client=http_client,
                agent_urls=agent_urls
            )
        else:
            logger.info(f"   ⏭️  Task 1: Skipping Neo4j search (no valid entity)")
            # Create a failed result immediately instead of calling Neo4j
            async def failed_neo4j():
                return ToolResult(success=False, error=f"No valid entity name provided")
            neo4j_task = failed_neo4j()
        
        # TASK 2: Pinecone semantic search (always run)
        logger.info(f"   📍 Task 2: Pinecone semantic search")
        pinecone_task = call_agent_tool(
            agent="indexer",
            tool="semantic_search",
            input_params={
                "query": query,
                "repo_id": "fastapi",
                "top_k": 5
            },
            http_client=http_client,
            agent_urls=agent_urls
        )
        
        # Execute both in parallel
        logger.info("   ⏳ Executing both tasks in parallel...")
        results = await asyncio.gather(neo4j_task, pinecone_task, return_exceptions=True)
        
        neo4j_result = results[0] if len(results) > 0 else None
        pinecone_result = results[1] if len(results) > 1 else None
        
        # Handle exceptions
        if isinstance(neo4j_result, Exception):
            logger.warning(f"   ⚠️  Neo4j search failed: {str(neo4j_result)}")
            neo4j_result = ToolResult(success=False, error=str(neo4j_result))
        
        if isinstance(pinecone_result, Exception):
            logger.warning(f"   ⚠️  Pinecone search failed: {str(pinecone_result)}")
            pinecone_result = ToolResult(success=False, error=str(pinecone_result))
        
        # Log results
        logger.info(f"   ✅ Neo4j: {'Success' if neo4j_result.success else 'Failed'}")
        logger.info(f"   ✅ Pinecone: {'Success' if pinecone_result.success else 'Failed'}")
        # Log detailed results
        logger.info(f"   ✅ Neo4j: {'Success' if neo4j_result.success else 'Failed'}")
        if not neo4j_result.success:
            logger.info(f"       Error: {neo4j_result.error}")
        logger.info(f"   ✅ Pinecone: {'Success' if pinecone_result.success else 'Failed'}")
        if pinecone_result.success:
            chunks_count = len(pinecone_result.data.get("chunks", []))
            logger.info(f"       Found: {chunks_count} code chunks")
        # SCENARIO 1: Both succeeded
        if neo4j_result.success and pinecone_result.success:
            logger.info("   ✅ SCENARIO 1: Both searches succeeded - combining results")
            
            # Normalize Neo4j data to ensure it has the right structure
            neo4j_data = neo4j_result.data or {}
            logger.debug(f"   🔍 Neo4j data structure: {list(neo4j_data.keys())}")
            
            return ToolResult(
                success=True,
                data={
                    "neo4j": {
                        "name": neo4j_data.get("name"),
                        "type": neo4j_data.get("type", "Unknown"),
                        "properties": neo4j_data.get("properties", {})
                    },
                    "pinecone": pinecone_result.data,
                    "scenario": "both_success",
                    "combined": True
                }
            )
        
        # SCENARIO 2: Only Neo4j succeeded
        elif neo4j_result.success:
            logger.info("   ⚠️  SCENARIO 2: Only Neo4j succeeded - using entity results")
            return ToolResult(
                success=True,
                data={
                    "neo4j": neo4j_result.data,
                    "pinecone": None,
                    "scenario": "neo4j_only",
                    "combined": False
                }
            )
        
        # SCENARIO 3: Only Pinecone succeeded
        elif pinecone_result.success:
            logger.info("   ⚠️  SCENARIO 3: Only Pinecone succeeded - using semantic results")
            return ToolResult(
                success=True,
                data={
                    "neo4j": None,
                    "pinecone": pinecone_result.data,
                    "scenario": "pinecone_only",
                    "combined": False
                }
            )
        
        # SCENARIO 4: Both failed - fetch memory context from last 3 chats
        else:
            logger.info("   ❌ SCENARIO 4: Both searches failed - fetching memory context")
            return await _fetch_memory_fallback(postgres_client)
        
    except Exception as e:
        logger.error(f"❌ Parallel search failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))


async def _fetch_memory_fallback(postgres_client: Any) -> ToolResult:
    """
    Fetch last 3 chat turns from memory as fallback.
    
    Args:
        postgres_client: PostgreSQL client
        
    Returns:
        ToolResult with memory context (success=True even if no history found)
    """
    try:
        logger.info("   💾 Fetching memory context from last 3 chats...")
        
        # Query memory WITHOUT session_id to get global recent history
        # This gets the most recent turns across all sessions
        try:
            # Try to get conversation history without session_id filter
            # by querying the database directly for recent turns
            history = await postgres_client.execute_query(
                """
                SELECT id, session_id, turn_number, role, content, created_at
                FROM conversation_turns
                ORDER BY created_at DESC
                LIMIT 6
                """
            )
            
            if history:
                logger.info(f"   ✅ Retrieved {len(history)} recent chat records")
            else:
                logger.info("   ℹ️ No chat history available yet")
                history = []
                
        except Exception as query_err:
            logger.warning(f"   ⚠️  Direct query failed, trying fallback: {query_err}")
            # Fallback: try to get stats or empty list
            history = []
        
        # IMPORTANT: Return success=True even if no history
        # This allows synthesis to work with memory_fallback scenario
        return ToolResult(
            success=True,
            data={
                "neo4j": None,
                "pinecone": None,
                "memory_context": history,
                "scenario": "memory_fallback",
                "combined": False,
                "message": "No search results, using conversation memory as context" if history else "No search results and no memory context available"
            }
        )
        
    except Exception as e:
        logger.error(f"   ❌ Memory fetch failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return success=True with empty context rather than failing
        # This ensures the pipeline doesn't break
        return ToolResult(
            success=True,
            data={
                "neo4j": None,
                "pinecone": None,
                "memory_context": [],
                "scenario": "memory_fallback",
                "combined": False,
                "message": "No search results and memory context unavailable"
            }
        )