"""Query analysis handler - uses GPT-4 to understand user intent."""

import json
from typing import Any, Dict
from openai import OpenAI

from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def analyze_query(
    query: str,
    openai_api_key: str
) -> ToolResult:
    """
    Use GPT-4 to analyze query intent intelligently.
    
    Returns:
        ToolResult with intent, entities, repo_url, confidence
    """
    try:
        client = OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
   {
        "role": "system",
        "content": """You are a code entity extractor for a Python codebase analysis system.

EXTRACTION RULES:
1. Extract ONLY real code entity names (classes, functions, modules)
2. IGNORE SQL keywords (MATCH, WHERE, SELECT, LIMIT, ORDER BY, etc.)
3. IGNORE natural language words that aren't code entities
4. Focus on: ClassName, function_name, module_name patterns
5. Return empty entities list if no real code entities found

INTENT TYPES:
- "search": Find code entity (e.g., "What is FastAPI?", "Find Depends")
- "explain": Explain entity behavior (e.g., "How does validation work?")
- "analyze": Deep code analysis (e.g., "Analyze FastAPI class structure")
- "index": Index repository to Neo4j (e.g., "Index https://github.com/...")
- "embed": Embed repository to Pinecone (e.g., "Embed https://github.com/...")
- "stats": Get codebase stats

Return ONLY valid JSON (no markdown, no extra text):
{
    "intent": "search|explain|analyze|index|embed|stats",
    "entities": ["RealClassName", "real_function_name"],
    "repo_url": "https://..." or null,
    "confidence": 0.0-1.0
}

CRITICAL: Extract entities STRICTLY from code context only.

Examples:
- "What is FastAPI?" → {"intent": "search", "entities": ["FastAPI"], "confidence": 0.95}
- "Explain Dependant class" → {"intent": "explain", "entities": ["Dependant"], "confidence": 0.9}
- "MATCH (e) WHERE..." → {"intent": "search", "entities": [], "confidence": 0.7}
- "Index https://github.com/tiangolo/fastapi" → {"intent": "index", "entities": [], "repo_url": "https://github.com/tiangolo/fastapi", "confidence": 0.95}
- "Embed https://github.com/tiangolo/fastapi" → {"intent": "embed", "entities": [], "repo_url": "https://github.com/tiangolo/fastapi", "confidence": 0.95}
"""
        },
                {"role": "user", "content": query}
            ],
            temperature=0.5,
            max_tokens=200
        )
        
        result_text = response.choices[0].message.content
        
        try:
            analysis = json.loads(result_text)
        except json.JSONDecodeError:
            analysis = {
                "intent": "search",
                "entities": [],
                "repo_url": None,
                "confidence": 0.5
            }
        
        logger.debug(f"🔍 Query analyzed: intent={analysis.get('intent')}")
        
        # Clean entity names (remove "class", "function", "method", etc.)
        entities = analysis.get("entities", [])
        cleaned_entities = []
        logger.info(f"🔍 RAW ANALYSIS: {analysis}")
        logger.info(f"🔍 Raw entities extracted: {analysis.get('entities', [])}")
        
        logger.debug(f"🔍 Query analyzed: intent={analysis.get('intent')}")
        for entity in entities:
            # Remove trailing "class", "function", "method", etc.
            cleaned = entity.strip()
            for suffix in [" class", " function", " method", " module", " file", " package"]:
                if cleaned.lower().endswith(suffix):
                    cleaned = cleaned[:-len(suffix)].strip()
            cleaned_entities.append(cleaned)
        
        return ToolResult(
            success=True,
            data={
                "query": query,
                "intent": analysis.get("intent", "search"),
                "entities": cleaned_entities,
                "repo_url": analysis.get("repo_url"),
                "confidence": analysis.get("confidence", 0.5)
            }
        )
    except Exception as e:
        logger.error(f"Failed to analyze query with LLM: {e}")
        return ToolResult(success=False, error=str(e))
