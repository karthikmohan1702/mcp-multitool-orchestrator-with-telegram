# modules/perception.py

from typing import Optional, Dict, Any, List, Tuple
import json
import os
import re
import aiohttp
from dataclasses import dataclass


def enhance_tool_hints(query: str, tool_hint: Optional[str] = None) -> str:
    """
    Pass through the tool hint without modification.
    The LLM will determine the appropriate tools based on the query and available tool descriptions.
    
    Args:
        query: The user query
        tool_hint: Existing tool hint (if any)
    
    Returns:
        The original tool hint
    """
    return tool_hint or ""


def get_intent_and_tools_from_patterns(query: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Simple fallback function that returns a generic intent and no tool hints.
    The actual intent and tool selection will be determined by the LLM.
    
    Args:
        query: The user query
    
    Returns:
        Tuple of (intent, tools)
    """
    # Return a generic intent and no specific tools
    # Let the LLM determine the appropriate tools based on the query
    return "Process user request", None


@dataclass
class PerceptionResult:
    """
    Represents the agent's understanding of a user query
    """
    intent: str
    tool_hint: Optional[str] = None
    entities: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    

async def extract_perception(query: str) -> PerceptionResult:
    """
    Extract intent, entities, and tool hints from a user query using Gemini 2.0 Flash
    """
    try:
        # Get Gemini API key from environment
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("[perception] ⚠️ No Gemini API key found in environment")
            return PerceptionResult(
                intent="unknown",
                tool_hint=None,
                confidence=0.0
            )
        
        # Prepare the prompt
        prompt = """
        Analyze the user query to extract intent and relevant entities.
        Determine what the user is trying to accomplish and which tool might be useful.
        
        Return a JSON object with the following fields:
        - intent: A brief description of what the user is trying to accomplish
        - tool_hint: A comma-separated list of tools that might be useful (search, web_reader, telegram, gdrive, gmail)
        - entities: Any relevant entities mentioned in the query (optional)
        - confidence: Your confidence in your analysis (0.0 to 1.0)
        
        For multi-step tasks, make sure to include ALL necessary tools in the tool_hint field.
        For example, if the user wants to search for information, create a Google Sheet, and share it,
        include "search, gdrive" in the tool_hint field.
        
        If the user mentions sharing a Google Sheet with an email, ALWAYS include "gdrive" in the tool_hint.
        
        User query: {query}
        """.format(query=query)
        
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
                    print(f"[perception] ⚠️ Gemini API error: {response.status}")
                    return PerceptionResult(
                        intent="unknown",
                        tool_hint=None,
                        confidence=0.0
                    )
                
                result = await response.json()
                # Extract content from Gemini response format
                content = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                
                # Parse the JSON response
                try:
                    # Find JSON in the response (it might be wrapped in markdown code blocks)
                    json_start = content.find('{')
                    json_end = content.rfind('}')
                    if json_start >= 0 and json_end >= 0:
                        json_str = content[json_start:json_end+1]
                        perception_data = json.loads(json_str)
                    else:
                        # Try to extract structured information even if JSON parsing fails
                        print(f"[perception] ⚠️ No JSON found, trying to extract structured information")
                        
                        # Use pattern matching to determine intent and tools
                        intent, tool_hint = get_intent_and_tools_from_patterns(query)
                        
                        if intent or tool_hint:
                            return PerceptionResult(
                                intent=intent or "Process user request",
                                tool_hint=tool_hint,
                                entities=None,
                                confidence=0.7
                            )
                        else:
                            raise json.JSONDecodeError("No structured information found", content, 0)
                    
                    # If we have valid JSON data, create the PerceptionResult
                    intent = perception_data.get("intent", "unknown")
                    tool_hint = perception_data.get("tool_hint")
                    
                    # Use pattern matching to enhance tool hints based on query
                    tool_hint = enhance_tool_hints(query, tool_hint)
                    
                    return PerceptionResult(
                        intent=intent,
                        tool_hint=tool_hint,
                        entities=perception_data.get("entities"),
                        confidence=perception_data.get("confidence", 1.0)
                    )
                except json.JSONDecodeError as e:
                    print(f"[perception] ⚠️ Failed to parse JSON response: {e}")
                    print(f"[perception] Raw content: {content}")
                    
                    # Use pattern matching for fallback perception
                    intent, tools = get_intent_and_tools_from_patterns(query)
                    
                    if intent and tools:
                        return PerceptionResult(
                            intent=intent,
                            tool_hint=tools,
                            confidence=0.8
                        )
                    
                    return PerceptionResult(
                        intent="Process user request",
                        tool_hint=None,
                        confidence=0.5
                    )
    
    except Exception as e:
        print(f"[perception] ⚠️ Error extracting perception: {e}")
        return PerceptionResult(
            intent="unknown",
            tool_hint=None,
            confidence=0.0
        )
