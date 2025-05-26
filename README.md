# MCP Multi-Tool Orchestrator with Telegram Integration
Agentic orchestrator for automating workflows across multiple MCP tools—including SerpAPI, Trafilatura, Google Drive/Sheets, and Telegram—featuring LLM-driven planning and seamless Telegram integration. This system demonstrates how to build a fully autonomous agent that can handle complex multi-step tasks by orchestrating various tools through the Model Context Protocol (MCP).

## Video


https://github.com/user-attachments/assets/e469e030-a0c7-464d-bdca-a269718852d5



## Overview

This project is a modular, agentic orchestrator for automating complex, multi-step workflows using a suite of Model Context Protocol (MCP) tools. It leverages LLM-based decision-making (Google Gemini) to dynamically select and sequence tool invocations, enabling advanced automation scenarios such as searching, extracting, writing to Google Sheets, and messaging via Telegram.

The orchestrator is designed to be extensible and robust, supporting the integration of new MCP tools and seamless communication between agents, tools, and external APIs. By using the MCP standard, this system can easily incorporate additional tools without requiring significant architectural changes.

Key capabilities include:
- Processing natural language requests from users via Telegram
- Formulating multi-step plans to fulfill complex requests
- Executing tool calls in the correct sequence with proper parameter handling
- Extracting web content using specialized tools like Trafilatura
- Creating and sharing Google Sheets with structured data
- Maintaining context across multiple steps of execution

---

## Youtube Video

https://youtu.be/vt1GdQ-f8NA

## Features

- **LLM-driven Tool Planning:** Uses Google Gemini to interpret user requests and generate a multi-step plan, expressed as a sequence of MCP tool calls. The system intelligently determines which tools to use and in what order based on the user's request.

- **Multi-Step Tool Orchestration:** The agent plans and executes a sequence of tool calls based on user requests. Each tool is called with arguments constructed from the user's input and the agent's planning logic.

- **Data Flow Between Tools:** Outputs from one tool can be used as inputs for subsequent steps, enabling complex workflows. (Note: Placeholder-style automatic substitution is not currently implemented; argument passing is managed by the agent's planning logic.)

- **Multi-Tool Support:** Integrates multiple specialized tools via their MCP servers:
  - **SerpAPI Search:** For retrieving up-to-date information from the web
  - **Trafilatura Extraction:** For clean extraction of content from web pages
  - **Google Drive/Sheets:** For creating, writing to, and sharing spreadsheets
  - **Telegram Messaging:** For receiving user requests and sending responses

- **Event-Driven & CLI Orchestration:** Supports both event-driven workflows (e.g., listening for Telegram messages) and interactive CLI mode. The agent processes events or user input, plans toolchains, and executes them step by step.

- **Robust Error Handling:** Detects and reports tool errors, validation issues, and connection problems, ensuring graceful degradation. The system can recover from failures and provide meaningful feedback to users.

- **Extensible Modular Architecture:** The codebase is organized into orchestrator, core, and modules subdirectories. Adding new MCP tools or replacing LLMs requires minimal code changes thanks to the modular design. Entry points include both CLI (`agent.py`) and event-driven (`main.py`) modes.

---

## Technology Stack

- **Python 3.11+**: Core programming language with strong async support and extensive libraries.

- **FastMCP** ([jlowin-fastmcp](https://github.com/jlowin/fastmcp)): Model Context Protocol client/server library for standardized tool invocation. Provides a consistent interface for all tool interactions.

- **Google Gemini API:** Advanced LLM for decision-making, planning, and natural language understanding. Used to interpret user requests and generate structured tool execution plans.

- **MCP-compatible Microservices**:
  - **SerpAPI MCP**: For web search capabilities and retrieving current information
  - **Trafilatura MCP**: Specialized web scraping tool for clean content extraction
  - **GDrive MCP**: Interface to Google Drive and Sheets APIs for document creation and management
  - **Telegram MCP**: Messaging platform integration for user interaction

- **Asyncio**: Python's asynchronous I/O framework for efficient concurrent operations without threading complexity.

- **HTTPX**: Modern HTTP client with async support for API interactions.

- **Pydantic**: For data validation and settings management using Python type annotations.

- **Logging**: Comprehensive, structured logging system for debugging, monitoring, and observability.

---

## MCP Servers & Implementation Details

### Communication Protocol

All MCP servers integrated in this project (including SerpAPI, Trafilatura, Google Drive/Sheets, and Telegram) communicate using the **Server-Sent Events (SSE)** protocol. This architecture allows the orchestrator to seamlessly coordinate multiple tools, handle asynchronous responses, and provide users with prompt feedback and results.

### MCP Server Implementation

Each MCP server follows a standardized implementation pattern:

1. **Tool Definition**: Each tool is defined with a name, description, and parameter schema that follows the JSON Schema specification.

2. **Server Implementation**: Each server exposes its tools via a FastMCP-compatible API endpoint that handles incoming requests and returns structured responses.

3. **Client Libraries**: The orchestrator uses client libraries to interact with each MCP server, handling authentication, request formatting, and response parsing.

### Trafilatura MCP Server

The Trafilatura MCP server is particularly important for web content extraction. It provides:

- Clean extraction of main content from web pages
- Removal of boilerplate, navigation, and ads
- Preservation of structural elements (paragraphs, lists, tables)
- Conversion of HTML to plain text or structured formats

This server is crucial for extracting structured data like sports standings, which can then be processed and inserted into Google Sheets.

### Tool Discovery Mechanism

The orchestrator uses a dynamic tool discovery mechanism that:

1. Queries each MCP server for its available tools
2. Builds a comprehensive tool registry
3. Makes all discovered tools available to the LLM for planning

This approach allows new tools to be added to the system without requiring changes to the orchestrator code.

## Usage

### Setup and Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/karthikmohan1702/mcp-multitool-orchestrator-with-telegram.git
   cd mcp-multitool-orchestrator-with-telegram
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root directory with the following variables:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here        # Google Gemini LLM API Key
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token     # Telegram Bot Token for your bot
   TELEGRAM_CHAT_ID=your_telegram_chat_id         # (Optional) Default chat ID for sending messages
   SERP_API_KEY=your_serpapi_key_here             # SerpAPI Key for web search
   ```
   - `GEMINI_API_KEY`: Required for LLM-driven planning and tool selection
   - `TELEGRAM_BOT_TOKEN`: Used by the Telegram MCP to receive and send messages
   - `TELEGRAM_CHAT_ID`: (Optional) Used for targeting a specific chat/user by default
   - `SERP_API_KEY`: Required for the SerpAPI MCP to perform web searches

   The MCP server URLs are configured in your YAML or code, not in `.env` by default. If you wish to override them, add:
   ```env
   SERPAPI_MCP_URL=http://localhost:8050/serpapi_mcp_sse/
   TRAFILATURA_MCP_URL=http://localhost:8030/trafilatura_mcp_sse/
   GDRIVE_MCP_URL=http://localhost:8020/gdrive_mcp_sse/
   TELEGRAM_MCP_URL=http://localhost:8000/telegram_mcp_sse/
   ```

### Running the System

1. **Start All MCP Servers:** Launch each MCP server in a separate terminal:
   ```bash
   # Terminal 1
   python -m serpapi_mcp.server
   
   # Terminal 2
   python -m trafilatura_mcp.server
   
   # Terminal 3
   python -m gdrive_mcp.server
   
   # Terminal 4
   python -m telegram_mcp.server
   ```

2. **Run the Orchestrator:** Start the main orchestrator in another terminal:
   ```bash
   python -m orchestrator.main
   ```

3. **Interact via Telegram:** Send queries to your Telegram bot. Example queries:
   - "Find the current points standings of F1 racers 2024, then put that into a Google Excel sheet and then share the link to this sheet with me on user@example.com on gmail"

4. **Monitor Execution:** The orchestrator provides detailed logs of each step in the process:
   - Tool selection and planning
   - Execution of each tool call
   - Results and error handling
   - Final response generation

---

## File Structure

```
mcp-multitool-orchestrator-with-telegram/
├── orchestrator/
│   ├── __init__.py
│   ├── agent.py              # Main agent entry point
│   ├── main.py               # Main entry point and orchestrator initialization
│   ├── config.py             # Environment config, endpoints, logging setup
│   ├── session.py            # MCP session management
│   ├── core/
│   │   ├── __init__.py
│   │   ├── context.py        # Agent context management
│   │   ├── loop.py           # Main agent loop: LLM planning, tool execution
│   │   ├── session.py        # MCP session handling
│   │   ├── strategy.py       # Strategy for decision making
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── action.py         # MCP tool invocation and function call parsing
│   │   ├── decision.py       # LLM (Gemini) request/response, plan generation
│   │   ├── memory.py         # Memory management for agent context
│   │   ├── perception.py     # Perception handling and extraction
│   │   ├── tools.py          # Tool management and description
│   ├── config/               # Configuration files
├── serpapi_mcp/              # SerpAPI MCP server/client for web search
├── gdrive_mcp/               # Google Drive MCP server/client
├── telegram_mcp/             # Telegram MCP server/client
├── trafilatura_mcp/          # Trafilatura MCP server/client
├── requirements.txt
├── .env
```

---

## Module Breakdown

### Core Components

#### `main.py`
- **Main entry point:** Initializes the orchestrator, sets up event listeners, and handles the main execution flow.
- **handle_telegram_message:** Processes incoming Telegram messages and initializes the agent.
- **listen_telegram_events:** Listens for incoming Telegram events and processes them.

#### `core/loop.py`
- **AgentLoop.run:** The core async loop that processes user messages, queries LLM for a plan, executes tools, and manages the execution flow.
- **AgentLoop.tool_expects_input:** Determines if a tool expects a simple input parameter.

#### `core/context.py`
- **AgentContext:** Manages the agent's context, including session ID, user input, memory, and final answer.

#### `core/session.py`
- **MultiMCP:** Handles connections to multiple MCP servers and provides a unified interface for tool calls.

### Module Components

#### `modules/action.py`
- **parse_function_call:** Parses function calls from text in various formats (parentheses, pipe, JSON).
- **ToolCallResult:** Data class for tool call results.

#### `modules/decision.py`
- **generate_plan:** Formats the prompt, sends it to Gemini, parses the response, and returns a structured tool plan.

#### `modules/perception.py`
- **extract_perception:** Analyzes user input to determine intent and tool hints.
- **PerceptionResult:** Data class for perception results.

#### `modules/memory.py`
- **MemoryItem:** Data class for memory items.
- **MemoryManager:** Manages the agent's memory, including storage and retrieval.

#### `modules/tools.py`
- **summarize_tools:** Creates a summary of available tools for the LLM to use in planning.
- **filter_tools_by_hint:** Filters tools based on a hint from perception.

### MCP Tool Directories
- Each of `serpapi_mcp`, `gdrive_mcp`, `telegram_mcp`, `trafilatura_mcp` contains a FastMCP-compatible server and client for their respective service.

---

## Configuration

- **.env:**  
  - `GEMINI_API_KEY` — Your Google Gemini API key (required for LLM planning).
  - `TELEGRAM_BOT_TOKEN` — Your Telegram bot token.

- **config/profiles.yaml:**
  - Contains MCP server configurations and agent profile settings.
  - Defines connection details for all MCP servers.
  - Configures agent parameters like max steps and memory settings.

- **Tool Discovery:**  
  - The agent automatically discovers all available MCP tools at startup via the MultiMCP class.
  - Tools are dynamically loaded and made available to the LLM for planning.

---

## Example Workflow

### F1 Standings Example

1. **User Message:** "Find the current points standings of F1 racers 2024, then put that into a Google Excel sheet and then share the link to this sheet with me on user@example.com on gmail."

2. **Orchestrator Processing:**
   - The `main.py` receives the message and extracts the text
   - It initializes the `AgentLoop` with the user's message
   - The agent begins processing the request

3. **LLM Planning Process:**
   - The `modules/perception.py` analyzes the user request to identify intent and tools
   - The `modules/decision.py` determines the necessary tools and their sequence
   - It generates a structured plan with specific tool calls

4. **Generated Tool Plan:**
   ```
   FUNCTION_CALL: serpapi_search(query="F1 points standings 2024", max_results=3)
   FUNCTION_CALL: trafilatura_extract(url="https://www.example.com/f1-standings")
   FUNCTION_CALL: gdrive_create_sheet(sheet_name="F1 Standings 2024")
   FUNCTION_CALL: gdrive_write_sheet(sheet_id="abc123", values=[["Driver", "Team", "Points"], ["Verstappen", "Red Bull", 255], ["Hamilton", "Mercedes", 212]])
   FUNCTION_CALL: gdrive_share_file(file_id="abc123", email_address="user@example.com", role="writer")
   ```

5. **Agent Execution:**
   - **Step 1:** `core/loop.py` processes the plan and calls the first tool via `modules/action.py`
     - Searches for F1 standings using SerpAPI MCP
     - Result: Returns search results with URLs to F1 standings pages
   
   - **Step 2:** The agent calls the trafilatura tool to extract content
     - Extracts clean content from the most relevant URL using Trafilatura MCP
     - Result: Clean HTML-free text with structured standings data
   
   - **Step 3:** The agent creates a new Google Sheet
     - Creates a sheet with the specified name via Google Drive MCP
     - Result: Returns a new sheet ID (e.g., "abc123")
   
   - **Step 4:** The agent writes the extracted data to the sheet
     - Formats the data appropriately for a spreadsheet
     - Uses the sheet ID from the previous step
   
   - **Step 5:** The agent shares the Google Sheet
     - Uses the sheet ID from step 3 and shares it with user@example.com
     - Extracts the email from the original request
     - Sets appropriate permissions

6. **Final Response to User:**
   - The agent generates a FINAL_ANSWER with the results
   - `main.py` processes this response
   - The system sends a message back to the user via Telegram
   - The message includes the Google Sheet link and confirmation of sharing

## Conclusion

This project is primarily an exploration of the Model Context Protocol (MCP) and agentic workflows. It serves as a demonstration of how different MCP-compatible tools can be orchestrated together to create a flexible, LLM-driven agent system.

This is not a complete production-ready product, but rather a foundation that you can build upon and customize for your specific use cases. You are encouraged to:

- Add your own MCP servers and tools
- Modify the agent's behavior and capabilities
- Extend the memory and context management systems
- Adapt the architecture to fit your specific requirements

The modular nature of MCP makes it easy to swap components and add new functionality, making this project an excellent starting point for your own agentic systems.


---

