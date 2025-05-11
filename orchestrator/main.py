import asyncio
from .perception import discover_mcp_tools, listen_to_source_sse, available_mcp_tools
from .config import logger
from .perception import FASTMCP_AVAILABLE
from .config import GEMINI_ENABLED

async def main():
    logger.info("--- Listener Main Coroutine Starting ---")
    logger.info("Initiating tool discovery...")
    await discover_mcp_tools()
    if available_mcp_tools is None or not available_mcp_tools:
        logger.warning("Tool discovery failed or returned no tools. Listener will continue but LLM may not be able to use tools effectively.")
    else:
        logger.info(f"Tool discovery completed. {len(available_mcp_tools)} total tools available.")
    logger.info("Starting main SSE listener loop for source messages...")
    await listen_to_source_sse()
    logger.info("--- Listener Main Coroutine Ended (This is unexpected if service should run indefinitely) ---")

if __name__ == "__main__":
    if not FASTMCP_AVAILABLE:
        logger.error("fastmcp or mcp.types not available. Exiting.")
    elif not GEMINI_ENABLED:
        logger.warning("Gemini API key not set. LLM tool selection will be disabled.")
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("Listener stopped by user (KeyboardInterrupt).")
        except Exception as e:
            logger.critical(f"Fatal error during main execution: {e}", exc_info=True)
