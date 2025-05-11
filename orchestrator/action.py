from typing import Any, Dict, Union
from .config import tool_to_endpoint_map, logger

try:
    from fastmcp import Client as FastMCPClient
    from fastmcp.exceptions import ClientError, ToolError
except ImportError:
    FastMCPClient = None
    ClientError = Exception
    ToolError = Exception
import asyncio

async def call_mcp_tool(tool_name: str, tool_input: Dict[str, Any]) -> Any:
    mcp_endpoint = tool_to_endpoint_map.get(tool_name)
    if not mcp_endpoint:
        logger.error(f"Endpoint not found for tool '{tool_name}' in tool_to_endpoint_map.")
        return {"error": f"Configuration error: Endpoint not found for tool '{tool_name}'."}
    logger.info(f"Attempting to call MCP tool '{tool_name}' on server {mcp_endpoint}")
    logger.debug(f"Tool Input: {tool_input}")
    client = FastMCPClient(mcp_endpoint)
    try:
        async with client:
            logger.info(f"Executing client.call_tool(name='{tool_name}', arguments=...) on {mcp_endpoint}")
            result = await asyncio.wait_for(
                client.call_tool(name=tool_name, arguments=tool_input),
                timeout=60.0
            )
            logger.info(f"MCP tool '{tool_name}' executed successfully on {mcp_endpoint}.")
            logger.debug(f"Raw tool result (content list from FastMCP client): {result}")
            return result
    except ClientError as e:
        logger.error(f"MCP ClientError calling tool '{tool_name}' on {mcp_endpoint}: {e}")
        return {"error": f"MCP Client Error: {e}"}
    except ToolError as e:
        logger.error(f"MCP ToolError calling tool '{tool_name}' on {mcp_endpoint}: {e}")
        return {"error": f"MCP Tool Error: {e}"}
    except asyncio.TimeoutError:
        logger.error(f"Timed out calling MCP tool '{tool_name}' on {mcp_endpoint}.")
        return {"error": f"Timeout calling MCP tool '{tool_name}'."}
    except Exception as e:
        logger.error(f"Unexpected error calling MCP tool '{tool_name}' on {mcp_endpoint}: {e}", exc_info=True)
        return {"error": f"Unexpected error calling tool: {e}"}

async def send_telegram_message(chat_id: Union[str, int], text: str):
    logger.info(f"Attempting to send Telegram message to {chat_id}: '{text[:50]}...'")
    telegram_tool_name = "telegram_send_message"
    if telegram_tool_name in tool_to_endpoint_map:
        tool_input = {"chat_id": int(chat_id), "text": text}
        logger.info(f"Using '{telegram_tool_name}' tool to send message.")
        result = await call_mcp_tool(telegram_tool_name, tool_input)
        if isinstance(result, dict) and result.get("error"):
            logger.error(f"Failed to send message via Telegram tool: {result['error']}")
        else:
            logger.info(f"Message sent via Telegram tool. Result: {result}")
    else:
        logger.warning(f"'{telegram_tool_name}' tool not found. Implement direct sending or configure Telegram MCP.")
