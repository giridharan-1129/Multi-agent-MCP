"""
Agentic Chat Endpoint - TRUE Agentic AI with Claude/OpenAI Reasoning.

WHAT: Multi-agent orchestration with LLM reasoning
WHY: Enable autonomous agent decision-making and tool chaining
HOW: Claude/OpenAI reasons about what tools to call, then chains them automatically

Example Flow:
    User: "How does FastAPI handle dependency injection?"
    
    Claude reasons:
      "I need to understand this better. Let me:"
      1. Find the Depends class
      2. Analyze it
      3. Get examples of its usage
      4. Explain how it works
      
    Claude autonomously calls tools in sequence based on results
    Returns comprehensive answer with reasoning shown
"""

import json
import os
import requests
from typing import Optional, AsyncGenerator, Dict, Any
from fastapi import APIRouter, HTTPException
from openai import OpenAI, AsyncOpenAI

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ...shared.config import config
from ..dependencies import (
    get_orchestrator,
    get_graph_query,
    get_code_analyst,
)

logger = get_logger(__name__)
router = APIRouter(tags=["agentic"], prefix="/api")


def build_tools_schema():
    """
    Build OpenAI function schema for all available agent tools.
    This tells Claude what tools it can use.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "find_entity",
                "description": "Find a class, function, or module by name in the codebase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Entity name to search for (e.g., 'FastAPI', 'Depends')"
                        },
                        "entity_type": {
                            "type": "string",
                            "enum": ["Class", "Function", "Module"],
                            "description": "Optional filter by entity type"
                        }
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dependencies",
                "description": "Find what an entity depends on (imports, calls, inherits from)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Entity name to analyze"
                        }
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_dependents",
                "description": "Find what depends on an entity (who uses it)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Entity name to analyze"
                        }
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_function",
                "description": "Deep analysis of a function including calls, callers, complexity",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Function name to analyze"
                        }
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_class",
                "description": "Deep analysis of a class including methods, inheritance, docstring",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Class name to analyze"
                        }
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "find_patterns",
                "description": "Detect design patterns in the codebase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern_type": {
                            "type": "string",
                            "description": "Optional pattern type filter"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "compare_implementations",
                "description": "Compare two code entities side-by-side",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity1": {
                            "type": "string",
                            "description": "First entity name"
                        },
                        "entity2": {
                            "type": "string",
                            "description": "Second entity name"
                        }
                    },
                    "required": ["entity1", "entity2"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_semantics",
                "description": "Semantic search in codebase using embeddings (Pinecone). Useful for finding code related to concepts or features",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query about code (e.g., 'how to handle authentication', 'error handling patterns')"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return (default: 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]
    return tools


async def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool by name with the given input.
    Routes to appropriate agent.
    """
    try:
        if tool_name == "find_entity":
            graph_query = get_graph_query()
            result = await graph_query.execute_tool(
                "find_entity",
                {
                    "name": tool_input.get("name"),
                    "entity_type": tool_input.get("entity_type")
                }
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif tool_name == "get_dependencies":
            graph_query = get_graph_query()
            result = await graph_query.execute_tool(
                "get_dependencies",
                {"name": tool_input.get("name")}
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif tool_name == "get_dependents":
            graph_query = get_graph_query()
            result = await graph_query.execute_tool(
                "get_dependents",
                {"name": tool_input.get("name")}
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif tool_name == "analyze_function":
            code_analyst = get_code_analyst()
            result = await code_analyst.execute_tool(
                "analyze_function",
                {"name": tool_input.get("name")}
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif tool_name == "analyze_class":
            code_analyst = get_code_analyst()
            result = await code_analyst.execute_tool(
                "analyze_class",
                {"name": tool_input.get("name")}
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif tool_name == "find_patterns":
            code_analyst = get_code_analyst()
            result = await code_analyst.execute_tool(
                "find_patterns",
                {"pattern_type": tool_input.get("pattern_type")}
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif tool_name == "compare_implementations":
            code_analyst = get_code_analyst()
            result = await code_analyst.execute_tool(
                "compare_implementations",
                {
                    "entity1": tool_input.get("entity1"),
                    "entity2": tool_input.get("entity2")
                }
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif tool_name == "search_semantics":
            # Search Pinecone for semantic matches
            try:
                query = tool_input.get("query", "")
                top_k = tool_input.get("top_k", 5)
                repo_id = tool_input.get("repo_id", "fastapi")  # Default to fastapi
                
                # Call the embeddings search endpoint
                search_response = requests.post(
                    f"{config.api_base}/api/embeddings/search",
                    json={"query": query, "repo_id": repo_id, "top_k": top_k},
                    timeout=30
                )
                
                if search_response.ok:
                    search_data = search_response.json()
                    if search_data.get("success"):
                        results = search_data.get("results", [])
                        return {
                            "success": True,
                            "data": {
                                "query": query,
                                "results_count": len(results),
                                "results": results
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "error": search_data.get("error", "Semantic search failed")
                        }
                else:
                    return {
                        "success": False,
                        "error": f"Embeddings service error: {search_response.text[:100]}"
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Semantic search error: {str(e)}"
                }

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error(f"Tool execution failed: {str(e)}", tool=tool_name)
        return {"success": False, "error": str(e)}


@router.post("/agentic-chat")
async def agentic_chat(request: dict):
    """
    TRUE Agentic Chat - Claude/OpenAI reasons and chains tools automatically.
    
    Request:
        {
            "query": "How does FastAPI handle dependency injection?",
            "session_id": "optional-session-id"
        }
    
    Response:
        {
            "response": "Comprehensive answer...",
            "thinking_process": ["Step 1: Found Depends class...", "Step 2: Analyzed..."],
            "tools_used": ["find_entity", "analyze_class", "get_dependents"],
            "correlation_id": "..."
        }
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        query = request.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        session_id = request.get("session_id", correlation_id)

        logger.info("Agentic chat started", query=query[:100], session_id=session_id)

        # Initialize OpenAI client
        client = OpenAI(api_key=config.openai.api_key or os.getenv("OPENAI_API_KEY"))

        # System prompt for agentic reasoning
        # System prompt for agentic reasoning
        system_prompt = """You are an expert FastAPI code analyst assistant with access to a complete knowledge graph of the FastAPI codebase and semantic search.

Your role:
1. Understand complex user questions about the codebase
2. Autonomously decide which tools to use and in what order
3. Chain tools together based on intermediate results
4. Synthesize findings into comprehensive, well-structured answers
5. Show your reasoning process

Available tools:
- find_entity: Search for classes, functions, modules by name
- get_dependencies: Find what something depends on
- get_dependents: Find what uses something
- analyze_function: Deep function analysis
- analyze_class: Deep class analysis
- find_patterns: Detect design patterns
- compare_implementations: Compare two entities
- search_semantics: Semantic search using embeddings (for concepts/features like "authentication", "error handling")

Guidelines:
- Be thorough but concise
- Use search_semantics for conceptual/feature searches
- Use find_entity for direct lookups
- When you find something interesting, follow up with related queries
- Use multiple tools to build a complete picture
- Explain your reasoning at each step
- Quote specific code when relevant
"""

        # Build initial message
       # Build initial messages with system prompt
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        # Agentic loop
        tools_schema = build_tools_schema()
        thinking_steps = []
        tools_used = set()
        max_iterations = 10
        iteration = 0

        all_sources = []  # MOVE THIS HERE - outside the loop
        
        while iteration < max_iterations:
            iteration += 1

            # Call OpenAI with tools
            response = client.chat.completions.create(
                model=config.openai.model or "gpt-4o-mini",
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.7,
            )

            if response.choices[0].finish_reason == "stop":
                # Extract final response
                final_response = response.choices[0].message.content
                
                logger.info(
                    "Agentic chat completed",
                    iterations=iteration,
                    tools_used=len(tools_used)
                )

                return {
                    "response": final_response,
                    "thinking_process": thinking_steps,
                    "tools_used": list(tools_used),
                    "iterations": iteration,
                    "session_id": session_id,
                    "correlation_id": correlation_id,
                    "retrieved_context": all_sources,  # Changed key name to match Streamlit
                }

            # Process tool calls
            if response.choices[0].finish_reason == "tool_calls":
                tool_calls = response.choices[0].message.tool_calls

                if not tool_calls:
                    break

                # Add assistant's response to messages
                # Add assistant's response to messages with tool calls
                messages.append({
                    "role": "assistant",
                    "content": response.choices[0].message.content,
                    "tool_calls": response.choices[0].message.tool_calls
                })

                
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)

                    logger.debug(f"Executing tool: {tool_name}", input=tool_input)

                    # Record thinking step
                    thinking_steps.append(f"Using {tool_name} with input: {tool_input}")
                    tools_used.add(tool_name)

                    # Execute tool
                    tool_result = await execute_tool(tool_name, tool_input)

                    thinking_steps.append(f"Result: {json.dumps(tool_result)[:200]}...")

                    # Extract sources from semantic search results
                    if tool_name == "search_semantics" and tool_result.get("success"):
                        search_results = tool_result.get("data", {}).get("results", [])
                        for result in search_results:
                            all_sources.append({
                                "source_type": "pinecone",
                                "type": "code_chunk",
                                "file_name": result.get("file_name", "unknown"),
                                "content": result.get("content", ""),
                                "preview": result.get("preview", ""),
                                "lines": result.get("lines", "N/A"),
                                "relevance": result.get("relevance", 0),
                                "language": result.get("language", "python"),
                                "start_line": result.get("start_line", "N/A"),
                                "end_line": result.get("end_line", "N/A"),
                            })

                    # Add tool result as separate message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result)
                    })

            else:
                # No tool calls and not end_turn, exit loop
                break

        # Fallback response if max iterations reached
        # Fallback response if max iterations reached
        return {
            "response": "Analysis completed but required multiple iterations. Please check the thinking process for details.",
            "thinking_process": thinking_steps,
            "tools_used": list(tools_used),
            "iterations": iteration,
            "session_id": session_id,
            "correlation_id": correlation_id,
            "retrieved_context": all_sources,  # Changed key name to match Streamlit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Agentic chat failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))