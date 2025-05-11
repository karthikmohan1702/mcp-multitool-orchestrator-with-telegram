# duckduckgo_mcp/server.py
# MCP server for DuckDuckGo Web Search (Corrected v8.x Usage)

import os
import logging
from fastapi import FastAPI, Request
from starlette.routing import Mount
import uvicorn
from dotenv import load_dotenv

# MCP Imports
from mcp.server.sse import SseServerTransport
from mcp.server.fastmcp import FastMCP

# Standard Python typing and libraries
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
import asyncio

# --- Corrected Import for Real Search ---
try:
    # Import the main class based on dir() output
    from duckduckgo_search import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False
    logging.warning("[WARN] duckduckgo-search library not found. DDG search tool will not work. Run: pip install -U duckduckgo-search")
# --- END Import ---


# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, '..', '.env'))

MCP_SERVER_HOST = os.getenv("DDG_MCP_SERVER_HOST", os.getenv("MCP_SERVER_HOST", "0.0.0.0"))
MCP_SERVER_PORT = int(os.getenv("DDG_MCP_SERVER_PORT", os.getenv("MCP_SERVER_PORT", "8040")))
MCP_POST_PATH = os.getenv("DDG_MCP_POST_PATH", "/duckduckgo_mcp_messages/")
MCP_SSE_PATH = os.getenv("DDG_MCP_SSE_PATH", "/duckduckgo_mcp_sse/")

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("duckduckgo_mcp_server")

# --- DuckDuckGo Search Result Dataclass ---
@dataclass
class SearchResult:
    title: str
    link: str
    snippet: str
    position: int

# --- DuckDuckGo Searcher Class (Using DDGS synchronous methods) ---
class DuckDuckGoSearcher:

    # NOTE: The search method remains async because the MCP tool calling it is async.
    # However, the duckduckgo_search call itself might be blocking if called this way.
    # For truly non-blocking, DDGS().atext() or similar async method would be needed if available.
    # This implementation uses the synchronous .text() within the async function.
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Performs a DuckDuckGo search using the DDGS class."""
        if not DUCKDUCKGO_AVAILABLE:
            logger.error("DuckDuckGo search unavailable: library not installed.")
            return [SearchResult(title="Search Error", link="#", snippet="duckduckgo-search library missing", position=1)]

        logger.info(f"Performing DDG search for: '{query}', max_results={max_results}")
        results_list = []
        try:
            # Use the synchronous context manager and text search method
            # The asyncio event loop will handle running this potentially blocking I/O
            # in a way that doesn't completely freeze other async tasks (depending on loop implementation),
            # but it's not ideal compared to a truly async library call if one exists.
            with DDGS(timeout=15) as ddgs:
                 # This is the synchronous call
                 search_results = ddgs.text(query, max_results=max_results)

                 # Convert results
                 if search_results:
                     for i, res in enumerate(search_results):
                         results_list.append(
                             SearchResult(
                                 title=res.get('title', 'No Title'),
                                 link=res.get('href', '#'),
                                 snippet=res.get('body', 'No Snippet'),
                                 position=i + 1
                             )
                         )
            logger.info(f"Found {len(results_list)} results for query '{query}'.")
            return results_list

        except Exception as e:
            # Log the specific error from duckduckgo_search
            logger.error(f"Error during DuckDuckGo search for '{query}': {e}", exc_info=True)
            # Return a structured error that the listener can potentially understand
            return [SearchResult(title="Search Execution Error", link="#", snippet=f"Error performing search: {e}", position=1)]
# --- End of Searcher Class ---


# --- MCP Server Setup ---
mcp = FastMCP("duckduckgo-fastmcp-server")
searcher = DuckDuckGoSearcher()

# --- DuckDuckGo MCP Tool Definition ---
@mcp.tool()
async def ddg_search(query: str, max_results: int = 5) -> list:
    """Searches DuckDuckGo and returns results. Usage: ddg_search|input={"query": "FastMCP", "max_results": 3}"""
    logger.info(f"MCP Tool 'ddg_search' called: query='{query}', max_results={max_results}")
    try:
        results: List[SearchResult] = await searcher.search(query, max_results)
        # Convert list of dataclasses to list of dicts for JSON serialization
        return [asdict(result) for result in results]
    except Exception as e:
        logger.error(f"Error within ddg_search MCP tool execution: {e}", exc_info=True)
        return [{"error": "Tool execution failed", "detail": str(e)}]

# --- FastAPI Application Setup ---
fastapi_app = FastAPI(title="DuckDuckGo MCP Server (FastMCP)")
sse_transport = SseServerTransport(MCP_POST_PATH)

@fastapi_app.get(MCP_SSE_PATH)
async def handle_sse_connection(request: Request):
    logger.info(f"Incoming SSE connection request from {request.client.host} to {MCP_SSE_PATH}")
    try:
        mcp_server_to_run = getattr(mcp, '_mcp_server', None)
        if not mcp_server_to_run: raise AttributeError("Cannot find internal MCP server object.")
    except AttributeError as e:
        logger.error(f"Failed to access internal MCP server: {e}")
        raise
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams: # type: ignore
        try:
            logger.info("SSE streams established, running MCP server logic...")
            init_options = getattr(mcp_server_to_run, 'create_initialization_options', lambda: None)()
            await mcp_server_to_run.run(streams[0], streams[1], init_options)
        finally: logger.debug("MCP server run loop finished for this SSE connection.")
    logger.info(f"SSE connection closed for {request.client.host}")

fastapi_app.router.routes.append(Mount(MCP_POST_PATH, app=sse_transport.handle_post_message))

# --- Run the FastAPI app directly using Uvicorn ---
if __name__ == "__main__":
    # *** Use correct import string for 'python -m' ***
    app_import_string = "duckduckgo_mcp.server:fastapi_app"

    logger.info(f"Starting DuckDuckGo MCP Uvicorn server on {MCP_SERVER_HOST}:{MCP_SERVER_PORT}...")
    logger.info(f"MCP SSE endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_SSE_PATH}")
    logger.info(f"MCP POST endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_POST_PATH}")
    if not DUCKDUCKGO_AVAILABLE:
         logger.critical("DuckDuckGo search library is missing. The ddg_search tool will fail. Please install it.")
    uvicorn.run(
        app_import_string, host=MCP_SERVER_HOST, port=MCP_SERVER_PORT,
        reload=False, log_level="info"
    )