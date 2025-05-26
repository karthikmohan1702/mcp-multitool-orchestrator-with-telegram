# core/session.py

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
    def __init__(self, server_configs: List[dict]):
        self.server_configs = server_configs
        self.tool_map: Dict[str, Dict[str, Any]] = {}  # tool_name → {config, tool}

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

    async def call_tool(self, tool_name: str, arguments: Any) -> Any:
        try:
            entry = self.tool_map.get(tool_name)
            if not entry:
                raise ValueError(f"Tool '{tool_name}' not found on any server.")
                
            config = entry["config"]
            server_name = config["name"]
            
            # Convert string arguments to dictionary if needed
            if isinstance(arguments, str):
                try:
                    # Check if it's already a JSON string
                    try:
                        import json
                        arguments = json.loads(arguments)
                        print(f"[DEBUG] Parsed JSON arguments: {arguments}")
                    except json.JSONDecodeError:
                        # Parse string like 'key1="value1", key2=5' into a dictionary
                        arg_dict = {}
                        import re
                        
                        # Use regex to properly handle quoted values with commas
                        pattern = r'(\w+)\s*=\s*("[^"]*"|[^,]+)'
                        matches = re.findall(pattern, arguments)
                        
                        for key, value in matches:
                            key = key.strip()
                            value = value.strip()
                            
                            # Remove quotes if present
                            if value.startswith('"') and value.endswith('"'):
                                value = value[1:-1]
                                
                            # Convert to appropriate type if possible
                            try:
                                if value.isdigit():
                                    value = int(value)
                                elif value.lower() == 'true':
                                    value = True
                                elif value.lower() == 'false':
                                    value = False
                                elif value.startswith('[') and value.endswith(']'):
                                    # Try to parse as a list
                                    try:
                                        value = json.loads(value)
                                    except:
                                        pass
                            except:
                                pass
                                
                            arg_dict[key] = value
                            
                        arguments = arg_dict
                        print(f"[DEBUG] Converted string arguments to dictionary: {arguments}")
                except Exception as e:
                    print(f"[ERROR] Failed to parse string arguments: {e}")
                    raise ValueError(f"Invalid argument format: {arguments}")
            
            print(f"[DEBUG] Preparing to call tool '{tool_name}' on {server_name} with arguments: {arguments}")
            try:
                async with sse_client(config["url"], timeout=15) as (read, write):  # Increased timeout
                    print(f"[DEBUG] SSE connection established for call_tool: {server_name}")
                    try:
                        async with ClientSession(read, write) as session:
                            print(f"[DEBUG] ClientSession created for call_tool: {server_name}")
                            await session.initialize()
                            print(f"[DEBUG] Session initialized for call_tool: {server_name}")
                            
                            # Call the tool and handle the response
                            try:
                                result = await session.call_tool(tool_name, arguments)
                                print(f"[DEBUG] Tool call complete for '{tool_name}' on {server_name}")
                                print(f"[DEBUG] Result type: {type(result)}, content: {result.content}")
                                return result
                            except Exception as e:
                                print(f"[ERROR] Exception during tool call execution: {e}")
                                import traceback
                                traceback.print_exc()
                                raise
                    except Exception as e:
                        print(f"[ERROR] Exception during ClientSession: {e}")
                        import traceback
                        traceback.print_exc()
                        raise
            except Exception as e:
                print(f"[ERROR] Exception during SSE client connection: {e}")
                import traceback
                traceback.print_exc()
                raise
        except Exception as e:
            print(f"[ERROR] Top-level exception in call_tool: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def list_all_tools(self) -> List[str]:
        return list(self.tool_map.keys())

    def get_all_tools(self) -> List[Any]:
        return [entry["tool"] for entry in self.tool_map.values()]

    async def shutdown(self):
        pass  # No persistent sessions to close in stateless SSE mode
