"""Synthesis handler - combines multiple agent outputs into coherent response."""

from typing import Any, Dict, List

from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)

async def synthesize_response(
    agent_results: List[Dict[str, Any]],
    original_query: str,
    openai_api_key: str = None,
    previous_context: str = ""  # ← ADD THIS
) -> ToolResult:
    """
    Combine agent outputs into a coherent response using LLM synthesis.
    
    Flow:
    1. Collect all available context (Neo4j, Pinecone, Code Analyst, Memory)
    2. If we have ANY context: use GPT-4 to synthesize natural response
    3. If no context: use memory fallback or graceful message
    
    Args:
        agent_results: List of results from agents OR dict with parallel_search result
        original_query: Original user query
        openai_api_key: Optional OpenAI API key for LLM synthesis
        
    Returns:
        ToolResult with synthesized response (always success=True)
    """
    try:
        logger.info(f"📝 SYNTHESIS: Starting with {len(agent_results)} agent results")
        logger.info(f"   Previous context: {'Yes' if previous_context else 'No'}")
        if previous_context:
            logger.debug(f"   Context: {previous_context[:100]}...")
        if not agent_results:
            return ToolResult(
                success=True,
                data={
                    "response": "I couldn't find any information to answer your query. Please try rephrasing or asking about a specific part of the codebase.",
                    "agents_used": [],
                    "retrieved_sources": []
                }
            )
        
        # ====================================================================
        # STEP 1: EXTRACT CONTEXT FROM ALL AGENTS
        # ====================================================================
        neo4j_context = []
        pinecone_context = []
        code_analyst_context = []
        memory_context = []
        agents_used = set()
        retrieved_sources = []
        parallel_scenario = None
        
        # Handle both list of results and single parallel_search result
        results_to_process = agent_results if isinstance(agent_results, list) else [agent_results]
        
        for result in results_to_process:
            if result is None:
                continue
            
            agent_name = result.get("agent", "Unknown")
            data = result.get("data", {}) or {}
            success = result.get("success", False)
            tool_name = result.get("tool", "unknown_tool")
            
            if success:
                agents_used.add(agent_name)
            
            # Handle parallel_search result (from parallel_entity_and_semantic_search)
            if tool_name == "parallel_search" or "scenario" in data:
                parallel_scenario = data.get("scenario")
                logger.info(f"📍 Parallel search scenario: {parallel_scenario}")
                
                # SCENARIO 1: both_success - both Neo4j and Pinecone returned results
                if data.get("neo4j"):
                    neo4j_context.append(data.get("neo4j"))
                    agents_used.add("graph_query")
                    
                    # Extract Neo4j entity as source
                    neo4j_data = data.get("neo4j", {})
                    logger.debug(f"   🔍 Neo4j data: {neo4j_data}")
                    
                    # Defensive checks: ensure we have valid data
                    if neo4j_data and isinstance(neo4j_data, dict):
                        entity_name = neo4j_data.get("name")
                        entity_type = neo4j_data.get("type", "Unknown")
                        
                        if entity_name:  # Only create source if we have a name
                            neo4j_source = {
                                "source_type": "neo4j",
                                "type": "entity",
                                "entity_name": entity_name,
                                "entity_type": entity_type,
                                "module": neo4j_data.get("properties", {}).get("module", "N/A"),
                                "line_number": neo4j_data.get("properties", {}).get("line_number"),
                                "properties": neo4j_data.get("properties", {})
                            }
                            retrieved_sources.append(neo4j_source)
                            logger.info(f"      ✅ Neo4j entity: {entity_name} ({entity_type})")
                        else:
                            logger.warning(f"   ⚠️  Neo4j data missing 'name' field: {neo4j_data}")
                    else:
                        logger.warning(f"   ⚠️  Neo4j data is not a valid dict: {neo4j_data}")
                
                if data.get("pinecone"):
                    pinecone_context.append(data.get("pinecone"))
                    agents_used.add("code_analyst") 
                    # Extract chunks for sources - COMPLETE information
                    chunks = data.get("pinecone", {}).get("chunks", [])
                    logger.info(f"   📍 Extracting {len(chunks)} Pinecone chunks as sources")
                    for idx, chunk in enumerate(chunks, 1):
                        # Get full code content - try multiple field names
                        # Pinecone can return: preview (short), content (full), or both
                        code_content = chunk.get("content")
                        if not code_content:
                            code_content = chunk.get("preview", "")
                        
                                                # Get full code content - try multiple field names
                        full_code = chunk.get("content") or chunk.get("preview", "")
                        
                        source = {
                            "source_type": "pinecone",
                            "type": "code_chunk",
                            "file_name": chunk.get("file_name", "unknown"),
                            "file_path": chunk.get("file_path", ""),
                            "start_line": chunk.get("start_line", 0),
                            "end_line": chunk.get("end_line", 0),
                            "lines": chunk.get("lines", "0-0"),
                            "language": chunk.get("language", "python"),
                            "content": full_code,
                            "preview": chunk.get("preview", "")[:200],
                            "relevance_score": round(chunk.get("relevance_score", 0), 3),
                            "confidence": round(chunk.get("confidence", 0), 3),
                            "reranked": chunk.get("reranked", False),
                            "chunk_id": chunk.get("chunk_id", "")
                        }
                        retrieved_sources.append(source)
                        logger.debug(f"      Chunk {idx}: {source['file_name']} (relevance: {source['relevance_score']}, reranked: {source['reranked']})")
                
                # SCENARIO 4: memory_fallback - use conversation memory as context
                if data.get("memory_context"):
                    memory_context = data.get("memory_context", [])
                    agents_used.add("memory")
            
            # Handle code_analyst results
            elif agent_name == "code_analyst" and success:
                code_analyst_context.append({
                    "tool": tool_name,
                    "data": data
                })
            
            # Handle regular graph_query
            elif agent_name == "graph_query" and success and tool_name != "parallel_search":
                neo4j_context.append(data)
        
        # ====================================================================
        # STEP 2: BUILD CONTEXT FOR LLM
        # ====================================================================
# ====================================================================
        # STEP 2: BUILD CONTEXT FOR LLM
        # ====================================================================
        context_parts = []
        scenario_info = f"[{parallel_scenario.upper()}]" if parallel_scenario else ""
        
        if neo4j_context:
            context_parts.append("📊 **Neo4j Graph Data:**\n" + _format_context(neo4j_context))
        
        if pinecone_context:
            context_parts.append("🔍 **Semantic Search Results:**\n" + _format_context(pinecone_context))
        
        if code_analyst_context:
            context_parts.append("📝 **Code Analysis:**\n" + _format_code_analysis(code_analyst_context))
        
        if memory_context:
            context_parts.append("💾 **Related Previous Conversations:**\n" + _format_memory(memory_context))
        
        full_context = "\n\n".join(context_parts)
        
        if full_context.strip():
            logger.info(f"🧠 Synthesizing response with LLM... {scenario_info}")
            response_text = await _generate_llm_response(
                query=original_query,
                context=full_context,
                openai_api_key=openai_api_key,
                scenario=parallel_scenario
            )
        else:
            logger.warning(f"⚠️  No context available - using fallback response {scenario_info}")
            response_text = (
                f"I couldn't find specific information about '{original_query}' in the codebase. "
                f"Try asking about:\n"
                f"- Specific class or function names\n"
                f"- What a particular module does\n"
                f"- Dependencies and relationships between components\n"
                f"- Code implementation details"
            )
        
        logger.info(f"✅ Response synthesized - Length: {len(response_text)} chars")
        
        logger.info(f"✅ SYNTHESIS COMPLETE")
        logger.info(f"   Agents: {list(agents_used)}")
        logger.info(f"   Sources: {len(retrieved_sources)} total")
        logger.info(f"   Scenario: {parallel_scenario or 'standard'}")
        
        # ✅ DEBUG: Log all retrieved sources
        if retrieved_sources:
            logger.info(f"   📚 Retrieved sources breakdown:")
            pinecone_count = len([s for s in retrieved_sources if s.get("source_type") == "pinecone"])
            neo4j_count = len([s for s in retrieved_sources if s.get("source_type") == "neo4j"])
            logger.info(f"      - Pinecone: {pinecone_count} chunks")
            logger.info(f"      - Neo4j: {neo4j_count} entities")
        else:
            logger.warning(f"   ⚠️  No sources extracted despite successful searches")
        
        return ToolResult(
            success=True,
            data={
                "response": response_text,
                "agents_used": list(agents_used),
                "retrieved_sources": retrieved_sources,  # ✅ ALWAYS return sources
                "sources_count": len(retrieved_sources),
                "scenario": parallel_scenario,
                "reranked_results": any(s.get("reranked") for s in retrieved_sources if s.get("source_type") == "pinecone")
            }
        )

    except Exception as e:
        logger.error(f"❌ Synthesis failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))


def _format_context(context: List[Any]) -> str:
    """Format context data into readable text for LLM."""
    lines = []
    for item in context:
        if isinstance(item, dict):
            # Check if this is a Neo4j entity (has 'name', 'type', 'properties')
            if "name" in item and "type" in item:
                entity_name = item.get("name", "Unknown")
                entity_type = item.get("type", "Unknown")
                properties = item.get("properties", {})
                module = properties.get("module", "N/A")
                line_num = properties.get("line_number", "N/A")
                
                lines.append(f"**Entity: {entity_name} ({entity_type})**")
                lines.append(f"- Module: {module}")
                lines.append(f"- Line Number: {line_num}")
                
                # Add any other properties
                for prop_key, prop_value in properties.items():
                    if prop_key not in ["name", "module", "line_number"]:
                        lines.append(f"- {prop_key}: {str(prop_value)[:150]}")
            else:
                # Fallback for other dict formats
                for key, value in item.items():
                    if value and key not in ["error"]:
                        if isinstance(value, list) and len(value) > 0:
                            lines.append(f"- {key}: {', '.join(map(str, value[:5]))}")
                        elif isinstance(value, dict):
                            lines.append(f"- {key}: {len(value)} items")
                        else:
                            lines.append(f"- {key}: {str(value)[:200]}")
    return "\n".join(lines) if lines else "No data available"


def _format_code_analysis(analysis: List[Dict]) -> str:
    """Format code analyst results."""
    lines = []
    for item in analysis:
        tool = item.get("tool", "unknown")
        data = item.get("data", {})
        lines.append(f"**Tool:** {tool}")
        if isinstance(data, dict):
            for key, value in data.items():
                if value and key not in ["error"]:
                    lines.append(f"- {key}: {str(value)[:300]}")
    return "\n".join(lines) if lines else "No analysis available"


def _format_memory(memory: List[Dict]) -> str:
    """Format memory context."""
    lines = []
    for turn in memory[:6]:  # Last 6 = 3 Q&A pairs
        role = turn.get("role", "unknown").upper()
        content = turn.get("content", "")[:150]
        lines.append(f"**{role}:** {content}...")
    return "\n".join(lines) if lines else "No memory available"

async def _generate_llm_response(
    query: str,
    context: str,
    openai_api_key: str = None,
    scenario: str = None
) -> str:
    """
    Use GPT-4 to synthesize a natural response from context.
    Falls back to formatted context if LLM fails.
    Always returns a response (never fails).
    """
    try:
        if not openai_api_key:
            logger.warning("⚠️  No OpenAI key - returning formatted context")
            return context
        
        from openai import OpenAI
        client = OpenAI(api_key=openai_api_key)
        
        # Adjust system prompt based on scenario
        if scenario == "memory_fallback":

            system_msg = (
                f"You are a software engineering tutor explaining FastAPI codebase.\n"
                f"Context Source: {context}\n\n"
                f"IMPORTANT: Explain code clearly for students learning FastAPI architecture.\n\n"
                f"You have access to:\n"
                f"1. CODE CHUNKS: Actual code from files (what happens)\n"
                f"2. CODE RELATIONSHIPS: Dependencies, imports, inheritance (how things connect)\n\n"
                f"Response Guidelines:\n"
                f"- Start with WHAT (what does this code do)\n"
                f"- Then explain WHERE (where is it used, what calls it)\n"
                f"- Finally show HOW (design pattern, best practices)\n"
                f"- Reference file paths and line numbers\n"
                f"- Use analogies for complex concepts\n"
                f"- Keep explanations accessible to students\n\n"
                f"Only use the provided context. Do NOT add external knowledge."
            )

        else:
            system_msg = """You are a helpful codebase assistant.
Synthesize the provided context into a natural, coherent answer.
- Be concise but informative
- Use the context to answer accurately
- If context is insufficient, acknowledge it
- Use markdown formatting for readability
- Include code examples when relevant"""
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": system_msg
                },
                {
                    "role": "user",
                    "content": f"""Query: {query}

Previous Conversation (if any):
{scenario if scenario == 'memory_fallback' else 'No previous context'}

Available Context:
{context}

Please provide a natural, well-formatted answer based on this context. If there's a previous conversation, maintain continuity with it."""
                }
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        response_text = response.choices[0].message.content
        logger.info("✅ LLM synthesis successful")
        return response_text
        
    except Exception as e:
        logger.warning(f"⚠️  LLM synthesis failed: {e} - returning formatted context")
        # ALWAYS return context as fallback - never fail
        return f"Based on available information:\n\n{context}"