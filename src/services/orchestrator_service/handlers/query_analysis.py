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
                    "content": """Analyze the user query for a codebase analysis system.
Return JSON:
{
    "intent": "search|explain|analyze|index|embed|implement|stats",
    "entities": ["entity1", "entity2"],
    "repo_url": "url if indexing" or null,
    "confidence": 0.0-1.0
}"""
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
        
        return ToolResult(
            success=True,
            data={
                "query": query,
                "intent": analysis.get("intent", "search"),
                "entities": analysis.get("entities", []),
                "repo_url": analysis.get("repo_url"),
                "confidence": analysis.get("confidence", 0.5)
            }
        )
    except Exception as e:
        logger.error(f"Failed to analyze query with LLM: {e}")
        return ToolResult(success=False, error=str(e))
