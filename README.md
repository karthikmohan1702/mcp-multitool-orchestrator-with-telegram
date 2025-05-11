# MCP Multi-Tool Orchestrator with Telegram Integration
Agentic orchestrator for automating workflows across multiple MCP tools—including DuckDuckGo, Trafilatura, Google Drive/Sheets, and Telegram—featuring LLM-driven planning and seamless Telegram integration.

## Overview

This project is a modular, agentic orchestrator for automating complex, multi-step workflows using a suite of Model Context Protocol (MCP) tools. It leverages LLM-based decision-making (Google Gemini) to dynamically select and sequence tool invocations, enabling advanced automation scenarios such as searching, extracting, writing to Google Sheets, and messaging via Telegram.

The orchestrator is designed to be extensible and robust, supporting the integration of new MCP tools and seamless communication between agents, tools, and external APIs.

---

## Features

- **LLM-driven Tool Planning:** Uses Google Gemini to interpret user requests and generate a multi-step plan, expressed as a sequence of MCP tool calls.
- **Dynamic Placeholder Resolution:** Automatically substitutes placeholders in tool arguments with results from previous steps (e.g., URLs, extracted text, IDs).
- **Multi-Tool Support:** Integrates DuckDuckGo search, Trafilatura extraction, Google Drive/Sheets, and Telegram messaging via their respective MCP servers.
- **Event-Driven Orchestration:** Listens to incoming events/messages (e.g., from Telegram), processes them in a loop, and executes the planned toolchain.
- **Robust Error Handling:** Detects and reports tool errors, validation issues, and connection problems, ensuring graceful degradation.
- **Extensible Architecture:** Easily add new MCP tools or replace LLMs with minimal code changes.

---

## Technology Stack

- **Python 3.11+**
- **FastMCP** ([jlowin-fastmcp](https://github.com/jlowin/fastmcp)): Model Context Protocol client/server library for tool invocation.
- **Google Gemini API:** For LLM-based decision-making and planning.
- **DuckDuckGo MCP, Trafilatura MCP, GDrive MCP, Telegram MCP:** Custom or open-source MCP-compatible microservices.
- **Asyncio, HTTPX:** For asynchronous event and network handling.
- **Logging:** Centralized, structured logging for observability.

---

## MCP Servers & SSE Protocol

All MCP servers integrated in this project (including DuckDuckGo, Trafilatura, Google Drive/Sheets, and Telegram) communicate using the **Server-Sent Events (SSE)** protocol.

This architecture allows the orchestrator to seamlessly coordinate multiple tools, handle asynchronous responses, and provide users with prompt feedback and results.

## Usage

1. **Start All MCP Servers:** Launch DuckDuckGo, Trafilatura, GDrive, and Telegram MCP servers as separate processes (see their respective directories).
2. **Configure Environment:** Set up `.env` with your Gemini API key and Telegram bot token.
3. **Run the Orchestrator:** Start the main orchestrator listener:
   ```bash
   python -m orchestrator.main
   ```
4. **Interact via Telegram:** Send queries to your Telegram bot (configured in `.env`). The orchestrator will process, plan, and execute the workflow, sending results back to you.
5. **Observe Logs:** Check the console or log files for detailed step-by-step execution and troubleshooting.

---

## File Structure

```
Session_8/
├── orchestrator/
│   ├── __init__.py
│   ├── action.py             # MCP tool invocation and Telegram message sending
│   ├── agent_loop.py         # Main agent loop: LLM planning, tool execution, placeholder resolution
│   ├── config.py             # Environment config, endpoints, logging setup
│   ├── decision.py           # LLM (Gemini) request/response, plan parsing
│   ├── main.py               # Entrypoint: tool discovery, event loop
│   ├── perception.py         # Tool discovery, event listener, notification handler
├── duckduckgo_mcp/           # DuckDuckGo MCP server/client
├── gdrive_mcp/               # Google Drive MCP server/client
├── telegram_mcp/             # Telegram MCP server/client
├── trafilatura_mcp/          # Trafilatura MCP server/client
├── requirements.txt
├── .env
```

---

## Module Breakdown

### `orchestrator/agent_loop.py`
- **agentic_tool_loop:** The core async loop that receives user messages, queries LLM for a tool plan, executes each tool in order, and manages memory/context for placeholder resolution.

### `orchestrator/action.py`
- **call_mcp_tool:** Invokes a specific MCP tool using FastMCP client, handling all exceptions and logging.
- **send_telegram_message:** Sends messages via the Telegram MCP tool.

### `orchestrator/decision.py`
- **ask_llm_for_tool_decision:** Formats the prompt, sends it to Gemini, parses the response, and returns a structured tool plan.
- **_sync_gemini_request:** Synchronous Gemini API call (run in thread).

### `orchestrator/perception.py`
- **discover_mcp_tools:** Discovers all available MCP tools from configured endpoints.
- **handle_notification:** Handles incoming events/messages and invokes the agent loop.
- **listen_to_source_sse:** Listens to the source SSE endpoint for new events.

### `orchestrator/config.py`
- Centralizes all configuration: endpoints, logging, environment variables, and tool-to-endpoint mapping.

### MCP Tool Directories
- Each of `duckduckgo_mcp`, `gdrive_mcp`, `telegram_mcp`, `trafilatura_mcp` contains a FastMCP-compatible server and client for their respective service.

---

## Configuration

- **.env:**  
  - `GEMINI_API_KEY` — Your Google Gemini API key (required for LLM planning).
  - `TELEGRAM_BOT_TOKEN` — Your Telegram bot token.
- **Endpoints:**  
  - All MCP endpoints are configurable via environment variables in `config.py`.
- **Tool Discovery:**  
  - The orchestrator will auto-discover all available MCP tools at startup.

---

## Example Workflow

1. **User Message:** "Find the current F1 standings and put them in a Google Sheet, then share the link on Telegram."
2. **LLM Plan:**  
   - Search F1 standings (DuckDuckGo MCP)
   - Extract standings table (Trafilatura MCP)
   - Create Google Sheet (GDrive MCP)
   - Write standings to sheet (GDrive MCP)
   - Share sheet link via Telegram (Telegram MCP)
3. **Orchestrator:** Executes each step, resolves placeholders, and sends the final message.

---

