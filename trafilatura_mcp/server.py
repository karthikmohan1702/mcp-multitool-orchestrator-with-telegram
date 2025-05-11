# trafilatura_mcp/server.py
# MCP SSE server for Trafilatura (web content extraction)

import os
import logging
from fastapi import FastAPI, Request
from starlette.routing import Mount
import uvicorn
from dotenv import load_dotenv

from mcp.server.sse import SseServerTransport
from mcp.server.fastmcp import FastMCP
import mcp.types as mcp_types

from typing import List, Dict, Any
from dataclasses import dataclass, asdict
import trafilatura

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, '..', '.env'))
MCP_SERVER_HOST = os.getenv("TRAFILATURA_MCP_SERVER_HOST", os.getenv("MCP_SERVER_HOST", "0.0.0.0"))
MCP_SERVER_PORT = int(os.getenv("TRAFILATURA_MCP_SERVER_PORT", os.getenv("MCP_SERVER_PORT", "8030")))
MCP_POST_PATH = os.getenv("TRAFILATURA_MCP_POST_PATH", "/trafilatura_mcp_messages/")
MCP_SSE_PATH = os.getenv("TRAFILATURA_MCP_SSE_PATH", "/trafilatura_mcp_sse/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("trafilatura_mcp_server")

# --- MCP Server Setup ---
mcp = FastMCP("trafilatura-fastmcp-server")
sse_transport = SseServerTransport(MCP_POST_PATH)
fastapi_app = FastAPI(title="Trafilatura MCP SSE Server (FastMCP)")

fastapi_app.router.routes.append(
    Mount(MCP_POST_PATH, app=sse_transport.handle_post_message)
)

# --- Trafilatura Extraction Result Dataclass ---
@dataclass
class MetadataResult:
    title: str = ""
    author: str = ""
    date: str = ""
    description: str = ""
    other: Dict[str, Any] = None

# --- Trafilatura MCP Tools ---
@mcp.tool()
async def extract_text(url: str) -> str:
    """
    Extracts main text content from a URL.
    Usage: extract_text|input={"url": "https://example.com"}
    """
    logger.info(f"[extract_text] Starting extraction for URL: {url}")
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.warning(f"[extract_text] Could not download URL: {url}")
            return "Could not download URL."
        result = trafilatura.extract(downloaded)
        if result:
            logger.info(f"[extract_text] Extraction successful for URL: {url}")
            return result
        else:
            logger.info(f"[extract_text] No main text content found for URL: {url}")
            return "No main text content found."
    except Exception as e:
        logger.error(f"[extract_text] Error extracting text from {url}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def extract_metadata(url: str) -> dict:
    """
    Extracts metadata (title, author, date, etc.) from a URL.
    Usage: extract_metadata|input={"url": "https://example.com"}
    """
    logger.info(f"[extract_metadata] Starting metadata extraction for URL: {url}")
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.warning(f"[extract_metadata] Could not download URL: {url}")
            return {"error": "Could not download URL."}
        result = trafilatura.extract(downloaded, output_format='json')
        if not result:
            logger.info(f"[extract_metadata] No metadata found for URL: {url}")
            return {"error": "No metadata found."}
        import json
        meta = json.loads(result)
        # Optionally wrap in dataclass for structure
        meta_result = MetadataResult(**{k: v for k, v in meta.items() if k in MetadataResult.__annotations__}, other={k: v for k, v in meta.items() if k not in MetadataResult.__annotations__})
        logger.info(f"[extract_metadata] Metadata extraction successful for URL: {url}")
        return asdict(meta_result)
    except Exception as e:
        logger.error(f"[extract_metadata] Error extracting metadata from {url}: {e}")
        return {"error": str(e)}

# --- FastAPI Application Setup ---
@fastapi_app.get(MCP_SSE_PATH)
async def handle_sse_connection(request: Request):
    logger.info(f"Incoming SSE connection request from {request.client.host}")
    try:
        mcp_server_to_run = mcp._mcp_server
    except AttributeError:
        logger.error("Could not access mcp._mcp_server. FastMCP structure might have changed.")
        raise AttributeError("Cannot find the internal server object in FastMCP instance. Check SDK.")

    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        try:
            logger.info("SSE streams established, running MCP server logic...")
            await mcp_server_to_run.run(
                streams[0], streams[1], mcp_server_to_run.create_initialization_options()
            )
        finally:
            pass
    logger.info(f"SSE connection closed for {request.client.host}")

if __name__ == "__main__":
    logger.info(f"Starting Uvicorn server on {MCP_SERVER_HOST}:{MCP_SERVER_PORT}...")
    uvicorn.run(
        "trafilatura_mcp.server:fastapi_app",
        host=MCP_SERVER_HOST,
        port=MCP_SERVER_PORT,
        reload=False,
        log_level="info"
    )
