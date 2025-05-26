# main.py

import asyncio
import json
import os
import yaml
from mcp.client.sse import sse_client
from core.session import MultiMCP
from core.loop import AgentLoop
from core.context import AgentProfile

# Adjust this URL to match your telegram MCP server SSE endpoint
TELEGRAM_MCP_SSE_URL = "http://localhost:8000/telegram_mcp_sse/"


def extract_telegram_data(event):
    """
    Extract Telegram message data from JSONRPCNotification event.
    Returns a tuple of (message_text, chat_id) if found, or (error_message, None) if not.
    """
    try:
        # Try direct attribute
        params = getattr(event, 'params', None)
        if params is None and hasattr(event, 'root'):
            params = getattr(event.root, 'params', None)
        if params and isinstance(params, dict):
            data = params.get('data')
            if data and isinstance(data, dict):
                text = data.get('text')
                chat_id = data.get('chat_id')
                if text:
                    return text, chat_id
        # fallback: show structure for debugging
        return f"[No text found, type={type(event)}, dir={dir(event)}, repr={repr(event)}]", None
    except Exception as e:
        return f"[Parse error: {e}]", None


async def process_telegram_message(message_text, chat_id=None):
    """
    Process a Telegram message using the agent
    """
    print(f"Processing message: {message_text}")
    
    try:
        # Load MCP server configs from profiles.yaml
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, "config", "profiles.yaml")
        
        with open(config_path, "r") as f:
            profile = yaml.safe_load(f)
            mcp_servers = profile.get("mcp_servers", [])

        # Initialize MultiMCP with all servers
        multi_mcp = MultiMCP(server_configs=mcp_servers)
        print("Initializing MCP connections...")
        await multi_mcp.initialize()

        # Create and run agent
        agent = AgentLoop(
            user_input=message_text,
            dispatcher=multi_mcp
        )

        try:
            final_response = await agent.run()
            response_text = final_response.replace("FINAL_ANSWER:", "").strip()
            
            # If we got a generic [no result], provide a more helpful message
            if response_text == "[no result]":
                response_text = "I'm sorry, I encountered an issue while processing your request. Please try a simpler query or check if all required services are running properly."
                
            print(f"Agent response: {response_text}")
            
            # Send response back to Telegram
            try:
                if chat_id is not None:
                    await multi_mcp.call_tool("telegram_send_message", {
                        "chat_id": chat_id,
                        "text": response_text
                    })
                    print("Response sent to Telegram")
                else:
                    print("Warning: No chat_id available, can't send response to Telegram")
            except Exception as e:
                error_msg = f"Error sending response to Telegram: {e}"
                print(error_msg)
                # Try to send error message
                try:
                    if chat_id is not None:
                        await multi_mcp.call_tool("telegram_send_message", {
                            "chat_id": chat_id,
                            "text": f"Error: Unable to complete the task. {str(e)}"
                        })
                except:
                    print("Failed to send error message to Telegram")
            
            return response_text
        except Exception as e:
            error_msg = f"Agent execution error: {e}"
            print(error_msg)
            
            # Try to send error message to Telegram
            try:
                if chat_id is not None:
                    await multi_mcp.call_tool("telegram_send_message", {
                        "chat_id": chat_id,
                        "text": f"I encountered an error while processing your request: {str(e)}"
                    })
                    print("Error message sent to Telegram")
                else:
                    print("Warning: No chat_id available, can't send error message to Telegram")
            except Exception as send_error:
                print(f"Failed to send error message to Telegram: {send_error}")
                
            return f"Error processing message: {e}"
    except Exception as e:
        print(f"Critical error in message processing: {e}")
        return f"Critical error: {e}"


async def listen_telegram_events():
    """
    Listen for Telegram events and process them with the agent
    """
    print(f"Connecting to Telegram MCP SSE at {TELEGRAM_MCP_SSE_URL} ...")
    async with sse_client(TELEGRAM_MCP_SSE_URL) as (reader, writer):
        print("Connected. Listening for incoming Telegram messages/events...")
        while True:
            event = await reader.receive()
            if event is None:
                print("Connection closed by server.")
                break
            
            # Print the raw event/message
            print("[EVENT RAW]", event)
            
            # Extract and print just the Telegram message text and chat_id (if present)
            msg_text, chat_id = extract_telegram_data(event)
            if msg_text and not msg_text.startswith("[No text found"):
                print("[TELEGRAM MESSAGE]", msg_text)
                
                # Process the message with our agent
                response = await process_telegram_message(msg_text, chat_id)
                print("[AGENT RESPONSE]", response)
            else:
                print("[NO MESSAGE TEXT FOUND]", msg_text)


if __name__ == "__main__":
    asyncio.run(listen_telegram_events())
