"""Main orchestration handler - coordinates the entire query execution flow."""

from typing import Any, Dict, List, Optional
from uuid import UUID

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
        
        # ====================================================================
        # STEP 1: ANALYZE QUERY
        # ====================================================================
        logger.info("\n📊 STEP 1: Analyzing query intent...")
        analysis = await analyze_query(query, openai_api_key)
        
        if not analysis.success:
            logger.error(f"❌ Query analysis failed: {analysis.error}")
            return ToolResult(
                success=False, 
                error=f"Query analysis failed: {analysis.error}"
            )
        
        intent = analysis.data.get("intent", "search")
        entities = analysis.data.get("entities", [])
        confidence = analysis.data.get("confidence", 0)
        
        logger.info(f"   ✅ Intent: {intent} (confidence: {confidence:.2f})")
        logger.info(f"   ✅ Entities: {entities}")
        
        # ====================================================================
        # STEP 2: ROUTE TO AGENTS
        # ====================================================================
        logger.info("\n🛣️  STEP 2: Routing to appropriate agents...")
        routing = await route_to_agents(query, intent)
        
        if not routing.success:
            logger.error(f"❌ Routing failed: {routing.error}")
            return ToolResult(
                success=False,
                error=f"Routing failed: {routing.error}"
            )
        
        agent_names = routing.data.get("recommended_agents", ["graph_query"])
        parallel = routing.data.get("parallel", False)
        
        logger.info(f"   ✅ Agents to call: {agent_names}")
        logger.info(f"   ✅ Mode: {'Parallel' if parallel else 'Sequential'}")
        
        # ====================================================================
        # STEP 3: CALL AGENTS
        # ====================================================================
        logger.info(f"\n🤖 STEP 3: Calling {len(agent_names)} agent(s)...")
        agent_results = []
        
        for agent_idx, agent_name in enumerate(agent_names, 1):
            logger.info(f"\n   [{agent_idx}/{len(agent_names)}] Agent: {agent_name}")
            
            # Determine which tool to call for this agent
            tool_name, tool_input = _select_tool_for_agent(
                agent_name, intent, entities, analysis.data
            )
            
            logger.info(f"      Tool: {tool_name}")
            logger.info(f"      Input: {tool_input}")
            
            # Call the agent
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
        
        # ====================================================================
        # STEP 4: SYNTHESIZE RESPONSE
        # ====================================================================
        logger.info(f"\n📝 STEP 4: Synthesizing {len(agent_results)} agent results...")
        
        synthesis = await synthesize_response(agent_results, query)
        
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
        
        return ToolResult(
            success=True,
            data={
                "response": response_text,
                "agents_used": agents_used,
                "intent": intent,
                "entities_found": entities,
                "session_id": str(session_uuid) if session_uuid else session_id,
                "num_agents": len(agent_results)
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
    analysis_data: Dict[str, Any]
) -> tuple:
    """
    Select appropriate tool for agent based on intent and entities.
    
    Returns:
        Tuple of (tool_name, tool_input)
    """
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
        else:
            return ("get_index_status", {})
    
    elif agent_name == "graph_query":
        return (
            "find_entity",
            {"name": entities[0] if entities else "main"}
        )
    
    elif agent_name == "code_analyst":
        return (
            "analyze_function",
            {"name": entities[0] if entities else "main"}
        )
    
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
