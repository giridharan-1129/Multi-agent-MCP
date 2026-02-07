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
            async def failed_neo4j():
                return ToolResult(success=False, error=f"No valid entity name provided")
            neo4j_task = failed_neo4j()
        
        # TASK 1B: Neo4j best entity search (LLM-based disambiguation fallback)
        # This will find the best matching entity if direct lookup fails
        logger.info(f"   📍 Task 1B: Neo4j LLM-based entity disambiguation")
        neo4j_best_entity_task = call_agent_tool(
            agent="graph_query",
            tool="find_best_entity",
            input_params={"query": query, "top_k": 50},
            http_client=http_client,
            agent_urls=agent_urls
        )
        
        # TASK 1C: Neo4j relationships search (EXHAUSTIVE - ALWAYS run)
        logger.info(f"   📍 Task 1C: Neo4j EXHAUSTIVE relationships for '{entity_name}'")
        neo4j_relationships_task = call_agent_tool(
            agent="graph_query",
            tool="find_entity_relationships",
            input_params={"entity_name": entity_name},
            http_client=http_client,
            agent_urls=agent_urls
        )
        
        # TASK 2: Pinecone semantic search (always run)
        logger.info(f"   📍 Task 2: Pinecone semantic search")
        # Enrich query with entity context for better semantic search results
        enriched_query = query
        if has_valid_entity:
            enriched_query = f"{query}\nEntity: {entity_name}"
            logger.info(f"   🔍 Enriched query with entity context: '{entity_name}'")
        
        pinecone_task = call_agent_tool(
            agent="indexer",
            tool="semantic_search",
            input_params={
                "query": enriched_query,
                "repo_id": "fastapi",
                "top_k": 5
            },
            http_client=http_client,
            agent_urls=agent_urls
        )
        
        # Execute all four in parallel
        logger.info("   ⏳ Executing all tasks in parallel...")
        results = await asyncio.gather(
            neo4j_task, 
            neo4j_best_entity_task,
            neo4j_relationships_task, 
            pinecone_task, 
            return_exceptions=True
        )
        
        neo4j_result = results[0] if len(results) > 0 else None
        neo4j_best_entity_result = results[1] if len(results) > 1 else None
        neo4j_relationships_result = results[2] if len(results) > 2 else None
        pinecone_result = results[3] if len(results) > 3 else None
        
        # Handle exceptions
        if isinstance(neo4j_result, Exception):
            logger.warning(f"   ⚠️  Neo4j search failed: {str(neo4j_result)}")
            neo4j_result = ToolResult(success=False, error=str(neo4j_result))
        
        if isinstance(neo4j_best_entity_result, Exception):
            logger.warning(f"   ⚠️  Neo4j best entity search failed: {str(neo4j_best_entity_result)}")
            neo4j_best_entity_result = ToolResult(success=False, error=str(neo4j_best_entity_result))
        
        if isinstance(neo4j_relationships_result, Exception):
            logger.warning(f"   ⚠️  Neo4j relationships search failed: {str(neo4j_relationships_result)}")
            neo4j_relationships_result = ToolResult(success=False, error=str(neo4j_relationships_result))
        
        if isinstance(pinecone_result, Exception):
            logger.warning(f"   ⚠️  Pinecone search failed: {str(pinecone_result)}")
            pinecone_result = ToolResult(success=False, error=str(pinecone_result))
        
        # Log results
        logger.info(f"   ✅ Neo4j Entity: {'Success' if neo4j_result.success else 'Failed'}")
        logger.info(f"   ✅ Neo4j Best Entity (LLM): {'Success' if neo4j_best_entity_result.success else 'Failed'}")
        logger.info(f"   ✅ Neo4j Relationships: {'Success' if neo4j_relationships_result.success else 'Failed'}")
        logger.info(f"   ✅ Pinecone: {'Success' if pinecone_result.success else 'Failed'}")
        
        # Log detailed results
        if not neo4j_result.success:
            logger.info(f"       Entity Error: {neo4j_result.error}")
        if neo4j_best_entity_result.success:
            best_match = neo4j_best_entity_result.data.get("best_match")
            confidence = neo4j_best_entity_result.data.get("confidence", 0)
            logger.info(f"       Best Match: {best_match} (confidence: {confidence})")
        if not neo4j_relationships_result.success:
            logger.info(f"       Relationships Error: {neo4j_relationships_result.error}")
        if pinecone_result.success:
            chunks_count = len(pinecone_result.data.get("chunks", []))
            logger.info(f"       Found: {chunks_count} code chunks")
        # SCENARIO 1: Neo4j entity + relationships + Pinecone all succeeded
        # SCENARIO 1: Try to use best entity match (LLM) if available
        # Fallback: Use initial entity if best entity fails
        if neo4j_best_entity_result.success and neo4j_best_entity_result.data:
            logger.info("   ✅ SCENARIO 1: Using LLM-matched entity")
            
            # Use best entity result
            best_entity_data = neo4j_best_entity_result.data
            best_entity_name = best_entity_data.get("best_match")
            
            # If we have relationships from the best entity, use them
            dependents = best_entity_data.get("dependents", [])
            dependencies = best_entity_data.get("dependencies", [])
            parents = best_entity_data.get("parents", [])
            
            neo4j_entity = {
                "source_type": "neo4j",
                "entity_name": best_entity_name,
                "entity_type": best_entity_data.get("entity_type", "Unknown"),
                "module": best_entity_data.get("module", "N/A"),
                "line_number": best_entity_data.get("line_number", 0),
                "confidence": best_entity_data.get("confidence", 0),
                "disambiguation_reason": best_entity_data.get("reason", ""),
                "dependents": dependents,
                "dependencies": dependencies,
                "parents": parents,
                "dependents_count": best_entity_data.get("dependents_count", 0),
                "dependencies_count": best_entity_data.get("dependencies_count", 0),
                "parents_count": best_entity_data.get("parents_count", 0)
            }
            
            logger.info(f"   📍 Using LLM-matched entity: {best_entity_name}")
            logger.info(f"       Confidence: {best_entity_data.get('confidence', 0)}")
            logger.info(f"       Relationships: {best_entity_data.get('dependents_count', 0)} dependents")
            
            # Format Pinecone chunks
            pinecone_chunks = pinecone_result.data.get("chunks", []) if pinecone_result.success else []
            formatted_chunks = []
            for chunk in pinecone_chunks:
                formatted_chunks.append({
                    "source_type": "pinecone",
                    "chunk_id": chunk.get("chunk_id", ""),
                    "file_name": chunk.get("file_name", "unknown"),
                    "file_path": chunk.get("file_path", "unknown"),
                    "start_line": chunk.get("start_line", 0),
                    "end_line": chunk.get("end_line", 0),
                    "language": chunk.get("language", "python"),
                    "content": chunk.get("content", ""),
                    "preview": chunk.get("preview", ""),
                    "relevance_score": chunk.get("relevance_score", 0),
                    "confidence": chunk.get("confidence", 0),
                    "reranked": chunk.get("reranked", False),
                    "lines": chunk.get("lines", "0-0")
                })
            
            logger.info(f"   📍 Formatted {len(formatted_chunks)} Pinecone chunks for synthesis")
            
            return ToolResult(
                success=True,
                data={
                    "neo4j_entity": neo4j_entity,
                    "pinecone_chunks": formatted_chunks,
                    "pinecone_metadata": {
                        "total_chunks": len(formatted_chunks),
                        "reranked": pinecone_result.data.get("reranked", False) if pinecone_result.success else False,
                        "reranker_model": pinecone_result.data.get("reranker_model") if pinecone_result.success else None
                    },
                    "scenario": "both_success_llm_matched",
                    "combined": True,
                    "llm_disambiguation": True
                }
            )
        
        # SCENARIO 2: Both direct Neo4j search and Pinecone succeeded
        elif neo4j_result.success and pinecone_result.success:
            logger.info("   ✅ SCENARIO 2: Direct entity match + Pinecone")
            
            # (keep existing logic from before)
            neo4j_data = neo4j_result.data or {}
            
            pinecone_chunks = pinecone_result.data.get("chunks", [])
            formatted_chunks = []
            for chunk in pinecone_chunks:
                formatted_chunks.append({
                    "source_type": "pinecone",
                    "chunk_id": chunk.get("chunk_id", ""),
                    "file_name": chunk.get("file_name", "unknown"),
                    "file_path": chunk.get("file_path", "unknown"),
                    "start_line": chunk.get("start_line", 0),
                    "end_line": chunk.get("end_line", 0),
                    "language": chunk.get("language", "python"),
                    "content": chunk.get("content", ""),
                    "preview": chunk.get("preview", ""),
                    "relevance_score": chunk.get("relevance_score", 0),
                    "confidence": chunk.get("confidence", 0),
                    "reranked": chunk.get("reranked", False),
                    "lines": chunk.get("lines", "0-0")
                })

            neo4j_entity = {
                "source_type": "neo4j",
                "entity_name": neo4j_data.get("name", "Unknown"),
                "entity_type": neo4j_data.get("type", "Unknown"),
                "module": neo4j_data.get("properties", {}).get("module", "N/A"),
                "line_number": neo4j_data.get("properties", {}).get("line_number", "N/A"),
                "properties": neo4j_data.get("properties", {})
            }

            # Merge relationships if available
            if neo4j_relationships_result.success and neo4j_relationships_result.data:
                relationships_data = neo4j_relationships_result.data
                neo4j_entity["dependents"] = relationships_data.get("dependents", [])
                neo4j_entity["dependencies"] = relationships_data.get("dependencies", [])
                neo4j_entity["parents"] = relationships_data.get("parents", [])
                neo4j_entity["dependents_count"] = relationships_data.get("dependents_count", 0)
                neo4j_entity["dependencies_count"] = relationships_data.get("dependencies_count", 0)
                neo4j_entity["parents_count"] = relationships_data.get("parents_count", 0)
                logger.info(f"   📊 Merged relationships: {neo4j_entity['dependents_count']} dependents")

            logger.info(f"   📍 Formatted {len(formatted_chunks)} Pinecone chunks for synthesis")

            return ToolResult(
                success=True,
                data={
                    "neo4j_entity": neo4j_entity,
                    "pinecone_chunks": formatted_chunks,
                    "pinecone_metadata": {
                        "total_chunks": len(formatted_chunks),
                        "reranked": pinecone_result.data.get("reranked", False),
                        "reranker_model": pinecone_result.data.get("reranker_model")
                    },
                    "scenario": "both_success",
                    "combined": True,
                    "llm_disambiguation": False
                }
            )
        
        # SCENARIO 2: Neo4j succeeded (with or without Pinecone)
        # ALWAYS include exhaustive relationships if Neo4j entity succeeded
        elif neo4j_result.success:
            logger.info("   ⚠️  SCENARIO 2: Neo4j entity succeeded (Pinecone failed)")
            
            neo4j_data = neo4j_result.data or {}
            relationships_data = neo4j_relationships_result.data or {} if neo4j_relationships_result.success else {}
            
            # Build entity with relationships
            neo4j_entity = {
                "source_type": "neo4j",
                "entity_name": neo4j_data.get("name", "Unknown"),
                "entity_type": neo4j_data.get("type", "Unknown"),
                "module": neo4j_data.get("properties", {}).get("module", "N/A"),
                "line_number": neo4j_data.get("properties", {}).get("line_number", "N/A"),
                "properties": neo4j_data.get("properties", {})
            }
            
            # Merge relationships if available
            if neo4j_relationships_result.success and relationships_data:
                neo4j_entity["dependents"] = relationships_data.get("dependents", [])
                neo4j_entity["dependencies"] = relationships_data.get("dependencies", [])
                neo4j_entity["parents"] = relationships_data.get("parents", [])
                neo4j_entity["dependents_count"] = relationships_data.get("dependents_count", 0)
                neo4j_entity["dependencies_count"] = relationships_data.get("dependencies_count", 0)
                neo4j_entity["parents_count"] = relationships_data.get("parents_count", 0)
                logger.info(f"   ✅ Added exhaustive relationships to entity")
            else:
                neo4j_entity["dependents"] = []
                neo4j_entity["dependencies"] = []
                neo4j_entity["parents"] = []
                neo4j_entity["dependents_count"] = 0
                neo4j_entity["dependencies_count"] = 0
                neo4j_entity["parents_count"] = 0
            
            return ToolResult(
                success=True,
                data={
                    "neo4j_entity": neo4j_entity,
                    "pinecone_chunks": [],
                    "scenario": "neo4j_only",
                    "combined": False,
                    "relationships_exhaustive": neo4j_relationships_result.success
                }
            )
        
        # SCENARIO 3: Only Pinecone succeeded (Neo4j entity failed, but try relationships anyway)
        elif pinecone_result.success:
            logger.info("   ⚠️  SCENARIO 3: Pinecone succeeded (Neo4j entity failed)")
            
            # Format Pinecone chunks
            pinecone_chunks = pinecone_result.data.get("chunks", [])
            formatted_chunks = []
            for chunk in pinecone_chunks:
                formatted_chunks.append({
                    "source_type": "pinecone",
                    "chunk_id": chunk.get("chunk_id", ""),
                    "file_name": chunk.get("file_name", "unknown"),
                    "file_path": chunk.get("file_path", "unknown"),
                    "start_line": chunk.get("start_line", 0),
                    "end_line": chunk.get("end_line", 0),
                    "language": chunk.get("language", "python"),
                    "content": chunk.get("content", ""),
                    "preview": chunk.get("preview", ""),
                    "relevance_score": chunk.get("relevance_score", 0),
                    "confidence": chunk.get("confidence", 0),
                    "reranked": chunk.get("reranked", False),
                    "lines": chunk.get("lines", "0-0")
                })
            
            # Try to add relationships even if entity lookup failed
            relationships_data = neo4j_relationships_result.data or {} if neo4j_relationships_result.success else {}
            relationships_only = {}
            
            if neo4j_relationships_result.success and relationships_data:
                relationships_only = {
                    "source_type": "neo4j",
                    "entity_name": relationships_data.get("entity_name", "Unknown"),
                    "entity_type": relationships_data.get("target_type", "Unknown"),
                    "dependents": relationships_data.get("dependents", []),
                    "dependencies": relationships_data.get("dependencies", []),
                    "parents": relationships_data.get("parents", []),
                    "dependents_count": relationships_data.get("dependents_count", 0),
                    "dependencies_count": relationships_data.get("dependencies_count", 0),
                    "parents_count": relationships_data.get("parents_count", 0)
                }
                logger.info(f"   ✅ Retrieved relationships despite entity lookup failure")
            
            return ToolResult(
                success=True,
                data={
                    "neo4j_entity": relationships_only if relationships_only else None,
                    "pinecone_chunks": formatted_chunks,
                    "scenario": "pinecone_only",
                    "combined": False,
                    "relationships_exhaustive": neo4j_relationships_result.success
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