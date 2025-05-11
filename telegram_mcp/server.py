# telegram_mcp_server.py

import asyncio
import logging
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.routing import Mount # Use Mount from Starlette
import uvicorn
from dotenv import load_dotenv

# MCP Imports
from mcp.server.sse import SseServerTransport
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types

# Telegram Imports
from telegram import Update
from telegram.ext import Application as TelegramApplication, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Assuming .env is in the parent directory of the 'orchestrator' or 'telegram_mcp' module directory
dotenv_path = os.path.join(BASE_DIR, '..', '.env')
if not os.path.exists(dotenv_path):
    # Fallback if the script is in a subdirectory like 'telegram_mcp' and .env is one level up from that
    dotenv_path = os.path.join(BASE_DIR, '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    # If .env is in the same directory as this script (less common for multi-server setups)
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env'))


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Use a specific prefix for Telegram MCP server env vars to avoid clashes
MCP_SERVER_HOST = os.getenv("TELEGRAM_MCP_HOST", os.getenv("MCP_SERVER_HOST", "0.0.0.0"))
MCP_SERVER_PORT = int(os.getenv("TELEGRAM_MCP_PORT", os.getenv("MCP_SERVER_PORT_TELEGRAM", "8000"))) # Default to 8000 for Telegram
MCP_POST_PATH = os.getenv("TELEGRAM_MCP_POST_PATH", "/telegram_mcp_messages/") # Ensure trailing slash
MCP_SSE_PATH = os.getenv("TELEGRAM_MCP_SSE_PATH", "/telegram_mcp_sse/") # Ensure trailing slash


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("telegram_mcp_server")

# --- Global Variables ---
sse_output_stream = None
telegram_application: TelegramApplication | None = None # Renamed for clarity

# --- Telegram Bot Logic ---
async def handle_tg_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming messages from Telegram and forwards them to the SSE stream."""
    global sse_output_stream
    if update.message and update.message.text:
        user = update.message.from_user
        message_data = {
            "user_id": user.id,
            "username": user.username or user.first_name,
            "text": update.message.text,
            "message_id": update.message.message_id,
            "chat_id": update.message.chat_id,
        }
        logger.info(f"Received Telegram message: {message_data}")
        if sse_output_stream is not None:
            try:
                # Using LoggingMessageNotification as a generic way to send structured data
                notification = mcp_types.LoggingMessageNotification(
                    jsonrpc="2.0",
                    method="notifications/message", # Custom method for Telegram messages
                    params=mcp_types.LoggingMessageNotificationParams(level="info", data=message_data)
                )
                await sse_output_stream.send(notification)
                logger.info(f"Sent notification to SSE: {message_data}")
            except Exception as e:
                logger.error(f"Error sending message to SSE stream: {e}", exc_info=True)
        else:
            logger.warning("sse_output_stream is None. Cannot forward Telegram message.")

async def tg_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Telegram Updates."""
    logger.error(f"Telegram Update {update} caused error {context.error}", exc_info=context.error)

def _setup_telegram_application() -> TelegramApplication:
    """Synchronously sets up the python-telegram-bot application."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set.")
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")
    application = TelegramApplication.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tg_message))
    application.add_error_handler(tg_error_handler)
    return application

# --- Lifespan Context Manager for FastAPI ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages Telegram bot startup and shutdown with FastAPI's lifespan."""
    global telegram_application
    logger.info("FastAPI app startup: Initializing Telegram bot...")
    try:
        telegram_application = _setup_telegram_application()
        await telegram_application.initialize()
        await telegram_application.start()
        if telegram_application.updater: # updater might be None if start() fails
            await telegram_application.updater.start_polling()
            logger.info("Telegram bot started polling successfully.")
        else:
            logger.error("Telegram bot updater not available after start().")
            raise RuntimeError("Telegram bot updater failed to initialize.")
    except Exception as e:
        logger.critical(f"Failed to initialize and start Telegram bot: {e}", exc_info=True)
        # Depending on severity, you might want to re-raise to stop FastAPI
        # For now, we'll let FastAPI start but log the critical failure.
        # raise RuntimeError("Telegram Bot failed to start") from e

    yield # Application runs here

    logger.info("FastAPI app shutdown: Stopping Telegram bot...")
    if telegram_application:
        try:
            if telegram_application.updater and telegram_application.updater.is_running:
                await telegram_application.updater.stop()
            await telegram_application.stop()
            await telegram_application.shutdown()
            logger.info("Telegram bot stopped gracefully.")
        except Exception as e:
            logger.error(f"Error stopping Telegram bot during shutdown: {e}", exc_info=True)
    logger.info("FastAPI shutdown complete.")

# --- MCP Server Setup ---
mcp = FastMCP(
    "telegram-mcp-server",
    dependencies=[] # Add any specific dependencies for this MCP server if needed
)

@mcp.tool()
async def telegram_send_message(chat_id: int, text: str) -> dict:
    """Sends a message to a specific chat_id via the Telegram bot."""
    global telegram_application
    if not telegram_application or not telegram_application.bot:
        logger.error("MCP Tool 'telegram_send_message' called, but Telegram app/bot not initialized.")
        return {"status": "error", "detail": "Telegram bot not available."}

    logger.info(f"MCP Tool 'telegram_send_message' called: chat_id={chat_id}, text='{text[:50]}...'")
    try:
        await telegram_application.bot.send_message(chat_id=chat_id, text=text)
        logger.info(f"Message successfully sent to chat_id {chat_id}.")
        return {"status": "success", "detail": f"Message sent to {chat_id}"}
    except Exception as e:
        logger.error(f"Failed to send Telegram message via MCP tool: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}

# --- FastAPI Application Setup ---
# Pass the lifespan manager to the FastAPI app
fastapi_app = FastAPI(title="Telegram MCP Server (FastMCP)", lifespan=lifespan)
sse_transport = SseServerTransport(MCP_POST_PATH)

@fastapi_app.get(MCP_SSE_PATH)
async def handle_sse_connection(request: Request):
    global sse_output_stream
    logger.info(f"Incoming SSE connection request from {request.client.host} to {MCP_SSE_PATH}")
    try:
        # Access the internal MCP server instance from the FastMCP wrapper
        mcp_server_to_run = getattr(mcp, '_mcp_server', None)
        if not mcp_server_to_run:
            logger.error("Could not access mcp._mcp_server. FastMCP structure might have changed or not initialized.")
            raise AttributeError("Cannot find the internal MCP server object in FastMCP instance.")
    except AttributeError as e:
        logger.error(f"Failed to access internal MCP server: {e}", exc_info=True)
        # Consider returning an HTTP 500 error response or similar
        raise # Re-raise to indicate a server-side issue

    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send # type: ignore
    ) as streams:
        input_stream, output_stream = streams
        sse_output_stream = output_stream # Make the output stream globally available for handle_tg_message
        try:
            logger.info("SSE streams established, running MCP server logic for connection...")
            init_options = getattr(mcp_server_to_run, 'create_initialization_options', lambda: None)()
            await mcp_server_to_run.run(
                input_stream, output_stream, init_options
            )
        finally:
            sse_output_stream = None # Clear the stream when connection closes
            logger.debug("MCP server run loop finished for this SSE connection.")
    logger.info(f"SSE connection closed for {request.client.host}")

# Mount the POST Message Handler for MCP client messages
fastapi_app.router.routes.append(
    Mount(MCP_POST_PATH, app=sse_transport.handle_post_message)
)

# --- Run the FastAPI app directly using Uvicorn ---
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set. Server cannot start.")
    else:
        # This import string should match how you intend to run the module.
        # If your module is 'telegram_mcp_server.py' in a directory 'orchestrator',
        # and you run `python -m orchestrator.telegram_mcp_server`,
        # then the string should be "orchestrator.telegram_mcp_server:fastapi_app".
        # Assuming this script is named 'telegram_mcp_server.py' and run from its directory or as a module.
        module_name = os.path.splitext(os.path.basename(__file__))[0] # e.g., "telegram_mcp_server"

        # Construct the app_import_string based on how the script might be located/run.
        # If in a package 'orchestrator', and you run `python -m orchestrator.telegram_mcp_server`
        # the __package__ variable would be 'orchestrator'.
        if __package__:
             app_import_string = f"{__package__}.{module_name}:fastapi_app"
        else:
             app_import_string = f"{module_name}:fastapi_app"


        logger.info(f"Starting Telegram MCP Uvicorn server on {MCP_SERVER_HOST}:{MCP_SERVER_PORT}...")
        logger.info(f"MCP SSE endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_SSE_PATH}")
        logger.info(f"MCP POST endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_POST_PATH}")
        uvicorn.run(
            app_import_string,
            host=MCP_SERVER_HOST,
            port=MCP_SERVER_PORT,
            reload=False, # Set to True for development if you want auto-reloads
            log_level="info"
        )