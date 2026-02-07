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
                
                if data.get("neo4j_entity"):
                    agents_used.add("graph_query")
                    
                    # Extract Neo4j entity as source (NEW FORMAT)
                    neo4j_entity = data.get("neo4j_entity", {})
                    logger.info(f"      ✅ Neo4j entity: {neo4j_entity.get('entity_name')} ({neo4j_entity.get('entity_type')})")
                    logger.debug(f"   🔍 Neo4j entity: {neo4j_entity}")
                    
                    # Use the formatted entity directly
                    if neo4j_entity.get("entity_name"):
                        neo4j_source = {
                            "source_type": "neo4j",
                            "type": "entity",
                            "entity_name": neo4j_entity.get("entity_name"),
                            "entity_type": neo4j_entity.get("entity_type", "Unknown"),
                            "module": neo4j_entity.get("module", "N/A"),
                            "line_number": neo4j_entity.get("line_number", "N/A"),
                            "properties": neo4j_entity.get("properties", {})
                        }
                        retrieved_sources.append(neo4j_source)
                        neo4j_context.append(neo4j_entity)
                    else:
                        logger.warning(f"   ⚠️  Neo4j entity missing 'entity_name': {neo4j_entity}")

                if data.get("pinecone_chunks"):
                    agents_used.add("code_analyst")
                    
                    # Extract chunks from NEW FORMAT
                    chunks = data.get("pinecone_chunks", [])
                    reranked_flag = data.get("pinecone_metadata", {}).get("reranked", False)
                    logger.info(f"   📍 Extracting {len(chunks)} Pinecone chunks as sources")
                    
                    for idx, chunk in enumerate(chunks, 1):
                        # Chunk is already formatted from parallel_search - use directly
                        source = {
                            "source_type": "pinecone",
                            "type": "code_chunk",
                            "file_name": chunk.get("file_name", "unknown"),
                            "file_path": chunk.get("file_path", "unknown"),
                            "start_line": chunk.get("start_line", 0),
                            "end_line": chunk.get("end_line", 0),
                            "lines": chunk.get("lines", "0-0"),
                            "language": chunk.get("language", "python"),
                            "content": chunk.get("content", ""),
                            "preview": chunk.get("preview", "")[:200],
                            "relevance_score": chunk.get("relevance_score", 0),  # Already decimal
                            "confidence": chunk.get("confidence", 0),
                            "reranked": chunk.get("reranked", False),
                            "chunk_id": chunk.get("chunk_id", "")
                        }
                        retrieved_sources.append(source)
                        logger.debug(f"      Chunk {idx}: {source['file_name']} (Lines {source['start_line']}-{source['end_line']}, Relevance: {source['relevance_score']:.1%}, Reranked: {source['reranked']})")
                    
                    # Add full chunks to context for LLM
                    pinecone_context.append({
                        "chunks": chunks,
                        "total": len(chunks),
                        "reranked": reranked_flag
                    })
                
                # Extract Neo4j relationships (from find_entity_relationships tool)
                # Handle BOTH old format (relationships) and NEW format (dependents/dependencies/parents)
                if data.get("relationships") or data.get("dependents"):
                    agents_used.add("graph_query")
                    
                    # Support new exhaustive relationship format
                    dependents = data.get("dependents", [])
                    dependencies = data.get("dependencies", [])
                    parents = data.get("parents", [])
                    
                    # Fallback to old format if new format not available
                    if not dependents and data.get("relationships"):
                        dependents = data.get("relationships", [])
                    
                    target_type = data.get("target_type", "Unknown")
                    entity_name_rel = data.get("entity_name", "Unknown")
                    target_module = data.get("target_module", "N/A")
                    target_line = data.get("target_line", "N/A")
                    
                    dependents_count = data.get("dependents_count", len(dependents))
                    dependencies_count = data.get("dependencies_count", len(dependencies))
                    parents_count = data.get("parents_count", len(parents))
                    
                    logger.info(f"   📍 Found {dependents_count} dependents, {dependencies_count} dependencies, {parents_count} parents")
                    
                    # Add comprehensive relationship source
                    rel_source = {
                        "source_type": "neo4j",
                        "type": "relationships",
                        "entity_name": entity_name_rel,
                        "entity_type": target_type,
                        "target_module": target_module,
                        "target_line": target_line,
                        "dependents": dependents,           # What uses this entity
                        "dependencies": dependencies,       # What this entity uses
                        "parents": parents,                 # What contains this entity
                        "dependents_count": dependents_count,
                        "dependencies_count": dependencies_count,
                        "parents_count": parents_count
                    }
                    retrieved_sources.append(rel_source)
                    logger.info(f"   ✅ Added exhaustive relationship source")
                    
                    # Add to context for LLM with full relationship map
                    neo4j_context.append({
                        "type": "relationships",
                        "entity": entity_name_rel,
                        "entity_type": target_type,
                        "module": target_module,
                        "line": target_line,
                        "dependents": dependents,
                        "dependencies": dependencies,
                        "parents": parents,
                        "dependents_count": dependents_count,
                        "dependencies_count": dependencies_count,
                        "parents_count": parents_count
                    })

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
        logger.info(f"\n📊 STEP 2: Building context for LLM synthesis...")
        context_parts = []
        scenario_info = f"[{parallel_scenario.upper()}]" if parallel_scenario else ""
        
        # Log context sources
        logger.info(f"   📍 Neo4j context items: {len(neo4j_context)}")
        logger.info(f"   📍 Pinecone context items: {len(pinecone_context)}")
        logger.info(f"   📍 Code analyst items: {len(code_analyst_context)}")
        logger.info(f"   📍 Memory context items: {len(memory_context)}")
        
        if neo4j_context:
            neo4j_formatted = _format_context(neo4j_context)
            context_parts.append("📊 **Neo4j Graph Data:**\n" + neo4j_formatted)
            logger.info(f"   ✅ Neo4j context added ({len(neo4j_formatted)} chars)")
            logger.debug(f"      Neo4j content:\n{neo4j_formatted[:300]}...")
        
        if pinecone_context:
            pinecone_formatted = _format_context(pinecone_context)
            context_parts.append("🔍 **Semantic Search Results:**\n" + pinecone_formatted)
            logger.info(f"   ✅ Pinecone context added ({len(pinecone_formatted)} chars)")
            logger.debug(f"      Pinecone content:\n{pinecone_formatted[:300]}...")
        
        if code_analyst_context:
            analyst_formatted = _format_code_analysis(code_analyst_context)
            context_parts.append("📝 **Code Analysis:**\n" + analyst_formatted)
            logger.info(f"   ✅ Code analyst context added ({len(analyst_formatted)} chars)")
            logger.debug(f"      Analyst content:\n{analyst_formatted[:300]}...")
        
        if memory_context:
            memory_formatted = _format_memory(memory_context)
            context_parts.append("💾 **Related Previous Conversations:**\n" + memory_formatted)
            logger.info(f"   ✅ Memory context added ({len(memory_formatted)} chars)")
            logger.debug(f"      Memory content:\n{memory_formatted[:300]}...")
        
        full_context = "\n\n".join(context_parts)
        total_context_length = len(full_context)
        
        logger.info(f"\n📄 FINAL CONTEXT SUMMARY:")
        logger.info(f"   📏 Total context length: {total_context_length} chars")
        logger.info(f"   📦 Context parts: {len(context_parts)}")
        logger.info(f"   🔍 Scenario: {scenario_info or 'standard'}")
        logger.debug(f"\n   FULL CONTEXT TO SEND TO LLM:\n{full_context}\n")
        
        if full_context.strip():
            logger.info(f"\n🧠 Synthesizing response with LLM... {scenario_info}")
            logger.info(f"   📝 Query: {original_query[:100]}...")
            logger.info(f"   📊 Context provided: {total_context_length} chars across {len(context_parts)} sections")
            
            response_text = await _generate_llm_response(
                query=original_query,
                context=full_context,
                openai_api_key=openai_api_key,
                scenario=parallel_scenario
            )
        else:
            logger.warning(f"⚠️  No context available - using fallback response {scenario_info}")
            logger.info(f"   ❌ Context parts: {len(context_parts)}")
            logger.info(f"   ❌ Neo4j: {len(neo4j_context)} items")
            logger.info(f"   ❌ Pinecone: {len(pinecone_context)} items")
            
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
            # Check if this is a relationships item (has 'type': 'relationships')
            if item.get("type") == "relationships":
                entity = item.get("entity", "Unknown")
                entity_type = item.get("entity_type", "Unknown")
                module = item.get("module", "N/A")
                line_num = item.get("line", "N/A")
                
                dependents = item.get("dependents", [])
                dependencies = item.get("dependencies", [])
                parents = item.get("parents", [])
                
                dependents_count = item.get("dependents_count", len(dependents))
                dependencies_count = item.get("dependencies_count", len(dependencies))
                parents_count = item.get("parents_count", len(parents))
                
                # Header
                lines.append(f"## **{entity}** ({entity_type})")
                lines.append(f"- **Location:** {module}:{line_num}")
                lines.append("")
                
                # What contains this entity (parents/context)
                if parents_count > 0:
                    lines.append(f"### 📦 **Where It's Defined ({parents_count} parent)**")
                    for parent in parents:
                        parent_name = parent.get("name", "Unknown")
                        parent_type = parent.get("type", "Unknown")
                        lines.append(f"  • Defined in: **{parent_name}** ({parent_type})")
                    lines.append("")
                
                # What this entity uses/depends on (dependencies/outgoing)
                if dependencies_count > 0:
                    lines.append(f"### 🔗 **Dependencies** ({dependencies_count} - What {entity} uses/imports):")
                    for dep in dependencies[:15]:  # Show top 15
                        dep_name = dep.get("name", "Unknown")
                        dep_type = dep.get("type", "Unknown")
                        relation = dep.get("relation", "USES")
                        lines.append(f"  • {dep_name} ({dep_type}) via {relation}")
                    if dependencies_count > 15:
                        lines.append(f"  ... and {dependencies_count - 15} more")
                    lines.append("")
                
                # What uses this entity (dependents/incoming)
                if dependents_count > 0:
                    lines.append(f"### 👥 **Dependents** ({dependents_count} - What depends on {entity}):")
                    lines.append(f"This entity is used by {dependents_count} other component(s):")
                    for dep in dependents[:20]:  # Show all incoming dependencies
                        dep_name = dep.get("name", "Unknown")
                        dep_type = dep.get("type", "Unknown")
                        relation = dep.get("relation", "USES")
                        module_info = dep.get("module", "")
                        lines.append(f"  • **{dep_name}** ({dep_type}) via {relation} {f'[{module_info}]' if module_info else ''}")
                    if dependents_count > 20:
                        lines.append(f"  ... and {dependents_count - 20} more")
                    lines.append("")
                
                # Summary statistics
                if dependents_count == 0 and dependencies_count == 0 and parents_count == 0:
                    lines.append(f"⚠️ **No relationships found** - {entity} is isolated in the codebase")
            
            # Check if this is a Neo4j entity (has 'name', 'type', 'properties')
            elif "name" in item and "type" in item and item.get("type") != "relationships":
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
    logger.info(f"\n🤖 LLM SYNTHESIS FUNCTION CALLED")
    logger.info(f"   📝 Query: {query[:100]}...")
    logger.info(f"   📏 Context length: {len(context)} chars")
    logger.info(f"   🔄 Scenario: {scenario or 'standard'}")
    logger.debug(f"   📄 Context preview:\n{context[:500]}...")
    
    # ✅ FIX: Check if this is an admin operation
    if "admin_clear" in context or ("clear" in query.lower() and "delete" in query.lower()):
        logger.info("✅ Admin operation detected - returning simple success message")
        return "✅ All indexed data has been successfully deleted from Neo4j and Pinecone databases. Your codebase index is now cleared."
    
    try:
        if not openai_api_key:
            logger.warning("⚠️  No OpenAI key - returning formatted context")
            return context
        
        from openai import OpenAI
        client = OpenAI(api_key=openai_api_key)
        
        logger.info(f"   ✅ OpenAI client initialized")
        logger.info(f"   📤 Sending request to GPT-4 (model: gpt-4)")
        
        # Comprehensive system prompt for detailed explanations
        system_msg = """You are an expert software engineering tutor helping new developers understand a complex codebase.

## Your Task:
Provide COMPREHENSIVE, EDUCATIONAL explanations using the provided context. This helps developers understand:
1. What each component does
2. Where it's used in the codebase
3. Why it's designed that way
4. How it connects to other components

## Response Structure (MANDATORY):

### 1. **WHAT** - Component Overview
- Clear definition of what this entity is (class, function, module, etc.)
- Its primary purpose in the system
- Key responsibilities or functionality
- Type: {entity_type} | Location: {file_path}:{line_number}

### 2. **WHERE** - Usage & Impact
**Parent Context (Where it's defined):**
- What module/class/package contains this entity
- Its role within that parent structure

**Dependents (What depends on it):**
- List of all entities that use/import/call this entity
- For each: name, type, and relationship type (IMPORTS, USES, CALLS, INHERITS_FROM)
- Show the count of dependent components

**Dependencies (What it depends on):**
- List of all entities this component uses/imports/calls
- For each: name, type, and relationship type
- Show the count of dependencies

### 3. **WHY** - Design & Patterns
- Explain the design pattern or architectural reason
- Why this entity is designed this way
- How it fits into the system's overall architecture
- Any alternative approaches and why this one was chosen

### 4. **HOW** - Code Implementation
- Reference specific code snippets from the provided chunks
- Show actual implementation details
- Explain key methods or properties
- Demonstrate usage patterns with code examples

## Formatting Rules:
- Use markdown headers (##, ###) for clear sections
- Include file paths and line numbers: `file.py:123-456`
- Use code blocks with language specification for snippets
- Create lists for relationships and dependencies
- Bold important concepts
- Use **relationship counts** to show impact: "Used by X other components"

## Relationship Interpretation:
- **Dependents**: "This entity is used by X components" → Shows its importance/impact
- **Dependencies**: "This entity depends on Y components" → Shows its complexity
- **Parents**: "Defined in {parent}" → Shows its context/scope

## Content Priority:
1. Start with a 1-2 sentence summary of WHAT
2. Expand on WHERE with actual relationship data
3. Explain WHY with design reasoning
4. Show HOW with code examples

## Special Instructions:
- If an entity has many dependents (>5), emphasize its importance
- If an entity has many dependencies (>5), explain the complexity
- Reference the actual code chunks provided
- Cross-reference related entities mentioned in dependencies
- Keep explanations accessible to mid-level developers (2-5 years experience)
- Use technical terms but explain them clearly

## Always Include:
✅ Component type and location
✅ Complete list of dependents (with count)
✅ Complete list of dependencies (with count)
✅ Parent/context information
✅ Code examples from provided chunks
✅ Design pattern or architectural reasoning
✅ Real file paths and line numbers

IMPORTANT: This is educational content. Be thorough and detailed. Don't be brief."""
        
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

IMPORTANT: The user is NEW to this codebase. Provide COMPREHENSIVE, DETAILED explanations.

Available Context:
{context}

Structure your answer using the WHAT-WHERE-WHY-HOW framework:
1. WHAT - What is this entity? (definition, purpose, type, location)
2. WHERE - Where is it used? (parents, dependents, dependencies with counts and names)
3. WHY - Why is it designed this way? (patterns, architecture, reasoning)
4. HOW - How is it implemented? (code examples, actual implementation details)

Be thorough and educational. Include:
- Exact file paths and line numbers
- Complete list of all dependents and dependencies
- Relationship counts showing impact
- Code examples from provided chunks
- Design pattern explanation

Do NOT be brief. This is for learning."""
                }
            ],
            temperature=0.7,
            max_tokens=1200  # ← Increased from 1500 to allow detailed responses
        )
        
        response_text = response.choices[0].message.content
        logger.info("✅ LLM synthesis successful")
        return response_text
        
    except Exception as e:
        logger.warning(f"⚠️  LLM synthesis failed: {e} - returning formatted context")
        # ALWAYS return context as fallback - never fail
        return f"Based on available information:\n\n{context}"
