from typing import Any, Dict, List, Optional
import asyncio
import json
import httpx
from .config import (
    DDG_SSE_ENDPOINT, TRAFILATURA_SSE_ENDPOINT, TELEGRAM_MCP_ENDPOINT, GDRIVE_SSE_ENDPOINT, SOURCE_SSE_ENDPOINT, logger, tool_to_endpoint_map
)

try:
    from fastmcp import Client as FastMCPClient
    from fastmcp.exceptions import ClientError, ToolError
    from mcp.types import Tool as MCPToolDefinition
    from mcp import types as mcp_types
    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False

available_mcp_tools: Optional[List[Dict[str, Any]]] = None

async def _discover_tools_from_endpoint(server_name: str, endpoint: str) -> List[Dict[str, Any]]:
    logger.info(f"Attempting tool discovery from {server_name} MCP server at: {endpoint}")
    if not FASTMCP_AVAILABLE:
        logger.error(f"MCP Tool Discovery Failed for {server_name}: FastMCP library not available.")
        return []
    client = FastMCPClient(endpoint)
    discovered_tools_with_endpoint = []
    try:
        async with client:
            tools: List[MCPToolDefinition] = await asyncio.wait_for(client.list_tools(), timeout=20.0)
        if tools:
            logger.info(f"Discovery from {server_name} Successful: Found {len(tools)} tool(s).")
            for tool_def in tools:
                tool_name = getattr(tool_def, 'name', 'N/A')
                tool_to_endpoint_map[tool_name] = endpoint
                logger.info(f"  -> {server_name} Tool: Name='{tool_name}', Desc='{getattr(tool_def, 'description', 'N/A')[:60]}...'")
                discovered_tools_with_endpoint.append({
                    "tool_definition": tool_def,
                    "endpoint": endpoint,
                    "server_name": server_name
                })
            return discovered_tools_with_endpoint
        else:
            logger.warning(f"Discovery from {server_name}: Server reported 0 tools.")
            return []
    except ClientError as e:
         logger.error(f"Discovery Failed for {server_name}: ClientError from {endpoint}: {e}")
    except asyncio.TimeoutError:
        logger.error(f"Discovery Failed for {server_name}: Timed out connecting to {endpoint}.")
    except Exception as e:
        logger.error(f"Discovery Failed for {server_name}: Unexpected error from {endpoint}: {e}", exc_info=True)
    return []

async def discover_mcp_tools() -> None:
    global available_mcp_tools, tool_to_endpoint_map
    logger.info("Initiating MCP Tool Discovery across all configured servers...")
    tool_to_endpoint_map.clear()
    all_discovered_tools = []
    servers_to_discover = [
        {"name": "DuckDuckGo", "endpoint": DDG_SSE_ENDPOINT},
        {"name": "Trafilatura", "endpoint": TRAFILATURA_SSE_ENDPOINT},
        {"name": "Telegram", "endpoint": TELEGRAM_MCP_ENDPOINT},
        {"name": "GDrive", "endpoint": GDRIVE_SSE_ENDPOINT}
    ]
    for server_config in servers_to_discover:
        if not server_config["endpoint"] or server_config["endpoint"] == "http://localhost:0/":
            logger.info(f"Skipping tool discovery for {server_config['name']} as endpoint is not configured meaningfully.")
            continue
        tools_from_server = await _discover_tools_from_endpoint(server_config["name"], server_config["endpoint"])
        all_discovered_tools.extend(tools_from_server)
    if all_discovered_tools:
        available_mcp_tools = all_discovered_tools
        logger.info(f"Total MCP Tools Discovered: {len(available_mcp_tools)} from active server(s).")
        logger.debug(f"Tool to endpoint map: {tool_to_endpoint_map}")
    else:
        logger.warning("MCP Tool Discovery: No tools found from any configured server.")
        available_mcp_tools = []

from .action import send_telegram_message
from .agent_loop import agentic_tool_loop

async def handle_notification(notification: dict[str, Any]):
    global available_mcp_tools
    logger.debug(f"Entering handle_notification for method: {notification.get('method')}")
    method = notification.get("method")
    params = notification.get("params", {})
    if method == "notifications/message":
        message_data = params.get("data", {})
        chat_id = message_data.get("chat_id")
        text = message_data.get("text")
        username = message_data.get('username', 'Unknown User')
        if chat_id and text:
            logger.info(f"Processing message from {username} (Chat ID: {chat_id}): '{text}'")
            if available_mcp_tools is None:
                logger.warning("MCP Tools list was None. Attempting discovery on-demand...")
                await discover_mcp_tools()
                if available_mcp_tools is None:
                    logger.error("CRITICAL: Failed to discover MCP tools on-demand. Cannot process message requiring tools.")
                    await send_telegram_message(chat_id, "[Agent Error: Tool system initialization failed.]")
                    return
            await agentic_tool_loop(text, available_mcp_tools or [], chat_id)
        else:
            logger.warning(f"Received incomplete message notification: {message_data}")
    elif method == "mcp/error":
        logger.error(f"Received MCP Error Notification from SOURCE SSE: Code={params.get('code')} Msg='{params.get('message')}' Data={params.get('data')}")
    else:
        logger.info(f"Received unknown notification type from SOURCE SSE: Method='{method}', Params={params}")
    logger.debug(f"Exiting handle_notification for method: {notification.get('method')}")

async def listen_to_source_sse():
    logger.info(f"Attempting to connect to SOURCE SSE endpoint: {SOURCE_SSE_ENDPOINT}")
    retry_delay = 5
    max_retry_delay = 60
    while True:
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", SOURCE_SSE_ENDPOINT, headers={"Accept": "text/event-stream"}, timeout=httpx.Timeout(30.0, connect=10.0)) as response:
                    if response.status_code == 200:
                        logger.info(f"--> Successfully connected to SOURCE SSE ({SOURCE_SSE_ENDPOINT}). Listening...")
                        retry_delay = 5
                        async for line in response.aiter_lines():
                            logger.debug(f"Raw line from source SSE: {line}")
                            if line.startswith("data:"):
                                data_str = line[len("data:"):].strip()
                                if data_str:
                                    if data_str.startswith("{") and data_str.endswith("}"):
                                        try:
                                            notification = json.loads(data_str)
                                            logger.debug(f"Received notification object: {notification}")
                                            asyncio.create_task(handle_notification(notification))
                                        except json.JSONDecodeError:
                                            logger.error(f"JSON Decode Error from source SSE: {data_str}")
                                        except Exception as e:
                                            logger.error(f"Error processing source notification: {e}\nRaw data: {data_str}", exc_info=True)
                                    else:
                                         logger.warning(f"Received non-JSON data line from source SSE (but not empty): {data_str}")
                                else:
                                     logger.debug("Received empty data line from source SSE (keepalive).")
                            elif line.strip() == ':':
                                logger.debug("Received SSE comment/keep-alive.")
                            elif line.strip():
                                logger.debug(f"Received other non-empty line from source SSE: {line}")
                        logger.warning("Source SSE stream closed by server.")
                    else:
                        logger.error(f"Connection failed to SOURCE SSE ({SOURCE_SSE_ENDPOINT})! Status: {response.status_code}")
                        try:
                            body = await asyncio.wait_for(response.aread(), timeout=5.0)
                            logger.error(f"Response body: {body.decode(errors='ignore')}")
                        except asyncio.TimeoutError: logger.error("Could not read response body (timeout).")
                        except Exception as read_err: logger.error(f"Could not read response body: {read_err}")
        except httpx.ConnectError as e:
            logger.error(f"Connection failed to SOURCE SSE ({SOURCE_SSE_ENDPOINT}). Is the source server running? Details: {e}")
        except httpx.ReadTimeout:
             logger.warning(f"Connection to SOURCE SSE ({SOURCE_SSE_ENDPOINT}) timed out during read. Reconnecting...")
        except httpx.StreamError as e:
            logger.error(f"Stream error with SOURCE SSE ({SOURCE_SSE_ENDPOINT}): {e}. Reconnecting...")
        except Exception as e:
            logger.error(f"Unexpected error in SOURCE SSE listener: {e}", exc_info=True)
        logger.info(f"Attempting to reconnect to SOURCE SSE in {retry_delay} seconds...")
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, max_retry_delay)
