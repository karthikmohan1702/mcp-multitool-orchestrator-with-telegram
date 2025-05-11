from typing import Any, Dict, List, Optional, Union
from .config import GEMINI_ENABLED, GEMINI_API_URL, logger, tool_to_endpoint_map
import requests
import json
import asyncio

# Synchronous Gemini request for use in thread
def _sync_gemini_request(prompt: str) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    logger.debug(f"Entering _sync_gemini_request. Prompt length: {len(prompt)}")
    if not GEMINI_ENABLED or not GEMINI_API_URL:
        logger.warning("Gemini is not enabled/configured, skipping API call.")
        return {"tool_name": None, "direct_answer": "[LLM Disabled]"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    headers = {'Content-Type': 'application/json'}
    logger.info("Sending request to Gemini API for tool decision/plan...")
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=120)
        logger.debug(f"Gemini API response status: {response.status_code}")
        response.raise_for_status()
        json_response = response.json()
        logger.debug(f"Raw Gemini JSON response: {json.dumps(json_response, indent=2)}")
        candidates = json_response.get("candidates", [])
        if not candidates:
            prompt_feedback = json_response.get("promptFeedback")
            if prompt_feedback:
                logger.warning(f"LLM response has no 'candidates'. Prompt Feedback: {prompt_feedback}")
                block_reason = prompt_feedback.get("blockReason", "UNKNOWN")
                return {"tool_name": None, "direct_answer": f"[LLM Error: Request blocked. Reason: {block_reason}]"}
            logger.warning("LLM response has no 'candidates' and no 'promptFeedback'.")
            return {"tool_name": None, "direct_answer": "[LLM Error: No 'candidates']"}
        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "UNKNOWN")
        if finish_reason not in ["STOP", "MAX_TOKENS", "UNKNOWN", "OTHER"]:
            logger.warning(f"Gemini response candidate finished due to: {finish_reason}")
            safety_ratings = candidate.get("safetyRatings", [])
            if safety_ratings: logger.warning(f"  Safety Ratings: {safety_ratings}")
            return {"tool_name": None, "direct_answer": f"[LLM Responded with Finish Reason: {finish_reason}]"}
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts or "text" not in parts[0]:
            logger.warning("LLM response candidate has no 'parts' or 'text' in parts. Finish Reason: %s", finish_reason)
            return {"tool_name": None, "direct_answer": f"[LLM Error: No text part. Reason: {finish_reason}]"}
        raw_text = parts[0].get("text", "").strip()
        logger.info(f"Received raw text response from Gemini: '{raw_text[:200]}{'...' if len(raw_text)>200 else ''}'")
        try:
            cleaned_text = raw_text
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
                if cleaned_text.endswith("```"): cleaned_text = cleaned_text[:-3]
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
                if cleaned_text.endswith("```"): cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
            decision_data = json.loads(cleaned_text)
            if isinstance(decision_data, list):
                if all(isinstance(item, dict) and "tool_name" in item for item in decision_data):
                    logger.info(f"Successfully parsed LLM multi-step plan: {decision_data}")
                    return decision_data
                else:
                    logger.warning(f"LLM returned a list, but items are not valid tool calls: {decision_data}")
                    return {"tool_name": None, "direct_answer": raw_text}
            elif isinstance(decision_data, dict):
                if "tool_name" in decision_data or "direct_answer" in decision_data:
                    logger.info(f"Successfully parsed LLM single decision: {decision_data}")
                    return decision_data
                else:
                    logger.warning(f"LLM response parsed as dict but structure is unexpected: {decision_data}")
                    return {"tool_name": None, "direct_answer": raw_text}
            else:
                logger.warning(f"LLM response was valid JSON but not a list or dict: {type(decision_data)}")
                return {"tool_name": None, "direct_answer": raw_text}
        except json.JSONDecodeError:
            logger.warning(f"LLM response was not valid JSON. Raw text: '{raw_text}'")
            return {"tool_name": None, "direct_answer": raw_text}
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Gemini API HTTP error: {http_err.response.status_code} {http_err.response.text}", exc_info=True)
        return {"tool_name": None, "direct_answer": f"[LLM HTTP Error: {http_err.response.status_code}]"}
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Gemini API request failed (network/timeout): {req_err}", exc_info=True)
        return {"tool_name": None, "direct_answer": f"[LLM Network Error]"}
    except Exception as e:
        logger.error(f"Gemini response processing error: {e}", exc_info=True)
        return {"tool_name": None, "direct_answer": f"[LLM Processing Error]"}

async def ask_llm_for_tool_decision(user_message: str, current_tools_with_meta: List[Dict[str, Any]], history: Optional[list] = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    logger.info("Entering ask_llm_for_tool_decision...")
    if not GEMINI_ENABLED:
        logger.warning("LLM decision skipped: Gemini not enabled.")
        return {"tool_name": None, "direct_answer": "[LLM Disabled]"}
    if not current_tools_with_meta:
        logger.info("No MCP tools available. Asking LLM for direct answer only.")
        prompt = f'''The user sent the following message: "{user_message}"
You have NO external tools available. Provide a helpful direct answer to the user's message based on your internal knowledge.
Respond ONLY with a JSON object containing the answer:
{{"tool_name": null, "direct_answer": "Your helpful answer here"}}'''
    else:
        logger.info(f"Formatting prompt for LLM with {len(current_tools_with_meta)} tools.")
        tool_descriptions = []
        for tool_entry in current_tools_with_meta:
            tool_def = tool_entry["tool_definition"]
            server_name = tool_entry["server_name"]
            tool_name = getattr(tool_def, 'name', 'N/A')
            schema_str = json.dumps(getattr(tool_def, 'inputSchema', {}))
            tool_descriptions.append(
                f"- Tool Name: {tool_name}\n  (From Server: {server_name})\n  Description: {getattr(tool_def, 'description', 'N/A')}\n  Input Schema: {schema_str}"
            )
        tools_context = "\n".join(tool_descriptions)
        history_context = ""
        if history:
            def format_history_item(item):
                item_type = item.get("type", "unknown")
                tool_name = item.get("tool_name", "")
                if item_type == "tool_call":
                    return f"  - Called: {tool_name} with input {str(item.get('input', {})).strip()[:100]}"
                elif item_type == "tool_result":
                    result = item.get("result")
                    raw_result = item.get("raw_result")
                    error_detail = ""
                    if isinstance(raw_result, dict) and raw_result.get("error"):
                        error_detail = f" (Error: {raw_result['error']})"
                    if isinstance(result, list) and all(isinstance(r_item, str) for r_item in result):
                        result_str = f"list of {len(result)} links: {', '.join(result)[:80]}..." if result else "empty list"
                    elif isinstance(result, str):
                        result_str = result[:100].replace('\n', ' ') + ('...' if len(result) > 100 else '')
                    else:
                        result_str = str(result).strip()[:100] + ('...' if len(str(result)) > 100 else '')
                    return f"  - Result from {tool_name}: {result_str}{error_detail}"
                return f"  - Unknown history item: {str(item)[:100]}"
            formatted_history_items = [format_history_item(item) for item in history]
            if formatted_history_items:
                history_context = f"\n\nPrevious actions in this conversation:\n" + "\n".join(formatted_history_items)
        prompt = f'''You are an intelligent agent that can use external tools to answer user queries.
Analyze the user's message, available tools, and conversation history carefully.

User Message: "{user_message}"
{history_context}

Available Tools:
{tools_context}

Your Task:
1. Determine if any tools can help answer the user's message, potentially in multiple steps. The "tool_name" you choose MUST EXACTLY MATCH one from the list.
2. If a single tool is suitable:
   Respond ONLY with a JSON object: {{"tool_name": "exact_tool_name_from_list", "tool_input": {{"argument1": "value1"}}}}
3. If a sequence of tools is needed (e.g., search, then extract from URLs, then summarize and send):
   Respond ONLY with a JSON list of tool call objects, in the order they should be executed.
   Example for a multi-step query "Search IPL standings, get page content, then send to Telegram":
   [
     {{"tool_name": "ddg_search", "tool_input": {{"query": "IPL standings", "max_results": 1}}}},
     {{"tool_name": "extract_text", "tool_input": {{"url": "<url_from_ddg_search_result_1>"}}}},
     {{"tool_name": "telegram_send_message", "tool_input": {{"chat_id": "<user_chat_id>", "text": "<extracted_IPL_standings_text>"}}}}
   ]
   Ensure placeholders like "<url_from_ddg_search_result_1>" or "<user_chat_id>" or "<extracted_IPL_standings_text>" are clearly indicated. The orchestrator will fill these.
   If the user explicitly asks for the response to be sent via Telegram, ensure `telegram_send_message` is the LAST tool in the list.
4. If NO tool is suitable or the message doesn't require a tool for the NEXT step (e.g., if all tools have run and you have the final answer):
   Respond ONLY with a JSON object: {{"tool_name": null, "direct_answer": "Your helpful, direct response."}}

Important Rules:
- Output ONLY the JSON object or list. No other text, explanations, or markdown.
- The "tool_name" MUST be one of the exact names provided.
- Ensure "tool_input" precisely matches the schema for the chosen tool.
- For `telegram_send_message`, use the placeholder "<user_chat_id>".
- For tools taking URLs from previous steps (like `extract_text` after `ddg_search`), use placeholders like "<url_from_ddg_search_result_1>", "<url_from_ddg_search_result_2>", etc. The orchestrator will substitute the actual URLs.
'''
    logger.debug(f"LLM Decision Prompt:\n---START PROMPT---\n{prompt}\n---END PROMPT---")
    try:
        decision = await asyncio.to_thread(_sync_gemini_request, prompt)
        logger.info(f"Received decision back from LLM thread: {decision}")
        if decision is None:
             logger.warning("LLM decision function returned None unexpectedly.")
             return {"tool_name": None, "direct_answer": "[LLM Error: Decision function returned None]"}
        return decision
    except Exception as e:
        logger.error(f"Failed to run LLM decision request in thread: {e}", exc_info=True)
        return {"tool_name": None, "direct_answer": f"[LLM Thread Error: {e}]"}
