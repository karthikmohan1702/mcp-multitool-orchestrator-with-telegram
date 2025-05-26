# serpapi_mcp/server.py
# MCP server for SerpAPI Web Search

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
import requests

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, '..', '.env'))

MCP_SERVER_HOST = os.getenv("SERPAPI_MCP_SERVER_HOST", os.getenv("MCP_SERVER_HOST", "0.0.0.0"))
MCP_SERVER_PORT = int(os.getenv("SERPAPI_MCP_SERVER_PORT", os.getenv("MCP_SERVER_PORT", "8050")))
MCP_POST_PATH = os.getenv("SERPAPI_MCP_POST_PATH", "/serpapi_mcp_messages/")
MCP_SSE_PATH = os.getenv("SERPAPI_MCP_SSE_PATH", "/serpapi_mcp_sse/")
SERP_API_KEY = os.getenv("SERP_API_KEY")

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("serpapi_mcp_server")

# --- SerpAPI Search Result Dataclass ---
@dataclass
class SearchResult:
    title: str
    link: str
    snippet: str
    position: int

# --- SerpAPI Searcher Class ---
class SerpAPISearcher:
    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Performs a Google search using SerpAPI."""
        if not SERP_API_KEY:
            logger.error("SerpAPI key not set in environment.")
            return [SearchResult(title="Search Error", link="#", snippet="SERP_API_KEY missing in .env", position=1)]
        logger.info(f"Performing SerpAPI search for: '{query}', max_results={max_results}")
        try:
            params = {
                "q": query,
                "api_key": SERP_API_KEY,
                "engine": "google",
                "num": max_results,
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            results_list = []
            organic_results = data.get("organic_results", [])
            for i, res in enumerate(organic_results[:max_results]):
                results_list.append(
                    SearchResult(
                        title=res.get("title", "No Title"),
                        link=res.get("link", "#"),
                        snippet=res.get("snippet", "No Snippet"),
                        position=i + 1
                    )
                )
            logger.info(f"Found {len(results_list)} results for query '{query}'.")
            return results_list
        except Exception as e:
            logger.error(f"Error during SerpAPI search for '{query}': {e}", exc_info=True)
            return [SearchResult(title="Search Execution Error", link="#", snippet=f"Error performing search: {e}", position=1)]

# --- MCP Server Setup ---
mcp = FastMCP("serpapi-fastmcp-server")
searcher = SerpAPISearcher()

# --- SerpAPI MCP Tool Definition ---
@mcp.tool()
async def serpapi_search(query: str, max_results: int = 5) -> list:
    """Searches Google via SerpAPI and returns results. Usage: serpapi_search|input={"query": "FastMCP", "max_results": 3}"""
    logger.info(f"MCP Tool 'serpapi_search' called: query='{query}', max_results={max_results}")
    try:
        results: List[SearchResult] = await searcher.search(query, max_results)
        return [asdict(result) for result in results]
    except Exception as e:
        logger.error(f"Error within serpapi_search MCP tool execution: {e}", exc_info=True)
        return [{"error": "Tool execution failed", "detail": str(e)}]

# --- FastAPI Application Setup ---
fastapi_app = FastAPI(title="SerpAPI MCP Server (FastMCP)")
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
    app_import_string = "serpapi_mcp.server:fastapi_app"
    logger.info(f"Starting SerpAPI MCP Uvicorn server on {MCP_SERVER_HOST}:{MCP_SERVER_PORT}...")
    logger.info(f"MCP SSE endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_SSE_PATH}")
    logger.info(f"MCP POST endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_POST_PATH}")
    uvicorn.run(
        app_import_string, host=MCP_SERVER_HOST, port=MCP_SERVER_PORT,
        reload=False, log_level="info"
    )
