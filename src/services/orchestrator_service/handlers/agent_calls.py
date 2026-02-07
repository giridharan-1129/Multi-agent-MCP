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
    """
    try:
        logger.info(f"🔗 [AGENT_CALL] Starting agent call")
        logger.info(f"   Agent: {agent}")
        logger.info(f"   Tool: {tool}")
        logger.info(f"   Params: {input_params}")
        
        # Get agent URL
        url = agent_urls.get(agent)
        if not url:
            logger.error(f"❌ [AGENT_CALL] Unknown agent: {agent}")
            logger.error(f"   Available agents: {list(agent_urls.keys())}")
            return ToolResult(success=False, error=f"Unknown agent: {agent}")
        
        logger.info(f"   ✓ Agent URL found: {url}")
        
        # Build request
        execute_url = f"{url}/execute"
        logger.info(f"   Execute URL: {execute_url}")
        logger.info(f"   Query param: tool_name={tool}")
        logger.debug(f"   Request body: {input_params}")

        # Make HTTP request
        logger.info(f"   ⏳ Sending HTTP POST request...")
        response = await http_client.post(
            execute_url,
            params={"tool_name": tool},  # Query parameter
            json=input_params,            # Body
            timeout=30.0
        )
        
        logger.info(f"   ✓ Response received")
        logger.info(f"   Status code: {response.status_code}")
        
        # Check response status
        if response.status_code != 200:
            error_msg = response.text[:500]  # Limit error message length
            logger.error(f"❌ [AGENT_CALL] HTTP Error {response.status_code}")
            logger.error(f"   Error message: {error_msg}")
            return ToolResult(
                success=False,
                error=f"HTTP {response.status_code}: {error_msg}"
            )
        
        # Parse result
        logger.info(f"   ⏳ Parsing JSON response...")
        result = response.json()
        
        success = result.get("success", False)
        error = result.get("error")
        data = result.get("data")
        
        logger.info(f"   Response success: {success}")
        
        if success:
            logger.info(f"   ✅ [AGENT_CALL] Agent call SUCCEEDED")
            if data:
                logger.info(f"   Data keys: {list(data.keys()) if isinstance(data, dict) else 'non-dict'}")
                if isinstance(data, dict):
                    for key in data.keys():
                        value = data[key]
                        if isinstance(value, list):
                            logger.debug(f"      {key}: {len(value)} items")
                        elif isinstance(value, dict):
                            logger.debug(f"      {key}: dict with {len(value)} keys")
                        else:
                            logger.debug(f"      {key}: {str(value)[:100]}")
        else:
            logger.warning(f"   ⚠️  [AGENT_CALL] Agent returned success=False")
            logger.warning(f"   Error: {error}")
        
        return ToolResult(
            success=success,
            data=data,
            error=error
        )
        
    except asyncio.TimeoutError:
        logger.error(f"❌ [AGENT_CALL] TIMEOUT - Agent took too long to respond")
        logger.error(f"   Agent: {agent}, Tool: {tool}")
        return ToolResult(success=False, error=f"Agent timeout: {agent}/{tool}")
    except Exception as e:
        logger.error(f"❌ [AGENT_CALL] EXCEPTION occurred")
        logger.error(f"   Agent: {agent}")
        logger.error(f"   Tool: {tool}")
        logger.error(f"   Error: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return ToolResult(success=False, error=str(e))