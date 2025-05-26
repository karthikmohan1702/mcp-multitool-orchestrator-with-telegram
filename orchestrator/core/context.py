# core/context.py

from typing import List, Optional, Dict, Any
import yaml
import time
import uuid
import os
import sys

# We'll implement the MemoryManager and MemoryItem later
# For now, let's create placeholder imports that we'll implement in the memory module
from modules.memory import MemoryManager, MemoryItem


class AgentProfile:
    """
    Loads and stores agent configuration from profiles.yaml
    """
    def __init__(self, config_path: str = "config/profiles.yaml"):
        # Adjust the path to be relative to the telegram_agent directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_config_path = os.path.join(base_dir, config_path)
        
        with open(full_config_path, "r") as f:
            config = yaml.safe_load(f)

        self.name = config["agent"]["name"]
        self.id = config["agent"]["id"]
        self.description = config["agent"]["description"]
        self.strategy = config["strategy"]["type"]
        self.max_steps = config["strategy"]["max_steps"]

        self.memory_config = config["memory"]
        self.llm_config = config["llm"]
        self.persona = config["persona"]
        self.mcp_servers = config.get("mcp_servers", [])

    def __repr__(self):
        return f"<AgentProfile {self.name} ({self.strategy})>"


class ToolCallTrace:
    """
    Stores information about a tool call for tracing and debugging
    """
    def __init__(self, tool_name: str, arguments: Dict[str, Any], result: Any):
        self.tool_name = tool_name
        self.arguments = arguments
        self.result = result
        self.timestamp = time.time()


class AgentContext:
    """
    Maintains session-wide state across loop steps
    """
    def __init__(self, user_input: str, profile: Optional[AgentProfile] = None):
        self.user_input = user_input
        self.agent_profile = profile or AgentProfile()
        self.session_id = f"session-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        self.step = 0
        
        # Initialize memory manager
        self.memory = MemoryManager()
        
        # Initialize traces
        self.memory_trace: List[MemoryItem] = []
        self.tool_calls: List[ToolCallTrace] = []
        self.final_answer: Optional[str] = None

    def add_tool_trace(self, name: str, args: Dict[str, Any], result: Any):
        """Add a tool call to the trace"""
        trace = ToolCallTrace(name, args, result)
        self.tool_calls.append(trace)

    def add_memory(self, item: MemoryItem):
        """Add a memory item to both the trace and the memory manager"""
        self.memory_trace.append(item)
        self.memory.add(item)

    def __repr__(self):
        return f"<AgentContext step={self.step}, session_id={self.session_id}>"
