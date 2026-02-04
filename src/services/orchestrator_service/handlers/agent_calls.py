"""Agent calls handler - calls remote agent services via HTTP."""

from typing import Any, Dict
import httpx

from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def call_agent_tool(
    agent: str,
    tool: str,
    input_params: Dict[str, Any],
    http_client: httpx.AsyncClient,
    agent_urls: Dict[str, str]
) -> ToolResult:
    """
    Call a specific tool on a remote agent service.
    
    Args:
        agent: Agent name (graph_query, code_analyst, indexer, memory)
        tool: Tool name to execute
        input_params: Tool input parameters
        http_client: Async HTTP client
        agent_urls: Map of agent names to URLs
        
    Returns:
        ToolResult with agent response
    """
    try:
        logger.debug(f"🔗 Calling agent: {agent} | Tool: {tool}")
        
        # Get agent URL
        url = agent_urls.get(agent)
        if not url:
            logger.error(f"❌ Unknown agent: {agent}")
            return ToolResult(success=False, error=f"Unknown agent: {agent}")
        
        # Build request
        execute_url = f"{url}/execute"
        logger.debug(f"   URL: {execute_url}")
        logger.debug(f"   Input: {input_params}")

        # Make HTTP request
        response = await http_client.post(
            execute_url,
            params={"tool_name": tool},  # Query parameter
            json=input_params,            # Body
            timeout=30.0
        )
        
        logger.debug(f"   Status: {response.status_code}")
        
        # Check response status
        if response.status_code != 200:
            error_msg = response.text
            logger.error(f"❌ Agent call failed: {error_msg}")
            return ToolResult(
                success=False,
                error=f"Agent call failed: {error_msg}"
            )
        
        # Parse result
        result = response.json()
        
        if result.get("success"):
            logger.debug(f"   ✓ Agent succeeded")
        else:
            logger.warning(f"   ⚠️  Agent returned error: {result.get('error')}")
        
        return ToolResult(
            success=result.get("success", False),
            data=result.get("data"),
            error=result.get("error")
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to call agent tool: {e}")
        return ToolResult(success=False, error=str(e))
