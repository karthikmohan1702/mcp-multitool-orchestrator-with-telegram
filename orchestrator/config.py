import os
import logging
from typing import Dict, List, Optional, Any

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True
)
logger = logging.getLogger("TelegramMCPListener")

# --- Configuration ---
DDG_MCP_SERVER_URL = os.getenv("DDG_MCP_SERVER_URL", "http://localhost:8040")
DDG_MCP_SSE_PATH = os.getenv("DDG_MCP_SSE_PATH", "/duckduckgo_mcp_sse/")
DDG_SSE_ENDPOINT = f"{DDG_MCP_SERVER_URL}{DDG_MCP_SSE_PATH}"

TRAFILATURA_MCP_SERVER_URL = os.getenv("TRAFILATURA_MCP_SERVER_URL", "http://localhost:8030")
TRAFILATURA_MCP_SSE_PATH = os.getenv("TRAFILATURA_MCP_SSE_PATH", "/trafilatura_mcp_sse/")
TRAFILATURA_SSE_ENDPOINT = f"{TRAFILATURA_MCP_SERVER_URL}{TRAFILATURA_MCP_SSE_PATH}"

TELEGRAM_MCP_SERVER_URL = os.getenv("TELEGRAM_MCP_SERVER_URL", "http://localhost:8000")
TELEGRAM_MCP_SSE_PATH = os.getenv("TELEGRAM_MCP_SSE_PATH", "/telegram_mcp_sse/")
TELEGRAM_MCP_ENDPOINT = f"{TELEGRAM_MCP_SERVER_URL}{TELEGRAM_MCP_SSE_PATH}"

GDRIVE_MCP_SERVER_URL = os.getenv("GDRIVE_MCP_SERVER_URL", "http://localhost:8020")
GDRIVE_MCP_SSE_PATH = os.getenv("GDRIVE_MCP_SSE_PATH", "/gdrive_mcp_sse/")
GDRIVE_SSE_ENDPOINT = f"{GDRIVE_MCP_SERVER_URL}{GDRIVE_MCP_SSE_PATH}"

SOURCE_SSE_URL = os.getenv("SOURCE_SSE_URL", "http://localhost:8000")
SOURCE_SSE_PATH = os.getenv("SOURCE_SSE_PATH", "/telegram_mcp_sse/")
SOURCE_SSE_ENDPOINT = f"{SOURCE_SSE_URL}{SOURCE_SSE_PATH}"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = None
GEMINI_ENABLED = False
if GEMINI_API_KEY:
    GEMINI_MODEL_NAME = "gemini-2.0-flash"
    GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    GEMINI_ENABLED = True

# Global tool to endpoint map
tool_to_endpoint_map: Dict[str, str] = {}
