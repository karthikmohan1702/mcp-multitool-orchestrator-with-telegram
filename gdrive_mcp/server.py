# gdrive_sse_server.py
# MCP SSE server for Google Drive (Python version)

import os
import asyncio
import logging
from contextlib import asynccontextmanager # For lifespan manager
from fastapi import FastAPI, Request
from starlette.routing import Mount
import uvicorn
from dotenv import load_dotenv
from typing import List, Dict, Optional, Union, Any

# MCP Imports
from mcp.server.sse import SseServerTransport
from mcp.server.fastmcp import FastMCP
import mcp.types as mcp_types # Keep this for potential type hinting if needed later

# Google API Imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource # For type hinting build()
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request as GoogleRequest

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Load .env from parent directory of this script's directory
dotenv_path = os.path.join(BASE_DIR, '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else: # Fallback for .env in the same directory or other structures if needed
    load_dotenv()


# Use GDrive-specific environment variables with defaults
MCP_SERVER_HOST = os.getenv("GDRIVE_MCP_HOST", os.getenv("MCP_SERVER_HOST", "0.0.0.0"))
MCP_SERVER_PORT = int(os.getenv("GDRIVE_MCP_PORT", "8020")) # Default GDrive MCP to 8020
MCP_POST_PATH = os.getenv("GDRIVE_MCP_POST_PATH", "/gdrive_mcp_messages/")
MCP_SSE_PATH = os.getenv("GDRIVE_MCP_SSE_PATH", "/gdrive_mcp_sse/") # Consistent SSE path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("gdrive_mcp_server")

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets'] # Added sheets scope

# Use path relative to this script's directory for credentials
CREDS_FILE_PATH = os.path.join(BASE_DIR, "..", "client_secrets.json")
TOKEN_PATH = os.path.join(BASE_DIR, "..", "token.json")

# Global variables for Google API services, initialized in lifespan
drive_service: Resource | None = None
sheets_service: Resource | None = None

# --- Google Services Initialization ---
def _get_google_creds() -> Credentials | None:
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.error(f"Failed to load token from {TOKEN_PATH}: {e}")
            # Potentially delete corrupted token file so re-auth can occur
            try:
                os.remove(TOKEN_PATH)
                logger.info(f"Removed potentially corrupted token file: {TOKEN_PATH}")
            except OSError as oe:
                logger.error(f"Error removing token file {TOKEN_PATH}: {oe}")


    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Google credentials expired, attempting to refresh.")
                creds.refresh(GoogleRequest())
            except Exception as e:
                logger.error(f"Failed to refresh Google credentials: {e}. Re-authentication required.")
                creds = None # Force re-authentication
        else:
            logger.info("Google credentials not found or invalid, starting OAuth flow.")
            if not os.path.exists(CREDS_FILE_PATH):
                logger.critical(f"CRITICAL: Google client_secrets.json not found at {CREDS_FILE_PATH}")
                raise FileNotFoundError(f"client_secrets.json not found at {CREDS_FILE_PATH}")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE_PATH, SCOPES)
            creds = flow.run_local_server(port=0) # User will need to authenticate in browser
        
        if creds:
            try:
                with open(TOKEN_PATH, 'w') as token_file:
                    token_file.write(creds.to_json())
                logger.info(f"Google credentials saved to {TOKEN_PATH}")
            except Exception as e:
                 logger.error(f"Failed to save token to {TOKEN_PATH}: {e}")
        else:
            logger.error("Failed to obtain Google credentials after OAuth flow.")
            return None
    return creds

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages Google API service initialization on startup."""
    global drive_service, sheets_service
    logger.info("FastAPI app startup: Initializing Google API services...")
    try:
        creds = _get_google_creds()
        if creds:
            drive_service = build('drive', 'v3', credentials=creds)
            sheets_service = build('sheets', 'v4', credentials=creds) # Use the same creds
            logger.info("Google Drive and Sheets API services initialized successfully.")
        else:
            logger.critical("Failed to obtain Google credentials. Google Drive/Sheets tools will not work.")
            # Optionally, raise an error to prevent FastAPI startup if services are critical
            # raise RuntimeError("Failed to initialize Google services")
    except Exception as e:
        logger.critical(f"Critical error during Google service initialization: {e}", exc_info=True)
        # raise RuntimeError(f"Google service init error: {e}") from e
    
    yield # Application runs here

    logger.info("FastAPI app shutdown: No specific shutdown actions for GDrive services needed here.")


# --- MCP Server Setup ---
mcp = FastMCP(
    "gdrive-fastmcp-server",
    dependencies=[] # Add dependencies if any are used by tools via context
)
sse_transport = SseServerTransport(MCP_POST_PATH)

# Pass the lifespan manager to the FastAPI app
fastapi_app = FastAPI(title="Google Drive MCP SSE Server (FastMCP)", lifespan=lifespan)

# Mount the POST Message Handler for MCP client messages BEFORE defining other routes on that path
fastapi_app.router.routes.append(
    Mount(MCP_POST_PATH, app=sse_transport.handle_post_message)
)

# --- SSE GET Endpoint Handler ---
@fastapi_app.get(MCP_SSE_PATH)
async def handle_sse_connection(request: Request):
    """
    Handles incoming Server-Sent Events (SSE) connections for MCP clients.

    Args:
        request (Request): The incoming FastAPI request object.

    Returns:
        StreamingResponse: The SSE stream for the client.
    """
    logger.info(f"Incoming SSE connection request from {request.client.host} to {MCP_SSE_PATH}")
    try:
        # Access the internal MCP server instance from the FastMCP wrapper
        mcp_server_to_run = getattr(mcp, '_mcp_server', None)
        if not mcp_server_to_run:
            logger.error("Could not access mcp._mcp_server. FastMCP structure might have changed or not initialized.")
            raise AttributeError("Cannot find the internal MCP server object in FastMCP instance.")
    except AttributeError as e:
        logger.error(f"Failed to access internal MCP server: {e}", exc_info=True)
        raise # Re-raise to indicate a server-side issue

    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send # type: ignore
    ) as streams:
        input_stream, output_stream = streams
        try:
            logger.info("SSE streams established, running MCP server logic for connection...")
            init_options = getattr(mcp_server_to_run, 'create_initialization_options', lambda: None)()
            await mcp_server_to_run.run(
                input_stream, output_stream, init_options
            )
        finally:
            logger.debug("MCP server run loop finished for this SSE connection.")
    logger.info(f"SSE connection closed for {request.client.host}")


# --- Google Drive MCP Tools ---
@mcp.tool()
async def gdrive_list_files(query: str = None, page_size: int = 10) -> list:
    """Lists files in Google Drive. Usage: gdrive_list_files|input={"query": "name contains 'Report'", "page_size": 5}"""
    if not drive_service:
        logger.error("gdrive_list_files tool called but Drive service is not available.")
        return [{"error": "Google Drive service not initialized."}]
    try:
        logger.info(f"Executing gdrive_list_files: query='{query}', page_size={page_size}")
        results = drive_service.files().list(
            q=query,
            pageSize=max(1, min(page_size, 1000)), # Ensure page_size is within valid range
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size,webViewLink,iconLink)"
        ).execute()
        files = results.get('files', [])
        logger.info(f"Found {len(files)} files.")
        return files
    except HttpError as error:
        logger.error(f"An HttpError occurred in gdrive_list_files: {error}", exc_info=True)
        return [{"error": f"Google Drive API error: {error.resp.status} - {error.reason}"}]
    except Exception as e:
        logger.error(f"An unexpected error occurred in gdrive_list_files: {e}", exc_info=True)
        return [{"error": f"An unexpected error occurred: {str(e)}"}]

@mcp.tool()
async def gdrive_create_sheet(sheet_name: str) -> dict:
    """Creates a new Google Sheet. Usage: gdrive_create_sheet|input={"sheet_name": "My New Sheet"}"""
    if not drive_service:
        logger.error("gdrive_create_sheet tool called but Drive service is not available.")
        return {"error": "Google Drive service not initialized."}
    try:
        logger.info(f"Executing gdrive_create_sheet: sheet_name='{sheet_name}'")
        file_metadata = {
            'name': sheet_name,
            'mimeType': 'application/vnd.google-apps.spreadsheet'
        }
        sheet = drive_service.files().create(body=file_metadata, fields='id, webViewLink').execute()
        logger.info(f"Created Google Sheet with ID: {sheet.get('id')}")
        return {"sheet_id": sheet.get('id'), "sheet_url": sheet.get('webViewLink')}
    except HttpError as error:
        logger.error(f"An HttpError occurred in gdrive_create_sheet: {error}", exc_info=True)
        return {"error": f"Google Drive API error: {error.resp.status} - {error.reason}"}
    except Exception as e:
        logger.error(f"An unexpected error occurred in gdrive_create_sheet: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def gdrive_write_sheet(sheet_id: str, values: List[List[Any]], range_name: str = "Sheet1!A1") -> dict:
    """Writes data to a Google Sheet. Usage: gdrive_write_sheet|input={"sheet_id": "abc123", "values": [["A",1],["B",2]], "range_name": "Sheet1!A1"}"""
    if not sheets_service:
        logger.error("gdrive_write_sheet tool called but Sheets service is not available.")
        return {"error": "Google Sheets service not initialized."}
    try:
        logger.info(f"Executing gdrive_write_sheet: sheet_id='{sheet_id}', range='{range_name}', data_rows={len(values)}")
        body = {'values': values}
        result = sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED", # Or "RAW"
            body=body
        ).execute()
        logger.info(f"Successfully wrote to Google Sheet ID: {sheet_id}. Result: {result}")
        return {
            "status": "success",
            "updated_range": result.get('updatedRange'),
            "updated_rows": result.get('updatedRows'),
            "updated_columns": result.get('updatedColumns'),
            "updated_cells": result.get('updatedCells')
        }
    except HttpError as error:
        logger.error(f"An HttpError occurred in gdrive_write_sheet: {error}", exc_info=True)
        return {"error": f"Google Sheets API error: {error.resp.status} - {error.reason}"}
    except Exception as e:
        logger.error(f"An unexpected error occurred in gdrive_write_sheet: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def gdrive_share_file(file_id: str, email_address: str, role: str = "reader", share_type: str = "user") -> dict:
    """Shares a Google Drive file or folder. Usage: gdrive_share_file|input={"file_id": "abc123", "email_address": "user@example.com", "role": "writer"}"""
    if not drive_service:
        logger.error("gdrive_share_file tool called but Drive service is not available.")
        return {"error": "Google Drive service not initialized."}
    try:
        logger.info(f"Executing gdrive_share_file: file_id='{file_id}', email='{email_address}', role='{role}', type='{share_type}'")
        permission = {
            'type': share_type,
            'role': role,
            'emailAddress': email_address
        }
        drive_service.permissions().create(
            fileId=file_id,
            body=permission,
            sendNotificationEmail=True # Send notification to the user
        ).execute()
        logger.info(f"Successfully shared file ID {file_id} with {email_address} as {role}.")
        return {"status": "success", "detail": f"File {file_id} shared with {email_address} as {role}."}
    except HttpError as error:
        logger.error(f"An HttpError occurred in gdrive_share_file: {error}", exc_info=True)
        return {"error": f"Google Drive API error: {error.resp.status} - {error.reason}"}
    except Exception as e:
        logger.error(f"An unexpected error occurred in gdrive_share_file: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred: {str(e)}"}


# --- Run the FastAPI app directly using Uvicorn ---
if __name__ == "__main__":
    # Dynamically create the app import string based on the filename
    module_name = os.path.splitext(os.path.basename(__file__))[0]
    # If this script is part of a package and run with `python -m package.module`
    # `__package__` will be set. Otherwise, it's None.
    if __package__:
        app_import_string = f"{__package__}.{module_name}:fastapi_app"
    else:
        app_import_string = f"{module_name}:fastapi_app"

    logger.info(f"Starting Google Drive MCP Uvicorn server on {MCP_SERVER_HOST}:{MCP_SERVER_PORT}...")
    logger.info(f"MCP SSE endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_SSE_PATH}")
    logger.info(f"MCP POST endpoint: http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}{MCP_POST_PATH}")
    logger.info(f"To authorize or re-authorize Google services, you might need to run this script in an environment where you can open a web browser.")
    
    uvicorn.run(
        app_import_string,
        host=MCP_SERVER_HOST,
        port=MCP_SERVER_PORT,
        reload=False, # Set to True for development if it helps, but be mindful of auth flow
        log_level="info"
    )