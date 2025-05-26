# telegram_agent/session.py

import os
import sys
from typing import Optional, Any, List, Dict
from mcp import ClientSession
from mcp.client.sse import sse_client


class MultiMCP:
    """
    Stateless version: discovers tools from multiple MCP servers, but reconnects per tool call.
    Each call_tool() uses a fresh session based on tool-to-server mapping.
    """
    def __init__(self, server_configs: List[dict] = None):
        self.server_configs = server_configs or self._default_server_configs()
        self.tool_map: Dict[str, Dict[str, Any]] = {}  # tool_name → {config, tool}

    def _default_server_configs(self):
        # Explicit config for each MCP server
        # Adjust script names and working directories as needed for your project structure
        return [
            {"name": "serpapi", "script": "serpapi_mcp_server.py", "cwd": os.getcwd(), "url": "http://localhost:8050/serpapi_mcp_sse/"},
            {"name": "trafilatura", "script": "trafilatura_mcp_server.py", "cwd": os.getcwd(), "url": "http://localhost:8030/trafilatura_mcp_sse/"},
            {"name": "telegram", "script": "telegram_mcp_server.py", "cwd": os.getcwd(), "url": "http://localhost:8000/telegram_mcp_sse/"},
            {"name": "gdrive", "script": "gdrive_mcp_server.py", "cwd": os.getcwd(), "url": "http://localhost:8020/gdrive_mcp_sse/"},
        ]

    async def initialize(self):
        print("in MultiMCP initialize")
        for config in self.server_configs:
            try:
                server_name = config["name"]
                server_url = config["url"]
                print(f"→ Connecting to SSE server: {server_name} at {server_url}")
                try:
                    async with sse_client(server_url, timeout=5) as (read, write):
                        print("[DEBUG] SSE connection established")
                        async with ClientSession(read, write) as session:
                            print("[DEBUG] ClientSession created")
                            await session.initialize()
                            print(f"[agent] MCP session initialized for {server_name}")
                            tools = await session.list_tools()
                            print(f"[DEBUG] Tools listed for {server_name}")
                            print(f"→ Tools received from {server_name}: {[tool.name for tool in tools.tools]}")
                            for tool in tools.tools:
                                self.tool_map[tool.name] = {
                                    "config": config,
                                    "tool": tool
                                }
                except Exception as se:
                    print(f"❌ Session error for {server_name}: {se}")
            except Exception as e:
                print(f"❌ Error initializing MCP server {config['name']}: {e}")

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        entry = self.tool_map.get(tool_name)
        if not entry:
            raise ValueError(f"Tool '{tool_name}' not found on any server.")
            
        config = entry["config"]
        server_name = config["name"]
        
        # Get existing session or create new one if needed
        config = entry["config"]
        server_name = config["name"]
        print(f"[DEBUG] Preparing to call tool '{tool_name}' on {server_name}")
        async with sse_client(config["url"], timeout=5) as (read, write):
            print(f"[DEBUG] SSE connection established for call_tool: {server_name}")
            async with ClientSession(read, write) as session:
                print(f"[DEBUG] ClientSession created for call_tool: {server_name}")
                await session.initialize()
                print(f"[DEBUG] Session initialized for call_tool: {server_name}")
                result = await session.call_tool(tool_name, arguments)
                print(f"[DEBUG] Tool call complete for '{tool_name}' on {server_name}")
                return result


    async def list_all_tools(self) -> List[str]:
        return list(self.tool_map.keys())

    def get_all_tools(self) -> List[Any]:
        return [entry["tool"] for entry in self.tool_map.values()]
        
    def get_task_patterns(self) -> Dict[str, Any]:
        """Return an empty dictionary for task patterns.
        This method is needed for compatibility with the AgentLoop class,
        but we're not using hardcoded task patterns anymore."""
        return {}
        
    def get_step_to_tool_mapping(self) -> Dict[str, str]:
        """Return an empty dictionary for step-to-tool mapping.
        This method is needed for compatibility with the AgentLoop class,
        but we're not using hardcoded step-to-tool mappings anymore."""
        return {}

    async def shutdown(self):
        pass  # No persistent sessions to close in stateless SSE mode

