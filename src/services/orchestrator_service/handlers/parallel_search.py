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
    Execute Neo4j multi-entity search + Pinecone semantic search IN PARALLEL.
    
    Flow:
    1. Task 1: Direct entity lookup (if valid entity name)
    2. Task 1B: MULTI-ENTITY analysis (find top-5 relevant entities + all relationships)
    3. Task 2: Exhaustive relationships for direct entity
    4. Task 3: Pinecone semantic search
    """
    try:
        logger.info("🔄 PARALLEL_SEARCH: Starting parallel entity + semantic search...")
        logger.info(f"   📝 Query: {query[:80]}...")
        logger.info(f"   🎯 Entity name: '{entity_name}'")
        
        # Check if entity_name is valid (not "unknown" or empty)
        has_valid_entity = entity_name and entity_name.lower() != "unknown"
        logger.info(f"   ✓ Valid entity: {has_valid_entity}")
        
        # TASK 1: SKIPPED - Use comprehensive_entity_analysis instead (handles both entity finding + relationships)
        # The comprehensive_entity_analysis tool is superior as it:
        # - Finds multiple relevant entities (not just one)
        # - Automatically fetches relationships for each
        # - Uses LLM to rank by relevance
        # So we skip the direct find_entity call
        logger.info(f"   📍 [TASK 1] SKIPPED - find_entity tool doesn't exist")
        logger.info(f"      → Using comprehensive_entity_analysis instead (does both entity finding + relationships)")
        async def skipped_neo4j():
            return ToolResult(success=False, error="Skipped - using comprehensive_entity_analysis instead")
        neo4j_task = skipped_neo4j()
        
        # TASK 1B: Comprehensive entity analysis (THE MAIN TASK)
        logger.info(f"   📍 [TASK 1B] Comprehensive entity analysis (LLM rank top-5 entities + relationships)")
        logger.debug(f"      Agent: graph_query | Tool: comprehensive_entity_analysis")
        logger.debug(f"      Query: {query[:80]}... | Top K: 5")
        neo4j_all_entities_task = call_agent_tool(
            agent="graph_query",
            tool="comprehensive_entity_analysis",
            input_params={"query": query, "top_k": 5},
            http_client=http_client,
            agent_urls=agent_urls
        )
        
        # TASK 1C: SKIPPED - comprehensive_entity_analysis already fetches ALL relationships
        # No need to call it twice - Task 1B already includes relationship fetching
        logger.info(f"   📍 [TASK 1C] SKIPPED - relationships already fetched in Task 1B")
        async def skipped_rel():
            return ToolResult(success=False, error="Skipped - comprehensive_entity_analysis handles this")
        neo4j_relationships_task = skipped_rel()
        
        # TASK 2: Pinecone semantic search
        logger.info(f"   📍 [TASK 2] Pinecone semantic search")
        logger.debug(f"      Agent: indexer | Tool: semantic_search")
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
        
        # Execute all 4 tasks in parallel
        logger.info("   ⏳ Executing all 4 tasks in parallel...")
        results = await asyncio.gather(
            neo4j_task,
            neo4j_all_entities_task,
            neo4j_relationships_task,
            pinecone_task,
            return_exceptions=True
        )
        
        logger.info(f"\n   ⏳ [RESULTS] Processing {len(results)} task results...")
        
        neo4j_result = results[0] if len(results) > 0 else None
        neo4j_all_entities_result = results[1] if len(results) > 1 else None
        neo4j_relationships_result = results[2] if len(results) > 2 else None
        pinecone_result = results[3] if len(results) > 3 else None
        
        logger.info(f"   Task 1 result type: {type(neo4j_result).__name__}")
        logger.info(f"   Task 1B result type: {type(neo4j_all_entities_result).__name__}")
        logger.info(f"   Task 1C result type: {type(neo4j_relationships_result).__name__}")
        logger.info(f"   Task 2 result type: {type(pinecone_result).__name__}")
        
        # Handle exceptions
        if isinstance(neo4j_result, Exception):
            logger.error(f"   ❌ [TASK 1] Exception occurred: {type(neo4j_result).__name__}")
            logger.error(f"      Message: {str(neo4j_result)}")
            neo4j_result = ToolResult(success=False, error=str(neo4j_result))
        
        if isinstance(neo4j_all_entities_result, Exception):
            logger.error(f"   ❌ [TASK 1B] Exception occurred: {type(neo4j_all_entities_result).__name__}")
            logger.error(f"      Message: {str(neo4j_all_entities_result)}")
            neo4j_all_entities_result = ToolResult(success=False, error=str(neo4j_all_entities_result))
        
        if isinstance(neo4j_relationships_result, Exception):
            logger.error(f"   ❌ [TASK 1C] Exception occurred: {type(neo4j_relationships_result).__name__}")
            logger.error(f"      Message: {str(neo4j_relationships_result)}")
            neo4j_relationships_result = ToolResult(success=False, error=str(neo4j_relationships_result))
        
        if isinstance(pinecone_result, Exception):
            logger.error(f"   ❌ [TASK 2] Exception occurred: {type(pinecone_result).__name__}")
            logger.error(f"      Message: {str(pinecone_result)}")
            pinecone_result = ToolResult(success=False, error=str(pinecone_result))
        
        # Log results
        logger.info(f"\n   [RESULT SUMMARY]")
        logger.info(f"   Task 1 (Neo4j Direct): SKIPPED (not available - using Task 1B instead)")
        
        logger.info(f"   Task 1B (Neo4j Multi-Entity + Relationships): {'✅ SUCCESS' if neo4j_all_entities_result.success else '❌ FAILED'}")
        if neo4j_all_entities_result.success and neo4j_all_entities_result.data:
            relevant_count = len(neo4j_all_entities_result.data.get("relevant_entities", []))
            total_rels = neo4j_all_entities_result.data.get("total_relationships", 0)
            logger.info(f"      Found: {relevant_count} entities with {total_rels} total relationships")
        else:
            logger.error(f"      Error: {neo4j_all_entities_result.error}")
        
        logger.info(f"   Task 1C (Neo4j Relationships): SKIPPED (already in Task 1B)")
        
        logger.info(f"   Task 2 (Pinecone): {'✅ SUCCESS' if pinecone_result.success else '❌ FAILED'}")
        if pinecone_result.success and pinecone_result.data:
            chunks_count = len(pinecone_result.data.get("chunks", []))
            logger.info(f"      Found: {chunks_count} code chunks")
        else:
            logger.error(f"      Error: {pinecone_result.error}")
        
        # Log detailed results
        if not neo4j_result.success:
            logger.info(f"       Direct Error: {neo4j_result.error}")
        if neo4j_all_entities_result.success:
            entities_count = neo4j_all_entities_result.data.get("relevant_count", 0)
            total_relationships = neo4j_all_entities_result.data.get("total_relationships", 0)
            logger.info(f"       Multi-Entity: Found {entities_count} relevant entities with {total_relationships} total relationships")
        if not neo4j_relationships_result.success:
            logger.info(f"       Relationships Error: {neo4j_relationships_result.error}")
        if pinecone_result.success:
            chunks_count = len(pinecone_result.data.get("chunks", []))
            logger.info(f"       Found: {chunks_count} code chunks")
        
        # ============================================================================
        # SCENARIO ROUTING: Choose best combination of results
        # ============================================================================
        
        # SCENARIO 1: Multi-entity analysis succeeded AND found entities
        if neo4j_all_entities_result.success and neo4j_all_entities_result.data:
            all_entities_data = neo4j_all_entities_result.data
            relevant_entities = all_entities_data.get("relevant_entities", [])
            
            # Check if we actually got entities back
            if relevant_entities and len(relevant_entities) > 0:
                logger.info("   ✅ SCENARIO 1: Using MULTI-ENTITY analysis (comprehensive)")
                
                # Format all entities with their relationships
                formatted_entities = []
                for entity in relevant_entities:
                    formatted_entities.append({
                        "source_type": "neo4j",
                        "entity_name": entity.get("entity_name"),
                        "entity_type": entity.get("entity_type"),
                        "confidence": entity.get("confidence"),
                        "reason": entity.get("reason"),
                        "module": entity.get("module"),
                        "line_number": entity.get("line_number"),
                        "dependents": entity.get("dependents", []),
                        "dependencies": entity.get("dependencies", []),
                        "parents": entity.get("parents", []),
                        "dependents_count": entity.get("dependents_count", 0),
                        "dependencies_count": entity.get("dependencies_count", 0),
                        "parents_count": entity.get("parents_count", 0)
                    })
                
                logger.info(f"   📍 Formatted {len(formatted_entities)} relevant entities with relationships")
            else:
                # Initialize empty list if no entities found
                formatted_entities = []
                logger.info("   ⚠️  SCENARIO 1B: Multi-entity analysis returned empty results, falling through to Pinecone")
            
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
                    "neo4j_entities": formatted_entities,  # PLURAL - multiple entities
                    "pinecone_chunks": formatted_chunks,
                    "pinecone_metadata": {
                        "total_chunks": len(formatted_chunks),
                        "reranked": pinecone_result.data.get("reranked", False) if pinecone_result.success else False,
                        "reranker_model": pinecone_result.data.get("reranker_model") if pinecone_result.success else None
                    },
                    "scenario": "multi_entity_analysis",
                    "combined": True,
                    "multi_entity": True,
                    "entities_count": len(formatted_entities),
                    "total_relationships": sum(e.get("dependents_count", 0) + e.get("dependencies_count", 0) + e.get("parents_count", 0) for e in formatted_entities)
                }
            )


        # SCENARIO 2: Direct entity + relationships succeeded
        elif neo4j_result.success and neo4j_relationships_result.success:
            logger.info("   ✅ SCENARIO 2: Direct entity + exhaustive relationships")
            
            neo4j_data = neo4j_result.data or {}
            relationships_data = neo4j_relationships_result.data or {}
            
            neo4j_entity = {
                "source_type": "neo4j",
                "entity_name": neo4j_data.get("name", "Unknown"),
                "entity_type": neo4j_data.get("type", "Unknown"),
                "module": neo4j_data.get("properties", {}).get("module", "N/A"),
                "line_number": neo4j_data.get("properties", {}).get("line_number", "N/A"),
                "properties": neo4j_data.get("properties", {}),
                "dependents": relationships_data.get("dependents", []),
                "dependencies": relationships_data.get("dependencies", []),
                "parents": relationships_data.get("parents", []),
                "dependents_count": relationships_data.get("dependents_count", 0),
                "dependencies_count": relationships_data.get("dependencies_count", 0),
                "parents_count": relationships_data.get("parents_count", 0)
            }
            
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
                    "neo4j_entity": neo4j_entity,  # SINGULAR
                    "pinecone_chunks": formatted_chunks,
                    "pinecone_metadata": {
                        "total_chunks": len(formatted_chunks),
                        "reranked": pinecone_result.data.get("reranked", False) if pinecone_result.success else False,
                        "reranker_model": pinecone_result.data.get("reranker_model") if pinecone_result.success else None
                    },
                    "scenario": "direct_entity",
                    "combined": True,
                    "multi_entity": False
                }
            )
        
        # SCENARIO 3: Only Pinecone succeeded
        elif pinecone_result.success:
            logger.info("   ⚠️  SCENARIO 3: Only Pinecone succeeded (using semantic search)")
            
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
            
            return ToolResult(
                success=True,
                data={
                    "neo4j_entities": [],
                    "pinecone_chunks": formatted_chunks,
                    "pinecone_metadata": {
                        "total_chunks": len(formatted_chunks),
                        "reranked": pinecone_result.data.get("reranked", False),
                        "reranker_model": pinecone_result.data.get("reranker_model")
                    },
                    "scenario": "pinecone_only",
                    "combined": False,
                    "multi_entity": False
                }
            )
        
        # SCENARIO 4: All searches failed - fetch memory fallback
        else:
            logger.info("   ❌ SCENARIO 4: All searches failed - fetching memory context")
            return await _fetch_memory_fallback(postgres_client)
        
    except Exception as e:
        logger.error(f"❌ Parallel search failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))


async def _fetch_memory_fallback(postgres_client: Any) -> ToolResult:
    """
    Fetch last 3 chat turns from memory as fallback.
    """
    try:
        logger.info("   💾 Fetching memory context from last 3 chats...")
        
        try:
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
            logger.warning(f"   ⚠️  Direct query failed: {query_err}")
            history = []
        
        return ToolResult(
            success=True,
            data={
                "neo4j_entities": [],
                "pinecone_chunks": [],
                "memory_context": history,
                "scenario": "memory_fallback",
                "combined": False,
                "multi_entity": False,
                "message": "No search results, using conversation memory as context" if history else "No search results and no memory context available"
            }
        )
        
    except Exception as e:
        logger.error(f"   ❌ Memory fetch failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return ToolResult(
            success=True,
            data={
                "neo4j_entities": [],
                "pinecone_chunks": [],
                "memory_context": [],
                "scenario": "memory_fallback",
                "combined": False,
                "multi_entity": False,
                "message": "No search results and memory context unavailable"
            }
        )