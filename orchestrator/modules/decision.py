# modules/decision.py

import os
import aiohttp
import json
import datetime
from typing import List, Dict, Any, Optional
from modules.perception import PerceptionResult
from modules.memory import MemoryItem


def log(stage: str, msg: str):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")





async def generate_plan(
    perception: PerceptionResult,
    memory_items: List[MemoryItem],
    tool_descriptions: Optional[str] = None,
    step_num: int = 1,
    max_steps: int = 10
) -> str:
    """
    Generate a plan for the next action based on perception and memory using Gemini 2.0 Flash
    """
    try:
        # Get Gemini API key from environment
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            log("decision", "⚠️ No Gemini API key found in environment")
            return "FINAL_ANSWER: Could not generate a plan due to missing API key."
        
        # Format memory items
        memory_texts = "\n".join(f"- {m.text}" for m in memory_items) or "None"
        tool_context = f"\nYou have access to the following tools:\n{tool_descriptions}" if tool_descriptions else ""
        
        # Prepare the prompt
        prompt = f"""
        You are a reasoning-driven AI agent with access to tools and memory.
        Your job is to solve the user's request step-by-step by reasoning through the problem, selecting a tool if needed, and continuing until the FINAL_ANSWER is produced.

        Respond in **exactly one line** using one of the following formats:

        - FUNCTION_CALL: tool_name(param1="value1", param2="value2")
        - FINAL_ANSWER: [your final result] *(Not description, but actual final answer)

        🧠 Context:
        - Step: {step_num} of {max_steps}
        - Memory: 
        {memory_texts}
        {tool_context}

        🎯 Input Summary:
        - User input: "{perception.user_input if hasattr(perception, 'user_input') else ''}" 
        - Intent: {perception.intent}
        - Tool hint: {perception.tool_hint or 'None'}

        ✅ EXACT TOOL FORMATS (FOLLOW THESE PRECISELY):
        - FUNCTION_CALL: serpapi_search(query="IPL standings", max_results=3)
        - FUNCTION_CALL: trafilatura_extract(url="https://example.com/some-page")
        - FUNCTION_CALL: gdrive_create_sheet(sheet_name="IPL Standings 2025")
        - FUNCTION_CALL: gdrive_write_sheet(sheet_id="abc123", values=[["Team", "Matches", "Points"]], range_name="Sheet1!A1")
        - FUNCTION_CALL: gdrive_share_file(file_id="abc123", email_address="<user specified email address in user query>", role="writer")
        - FINAL_ANSWER: I've created a Google Sheet with the IPL standings and shared it with you at <user specified email address in user query>. Here's the link: https://docs.google.com/spreadsheets/d/abc123/edit
        
        
        ✅ EXAMPLE WORKFLOW:
        1. FUNCTION_CALL: serpapi_search(query="IPL standings 2025", max_results=3)
        2. FUNCTION_CALL: trafilatura_extract(url="https://example.com/ipl-standings")
        3. FUNCTION_CALL: gdrive_create_sheet(sheet_name="IPL Standings 2025")
        4. FUNCTION_CALL: gdrive_write_sheet(sheet_id="abc123", values=[["Team", "Matches", "Points"]], range_name="Sheet1!A1")
        5. FUNCTION_CALL: gdrive_share_file(file_id="abc123", email_address="<user specified email address in user query>", role="writer")
        6. FINAL_ANSWER: I've created a Google Sheet with the IPL standings and shared it with you at <user specified email address in user query>. Here's the link: https://docs.google.com/spreadsheets/d/abc123/edit

        ---

        💯 IMPORTANT Rules:

        - 🚫 Use only the tools available in the system.
        - 📧 ALWAYS extract email addresses from the user's query when sharing Google Sheets.
        - 📤 SHARING: ALWAYS use gdrive_share_file after creating and writing to a Google Sheet when the user wants to share it.
        - 💡 WEB SCRAPING: Try trafilatura_extract first for clean content extraction.
        - ⚠️ PARAMETERS: Use the exact parameter names shown in the examples above.
        - ⏳ Return FINAL_ANSWER only when you've completed ALL parts of the user's request.
        
        Now, determine the next action:
        """
        
        # Call Gemini API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                }
            ) as response:
                if response.status != 200:
                    log("decision", f"⚠️ Gemini API error: {response.status}")
                    return "FINAL_ANSWER: Could not generate a plan due to API error."
                
                result = await response.json()
                # Extract content from Gemini response format
                raw = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                raw = raw.strip()
                log("plan", f"LLM output: {raw}")
                
                # Extract the function call or final answer from the response
                for line in raw.splitlines():
                    if line.strip().startswith("FUNCTION_CALL:") or line.strip().startswith("FINAL_ANSWER:"):
                        return line.strip()
                
                # If no valid response format was found, return a default
                return "FINAL_ANSWER: [no result]"
    
    except Exception as e:
        log("decision", f"⚠️ Error generating plan: {e}")
        return "FINAL_ANSWER: Could not generate a plan due to an error."
