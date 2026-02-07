"""Main orchestration handler - coordinates the entire query execution flow."""

from typing import Any, Dict, List, Optional
from uuid import UUID
from .parallel_search import parallel_entity_and_semantic_search

from ....shared.mcp_server import ToolResult

from ....shared.postgres_client import PostgreSQLClientManager
from ....shared.logger import get_logger
from .query_analysis import analyze_query
from .routing import route_to_agents
from .agent_calls import call_agent_tool
from .synthesis import synthesize_response

logger = get_logger(__name__)


async def execute_query(
    query: str,
    session_id: Optional[str],
    openai_api_key: str,
    http_client: Any,
    postgres_client: PostgreSQLClientManager,
    agent_urls: Dict[str, str]
) -> ToolResult:
    """
    Complete orchestration pipeline for a user query.
    
    Flow:
    1. Analyze query intent with GPT-4
    2. Route to appropriate agents
    3. Call agents in parallel/sequence
    4. Synthesize agent outputs into response
    5. Store conversation for context
    6. Return final response to user
    """
    try:
        logger.info("=" * 80)
        logger.info(f"🎯 ORCHESTRATOR: Query received")
        logger.info(f"   Query: {query[:100]}...")
        logger.info(f"   Session: {session_id or 'NEW'}")
        logger.info("=" * 80)
        
        ## ====================================================================
        # STEP 0: GET PREVIOUS CHAT CONTEXT FROM MEMORY
        # ====================================================================
        logger.info("\n💭 STEP 0: Fetching previous conversation context...")
        
        previous_context = ""
        try:
            
            # Call memory service to get chat history
            memory_result = await call_agent_tool(
                agent="memory",
                tool="get_context",
                input_params={
                    "session_id": session_id or "new",
                    "last_n_turns": 3  # Get last 3 turns for context
                },
                http_client=http_client,
                agent_urls=agent_urls
            )
            
            if memory_result.success and memory_result.data:
                context_turns = memory_result.data.get("context_turns", [])
                logger.info(f"   ✅ Retrieved {len(context_turns)} previous turns")
                
                # Build context string from previous turns
                if context_turns:
                    previous_context = "\n\n".join([
                        f"[{turn.get('role', 'unknown').upper()}]: {turn.get('content', '')}"
                        for turn in context_turns
                    ])
                    logger.debug(f"   📝 Context preview: {previous_context[:100]}...")
            else:
                logger.info(f"   ℹ️  No previous context found (new session)")
                
        except Exception as ctx_err:
            logger.warning(f"   ⚠️  Failed to fetch context (continuing): {ctx_err}")
            previous_context = ""
        
        # ====================================================================
        # STEP 1: ANALYZE QUERY (WITH CONTEXT)
        # ====================================================================
        logger.info("\n📊 STEP 1: Analyzing query intent...")
        
        # If we have context, include it in the analysis
        enriched_query = query
        if previous_context:
            enriched_query = f"Previous conversation:\n{previous_context}\n\nNew query:\n{query}"
            logger.info(f"   📚 Query enriched with {len(previous_context)} chars of context")
        
        analysis = await analyze_query(enriched_query, openai_api_key)
        
        if not analysis.success:
            logger.error(f"❌ Query analysis failed: {analysis.error}")
            return ToolResult(
                success=False, 
                error=f"Query analysis failed: {analysis.error}"
            )
        
        intent = analysis.data.get("intent", "search")
        entities = analysis.data.get("entities", [])
        confidence = analysis.data.get("confidence", 0)
        
        # Clean entity names (remove class/function/method suffixes)
        cleaned_entities = []
        for entity in entities:
            cleaned = entity.strip()
            for suffix in [" class", " function", " method", " module", " file", " package"]:
                if cleaned.lower().endswith(suffix):
                    cleaned = cleaned[:-len(suffix)].strip()
            cleaned_entities.append(cleaned)
        
        entities = cleaned_entities
        
        logger.info(f"Intent: {intent} (confidence: {confidence:.2f})")
        logger.info(f"Entities: {entities}")
        
        # ====================================================================
        # STEP 2: ROUTE TO AGENTS
        # ====================================================================
        logger.info("STEP 2: Routing to appropriate agents...")
        routing = await route_to_agents(query, intent)
        
        if not routing.success:
            logger.error(f"Routing failed: {routing.error}")
            return ToolResult(
                success=False,
                error=f"Routing failed: {routing.error}"
            )
        
        agent_names = routing.data.get("recommended_agents", ["graph_query"])
        parallel = routing.data.get("parallel", False)
        intent = routing.data.get("intent", intent)  # ← ADD THIS LINE to update intent from routing
        
        logger.info(f"Agents to call: {agent_names}")
        logger.info(f"Mode: {'Parallel' if parallel else 'Sequential'}")
        
                # ====================================================================
        # STEP 3: CALL AGENTS IN PARALLEL
        # ====================================================================
        import asyncio
        logger.info(f"STEP 3: Calling {len(agent_names)} agent(s) in PARALLEL...")
        agent_results = []
        entity_name = entities[0] if entities else "unknown"
        
        # Check if we have graph_query + other agents for parallel execution
        # ALWAYS do parallel search for search/explain intents (Neo4j + Pinecone in parallel)
        # SKIP parallel search for admin operations
        if intent in ["search", "explain", "analyze"] and "graph_query" in agent_names and intent != "admin":
            logger.info("   🔄 Parallel search scenario: Neo4j + Pinecone")
            
            # Execute parallel entity + semantic search first
            logger.info("   📍 Starting parallel Neo4j + Pinecone search...")
            parallel_result = await parallel_entity_and_semantic_search(
                query=query,
                entity_name=entity_name,
                openai_api_key=openai_api_key,
                http_client=http_client,
                postgres_client=postgres_client,
                agent_urls=agent_urls
            )
            
            # Add parallel search results
            agent_results.append({
                "agent": "graph_query",
                "tool": "parallel_search",
                "success": parallel_result.success,
                "data": parallel_result.data,
                "error": parallel_result.error,
                "scenario": parallel_result.data.get("scenario") if parallel_result.success else None
            })
            
            # If other agents exist (like code_analyst), call them
            other_agents = [a for a in agent_names if a != "graph_query"]
            for agent_name in other_agents:
                logger.info(f"\n   [{len(agent_results)+1}/{len(agent_names)}] Agent: {agent_name}")
                
                tool_name, tool_input = _select_tool_for_agent(
                    agent_name, intent, entities, analysis.data, query
                )
                
                logger.info(f"      Tool: {tool_name}")
                logger.info(f"      Input: {tool_input}")
                
                agent_call = await call_agent_tool(
                    agent=agent_name,
                    tool=tool_name,
                    input_params=tool_input,
                    http_client=http_client,
                    agent_urls=agent_urls
                )
                
                if agent_call.success:
                    logger.info(f"      ✅ Success")
                else:
                    logger.error(f"      ❌ Error: {agent_call.error}")
                
                agent_results.append({
                    "agent": agent_name,
                    "tool": tool_name,
                    "success": agent_call.success,
                    "data": agent_call.data if agent_call.success else None,
                    "error": agent_call.error
                })
        
        else:
            # Sequential execution for single agent or non-graph_query scenarios
            logger.info("   ⏳ Sequential execution mode")
            
            for agent_idx, agent_name in enumerate(agent_names, 1):
                logger.info(f"\n   [{agent_idx}/{len(agent_names)}] Agent: {agent_name}")
                
                tool_name, tool_input = _select_tool_for_agent(
                    agent_name, intent, entities, analysis.data, query
                )
                
                logger.info(f"      Tool: {tool_name}")
                logger.info(f"      Input: {tool_input}")
                
                # Special handling for admin operations (clear/delete)
                if tool_name == "admin_clear":
                    logger.info("   🔴 ADMIN OPERATION: Clearing all indexes")
                    
                    # Call both clear tools sequentially
                    results = []
                    
                    # 1. Clear Neo4j
                    logger.info("      [1/2] Calling clear_index...")
                    clear_neo4j = await call_agent_tool(
                        agent=agent_name,
                        tool="clear_index",
                        input_params={},
                        http_client=http_client,
                        agent_urls=agent_urls
                    )
                    results.append(("clear_index", clear_neo4j))
                    logger.info(f"      ✅ Neo4j cleared: {clear_neo4j.success}")
                    
                    # 2. Clear Pinecone
                    logger.info("      [2/2] Calling clear_embeddings...")
                    clear_pinecone = await call_agent_tool(
                        agent=agent_name,
                        tool="clear_embeddings",
                        input_params={"repo_id": "all"},
                        http_client=http_client,
                        agent_urls=agent_urls
                    )
                    results.append(("clear_embeddings", clear_pinecone))
                    logger.info(f"      ✅ Pinecone cleared: {clear_pinecone.success}")
                    
                    # Store combined result
                    agent_results.append({
                        "agent": agent_name,
                        "tool": "admin_clear",
                        "success": all(r[1].success for r in results),
                        "data": {
                            "clear_index": results[0][1].data if results[0][1].success else None,
                            "clear_embeddings": results[1][1].data if results[1][1].success else None,
                            "message": "Both Neo4j and Pinecone have been cleared"
                        },
                        "error": None
                    })
                    continue  # Skip normal tool call
                
                # Normal tool execution
                agent_call = await call_agent_tool(
                    agent=agent_name,
                    tool=tool_name,
                    input_params=tool_input,
                    http_client=http_client,
                    agent_urls=agent_urls
                )
                
                if agent_call.success:
                    logger.info(f"      ✅ Success")
                else:
                    logger.error(f"      ❌ Error: {agent_call.error}")
                
                agent_results.append({
                    "agent": agent_name,
                    "tool": tool_name,
                    "success": agent_call.success,
                    "data": agent_call.data if agent_call.success else None,
                    "error": agent_call.error
                })
        
        logger.info(f"\n📝 STEP 4: Synthesizing {len(agent_results)} agent results...")
                
        synthesis = await synthesize_response(
            agent_results=agent_results,
            original_query=query,
            openai_api_key=openai_api_key,
            previous_context=previous_context
        )
        
        # Safety check: synthesis should never be None, but handle it gracefully
        if synthesis is None:
            logger.error(f"❌ Synthesis returned None")
            return ToolResult(
                success=False,
                error="Response synthesis failed - returned None"
            )
        
        if not synthesis.success:
            logger.error(f"❌ Synthesis failed: {synthesis.error}")
            return ToolResult(
                success=False,
                error=f"Synthesis failed: {synthesis.error}"
            )
        
        response_text = synthesis.data.get("response", "No response generated")
        agents_used = synthesis.data.get("agents_used", [])
        
        logger.info(f"   ✅ Response synthesized")
        logger.info(f"   ✅ Response length: {len(response_text)} chars")
        logger.info(f"   ✅ Agents involved: {agents_used}")
        
        # ====================================================================
        # STEP 5: STORE CONVERSATION
        # ====================================================================
        logger.info(f"\n💾 STEP 5: Storing conversation...")
        session_uuid = None
        
        try:
            session_uuid = await _store_conversation(
                query, response_text, agents_used, session_id, postgres_client
            )
            logger.info(f"   ✅ Stored in session: {session_uuid}")
        except Exception as store_err:
            logger.warning(f"   ⚠️  Storage failed (continuing): {store_err}")
        
        # ====================================================================
        # RETURN FINAL RESULT
        # ====================================================================
        logger.info("\n" + "=" * 80)
        logger.info(f"✅ ORCHESTRATION COMPLETE")
        logger.info(f"   Status: SUCCESS")
        logger.info(f"   Agents used: {agents_used}")
        logger.info(f"   Session: {session_uuid}")
        logger.info("=" * 80 + "\n")
        
        # Extract retrieved sources from synthesis data
        retrieved_sources = synthesis.data.get("retrieved_sources", [])
        sources_count = synthesis.data.get("sources_count", 0)
        reranked_results = synthesis.data.get("reranked_results", False)
        
        logger.info(f"   📍 Retrieved sources: {sources_count}")
        logger.info(f"   📍 Reranked results: {reranked_results}")
        
        return ToolResult(
            success=True,
            data={
                "response": response_text,
                "agents_used": agents_used,
                "intent": intent,
                "entities_found": entities,
                "session_id": str(session_uuid) if session_uuid else session_id,
                "num_agents": len(agent_results),
                "retrieved_sources": retrieved_sources,  # ← ADD
                "sources_count": sources_count,  # ← ADD
                "reranked_results": reranked_results,  # ← ADD
                "previous_context_used": bool(previous_context)  # ← ADD
            }
        )
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ ORCHESTRATION FAILED")
        logger.error(f"   Error: {str(e)}")
        logger.error("=" * 80)
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))


def _select_tool_for_agent(
    agent_name: str,
    intent: str,
    entities: List[str],
    analysis_data: Dict[str, Any],
    query: str = ""  # ← ADD query parameter
) -> tuple:
    """
    Select appropriate tool for agent based on intent and entities.
    
    Returns:
        Tuple of (tool_name, tool_input)
    """
    # Get first entity (already cleaned by caller)
    entity_name = entities[0] if entities else "main"
    
    if agent_name == "indexer":
        if intent == "index":
            return (
                "index_repository",
                {
                    "repo_url": analysis_data.get("repo_url", ""),
                    "branch": "main"
                }
            )
        elif intent == "embed":
            repo_url = analysis_data.get("repo_url", "")
            repo_id = repo_url.split("/")[-1].replace(".git", "") if repo_url else "repo"
            return (
                "embed_repository",
                {
                    "repo_url": repo_url,
                    "repo_id": repo_id,
                    "branch": "main"
                }
            )
        elif intent == "admin":
            # Admin queries: clear database and embeddings
            # Return special marker for orchestration to call both tools
            return (
                "admin_clear",  # Special tool name
                {
                    "action": "clear_all",
                    "repo_id": "all"
                }
            )
        else:
            return ("get_index_status", {})
    
    elif agent_name == "graph_query":
        # Check for admin operations first
        if intent == "admin":
            return (
                "admin_clear",
                {
                    "action": "clear_all",
                    "repo_id": "all"
                }
            )
        # For index/embed, skip graph_query (only call indexer)
        # This is handled by routing, so we shouldn't reach here
        # But if we do, return a safe default
        if intent in ["index", "embed"]:
            logger.warning(f"⚠️ graph_query called for {intent} intent - should not happen. Routing error.")
            return (
                "find_entity",
                {"name": entity_name}
            )
        # For analyze intent, get both entity info AND relationships
        if intent == "analyze":
            return (
                "find_entity_relationships",
                {"entity_name": entity_name}
            )
        return (
            "find_entity",
            {"name": entity_name}
        )
    
    elif agent_name == "code_analyst":
        # Select tool based on intent
        if intent == "compare":
            # For compare intent, we need 2 entities - use first if available
            entity2 = entities[1] if len(entities) > 1 else entity_name
            return ("compare_implementations", {"entity1": entity_name, "entity2": entity2})
        elif intent == "pattern":
            return ("find_patterns", {"pattern_type": entity_name})
        elif intent == "explain":
            # Explain what a specific entity does
            return ("explain_implementation", {"entity_name": entity_name})
        elif intent == "analyze":
            # Analyze if it's a class or function - default to analyze_class
            return ("analyze_class", {"name": entity_name})
        else:
            # Default to function analysis
            return ("analyze_function", {"name": entity_name})

    else:
        return ("get_index_status", {})


async def _store_conversation(
    query: str,
    response_text: str,
    agents_used: List[str],
    session_id: Optional[str],
    postgres_client: PostgreSQLClientManager
) -> Optional[UUID]:
    """
    Store conversation turn in database.
    
    Returns:
        Session UUID or None if storage failed
    """
    try:
        if not session_id:
            logger.debug("No session provided, creating new session")
            session_id = str(UUID(int=0))
        
        session_uuid = UUID(session_id) if isinstance(session_id, str) else session_id
        
        # Get or create session
        existing_session = await postgres_client.get_session(session_uuid)
        if not existing_session:
            existing_session = await postgres_client.create_session(
                user_id="anonymous",
                session_name=f"Query: {query[:50]}"
            )
            session_uuid = existing_session.id
        
        # Get turn count
        history = await postgres_client.get_conversation_history(session_uuid, limit=1)
        turn_number = len(history) + 1
        
        # Store user query
        user_turn = await postgres_client.store_turn(
            session_id=session_uuid,
            turn_number=turn_number,
            role="user",
            content=query
        )
        
        # Store assistant response
        assistant_turn = await postgres_client.store_turn(
            session_id=session_uuid,
            turn_number=turn_number + 1,
            role="assistant",
            content=response_text
        )
        
        # Store agent metadata
        await postgres_client.store_agent_response(
            turn_id=assistant_turn.id,
            agent_name="orchestrator",
            tools_used=agents_used,
            result=response_text
        )
        
        return session_uuid
        
    except Exception as e:
        logger.error(f"Failed to store conversation: {e}")
        raise
