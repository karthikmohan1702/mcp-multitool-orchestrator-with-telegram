from typing import Any, Dict, List, Union
from .decision import ask_llm_for_tool_decision
from .action import send_telegram_message, call_mcp_tool
from .config import logger
import json
import asyncio
from .config import tool_to_endpoint_map
try:
    from mcp import types as mcp_types
except ImportError:
    mcp_types = None

def json_serializable_default(obj):
    if hasattr(obj, 'model_dump_json') and callable(obj.model_dump_json):
        try:
            return json.loads(obj.model_dump_json())
        except Exception:
            return str(obj)
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    return str(obj)

async def agentic_tool_loop(user_message: str, tools_with_meta: List[Dict[str, Any]], chat_id: Union[str, int], max_steps: int = 6):
    memory: List[Dict[str, Any]] = []
    original_user_query = user_message
    for step in range(max_steps):
        logger.info(f"[AgentLoop] Step {step + 1} of {max_steps} for chat_id={chat_id}")
        current_prompt_message = original_user_query
        llm_decision = await ask_llm_for_tool_decision(current_prompt_message, tools_with_meta, memory)
        logger.info(f"[AgentLoop] LLM decision for step {step + 1}: {llm_decision}")
        if isinstance(llm_decision, dict) and llm_decision.get("direct_answer"):
            logger.info(f"[AgentLoop] LLM provided direct answer: {llm_decision['direct_answer']}")
            await send_telegram_message(chat_id, llm_decision['direct_answer'])
            return
        tool_calls_to_execute: List[Dict[str, Any]] = []
        if isinstance(llm_decision, list):
            tool_calls_to_execute = llm_decision
        elif isinstance(llm_decision, dict) and llm_decision.get("tool_name"):
            tool_calls_to_execute.append(llm_decision)
        else:
            logger.warning(f"[AgentLoop] LLM decision not understood: {llm_decision}")
            await send_telegram_message(chat_id, "[Agent Error: LLM did not provide a valid tool call or answer.]")
            return
        for i, tool_call in enumerate(tool_calls_to_execute):
            tool_name = tool_call.get("tool_name")
            tool_input = tool_call.get("tool_input", {})
            # Placeholder substitution logic (simplified for brevity)
            for key, value in list(tool_input.items()):
                if isinstance(value, str) and value.startswith("<url_from_ddg_search_result_"):
                    ddg_link_list_from_memory = None
                    for mem in reversed(memory):
                        if mem.get("type") == "tool_result" and \
                           mem.get("tool_name") == "ddg_search" and \
                           isinstance(mem.get("result"), list) and \
                           all(isinstance(link_item, str) for link_item in mem.get("result", [])):
                            ddg_link_list_from_memory = mem["result"]
                            break
                    if ddg_link_list_from_memory:
                        all_links = ddg_link_list_from_memory
                        url_index_str = value.split('_')[-1].replace(">", "")
                        url_index = int(url_index_str) - 1
                        if 0 <= url_index < len(all_links):
                            tool_input[key] = all_links[url_index]
                            logger.info(f"Replaced placeholder '{value}' with '{all_links[url_index]}'")
                        else:
                            logger.warning(f"Could not find URL for placeholder: {value}. Index {url_index} out of range for {len(all_links)} links. Links from memory: {all_links}")
                            await send_telegram_message(chat_id, f"[Agent Error: Could not find link for {value}]")
                            return
                    else:
                        logger.warning(f"Placeholder {value} found, but no suitable ddg_search link list results in memory. Memory state: {json.dumps(memory, indent=2, default=json_serializable_default)}")
                        await send_telegram_message(chat_id, f"[Agent Error: No search results found to use for {value}]")
                        return
                elif isinstance(value, str) and value.startswith("<extracted_"):
                    found_text = "No extracted text found for placeholder."
                    for mem_item in reversed(memory):
                        if mem_item.get("type") == "tool_result" and \
                           mem_item.get("tool_name") == "extract_text":
                            if isinstance(mem_item.get("result"), str):
                                found_text = mem_item["result"]
                                logger.info(f"Retrieved text for placeholder '{value}' from '{mem_item.get('tool_name')}' tool result.")
                                break
                            elif isinstance(mem_item.get("result"), list) and mem_item["result"] and hasattr(mem_item["result"][0], 'text'):
                                found_text = mem_item["result"][0].text
                                logger.info(f"Retrieved text for placeholder '{value}' from '{mem_item.get('tool_name')}' tool result (from list).")
                                break
                    if tool_name == "gdrive_write_sheet" and key == "values":
                        if isinstance(found_text, str):
                            lines = found_text.strip().split('\n')
                            processed_values = []
                            for line_idx, line_content in enumerate(lines):
                                if line_content.strip():
                                    cells = [cell.strip() for cell in line_content.split('|')]
                                    processed_values.append(cells)
                            tool_input[key] = processed_values
                            logger.info(f"Processed extracted text (for '{value}') into List[List[str]] for gdrive_write_sheet. {len(processed_values)} rows. First row example: {processed_values[0] if processed_values else 'N/A'}")
                        else:
                            logger.warning(f"Expected string for extracted text (for '{value}') to process for gdrive_write_sheet, but got {type(found_text)}. Using raw value.")
                            tool_input[key] = found_text
                    else:
                        tool_input[key] = found_text
                        logger.info(f"Replaced placeholder '{value}' with extracted text (first 100 chars): '{str(found_text)[:100]}...'")
                # PATCH: Handle <f1_standings_extracted_and_formatted> for gdrive_write_sheet, as in telegram_event_listener.py
                elif (
                    isinstance(value, str)
                    and value in ("<f1_standings_extracted_and_formatted>", "<f1_standings_data>")
                    and tool_name == "gdrive_write_sheet"
                    and key == "values"
                ):
                    standings_text = None
                    for mem_item in reversed(memory):
                        if mem_item.get("type") == "tool_result" and mem_item.get("tool_name") == "extract_text":
                            standings_text = mem_item.get("result")
                            break
                    if standings_text:
                        parsed_values = []
                        for line in standings_text.strip().split('\n'):
                            if line.strip():
                                cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                                if cells:
                                    parsed_values.append(cells)
                        tool_input[key] = parsed_values
                        logger.info(f"Parsed standings for gdrive_write_sheet: {parsed_values[:2]}...")  # Show first 2 rows
                    else:
                        logger.warning("Could not find extracted standings text in memory for placeholder replacement.")
                        tool_input[key] = []
                elif isinstance(value, str) and (value == "<sheet_id_from_gdrive_create_sheet>" or value == "<file_id_from_gdrive_create_sheet>"):
                    sheet_id_from_memory = "No sheet_id found in memory"
                    for mem_item in reversed(memory):
                        if mem_item.get("type") == "tool_result" and \
                           mem_item.get("tool_name") == "gdrive_create_sheet" and \
                           isinstance(mem_item.get("result"), dict) and \
                           mem_item["result"].get("sheet_id"):
                            sheet_id_from_memory = mem_item["result"]["sheet_id"]
                            break
                    if sheet_id_from_memory == "No sheet_id found in memory":
                        logger.warning(f"Could not find sheet_id for placeholder {value}. Memory: {memory}")
                        await send_telegram_message(chat_id, "[Agent Error: Could not find previously created sheet ID.]")
                        return
                    tool_input[key] = sheet_id_from_memory
                    logger.info(f"Replaced placeholder '{value}' with sheet_id: '{sheet_id_from_memory}'")
            logger.info(f"[AgentLoop] Executing tool: '{tool_name}' with input: {tool_input}")
            memory.append({"type": "tool_call", "tool_name": tool_name, "input": tool_input})
            raw_tool_output = await call_mcp_tool(tool_name, tool_input)
            processed_result_for_memory = raw_tool_output
            if tool_name == "ddg_search":
                if mcp_types and isinstance(raw_tool_output, list) and raw_tool_output and isinstance(raw_tool_output[0], mcp_types.TextContent):
                    links = []
                    for content_item in raw_tool_output:
                        if hasattr(content_item, 'text') and content_item.text:
                            try:
                                search_item_dict = json.loads(content_item.text)
                                if isinstance(search_item_dict, dict) and search_item_dict.get("link"):
                                    links.append(search_item_dict["link"])
                            except json.JSONDecodeError:
                                logger.warning(f"Could not parse ddg_search item text as JSON: {content_item.text}")
                    processed_result_for_memory = links
                    logger.info(f"Processed ddg_search result for memory (list of links): {processed_result_for_memory}")
                elif isinstance(raw_tool_output, dict) and raw_tool_output.get("error"):
                    processed_result_for_memory = raw_tool_output
                else:
                    logger.warning(f"ddg_search result was not in expected format (List[TextContent]): {raw_tool_output}")
            elif tool_name == "extract_text":
                if mcp_types and isinstance(raw_tool_output, list) and raw_tool_output and isinstance(raw_tool_output[0], mcp_types.TextContent):
                    processed_result_for_memory = raw_tool_output[0].text
                elif isinstance(raw_tool_output, str):
                    processed_result_for_memory = raw_tool_output
                elif isinstance(raw_tool_output, dict) and raw_tool_output.get("error"):
                    processed_result_for_memory = raw_tool_output
                else:
                    logger.warning(f"extract_text result in unexpected format: {raw_tool_output}")
            elif tool_name.startswith("gdrive_") and mcp_types and isinstance(raw_tool_output, list) and raw_tool_output and isinstance(raw_tool_output[0], mcp_types.TextContent):
                try:
                    processed_result_for_memory = json.loads(raw_tool_output[0].text)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"{tool_name} result could not be parsed as JSON from TextContent: {raw_tool_output[0].text}")
                    processed_result_for_memory = raw_tool_output[0].text
            elif mcp_types and isinstance(raw_tool_output, list) and raw_tool_output and hasattr(raw_tool_output[0], 'text') and isinstance(raw_tool_output[0], mcp_types.TextContent):
                processed_result_for_memory = raw_tool_output[0].text
            processed_result_str = str(processed_result_for_memory)
            logger.info(f"[AgentLoop] Tool '{tool_name}' result (processed for memory): {processed_result_str[:200]}{'...' if len(processed_result_str) > 200 else ''}")
            memory.append({"type": "tool_result", "tool_name": tool_name, "result": processed_result_for_memory, "raw_result": raw_tool_output})
            if isinstance(raw_tool_output, dict) and raw_tool_output.get("error"):
                logger.error(f"[AgentLoop] Error from tool '{tool_name}': {raw_tool_output['error']}. Stopping current plan execution.")
                if tool_name != "telegram_send_message":
                    await send_telegram_message(chat_id, f"An error occurred with tool {tool_name}: {raw_tool_output['error']}")
                return
            if tool_name == "telegram_send_message":
                logger.info(f"[AgentLoop] 'telegram_send_message' was called. Assuming this segment of plan is complete.")
                if i == len(tool_calls_to_execute) - 1:
                    return
    logger.warning(f"[AgentLoop] Max steps ({max_steps}) reached for chat_id={chat_id}.")
    final_words = "I've reached the maximum processing steps for your request."
    if memory and memory[-1].get("type") == "tool_result" and \
       not (isinstance(memory[-1].get("raw_result"), dict) and memory[-1]["raw_result"].get("error")):
        last_res = memory[-1]['result']
        final_words += f" Here's the last information I have: {str(last_res)[:200]}"
    await send_telegram_message(chat_id, final_words)
