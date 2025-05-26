# modules/action.py

from typing import Dict, Any, Union, Tuple
from dataclasses import dataclass
import ast


@dataclass
class ToolCallResult:
    """Result of a tool call"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    raw_response: Any = None
    error: str = None


def parse_function_call(response: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parses a function call string in various formats:
    1. "FUNCTION_CALL: tool_name(param1="value1", param2="value2")"
    2. "FUNCTION_CALL: tool_name|param1=value1|param2=value2"
    3. "FUNCTION_CALL: {"tool_name": "tool", "parameters": {...}}"
    4. "FUNCTION_CALL: {"tool": "tool_name", "tool_input": {...}}"
    5. "FUNCTION_CALL: {"tool": "tool_name", "query": "...", ...}"
    
    Returns a tuple of (tool_name, arguments_dict)
    """
    import re
    import json
    
    # Clean up the response
    response = response.strip()
    
    # Check if it's a FUNCTION_CALL format
    if response.startswith("FUNCTION_CALL:"):
        
        # Extract everything after the prefix
        function_text = response[len("FUNCTION_CALL:"):].strip()
        
        # Check if it's using the pipe format: tool_name|param1=value1|param2=value2
        if "|" in function_text:
            try:
                parts = [p.strip() for p in function_text.split("|")]
                tool_name, param_parts = parts[0], parts[1:]
                
                args = {}
                for part in param_parts:
                    if "=" not in part:
                        raise ValueError(f"Invalid parameter: {part}")
                    key, val = part.split("=", 1)
                    
                    # Try parsing as literal, fallback to string
                    try:
                        parsed_val = ast.literal_eval(val)
                    except Exception:
                        parsed_val = val.strip()
                    
                    # Support nested keys (e.g., input.value)
                    keys = key.split(".")
                    current = args
                    for k in keys[:-1]:
                        current = current.setdefault(k, {})
                    current[keys[-1]] = parsed_val
                
                print(f"[parser] Parsed: {tool_name} → {args}")
                return tool_name, args
            except Exception as e:
                print(f"[parser] ❌ Parse failed for pipe format: {e}")
                # Fall through to try other formats
        
        # Check if it's using the parentheses format: tool_name(param1="value1", param2="value2")
        match = re.match(r'([\w_]+)\s*\((.*)\)\s*$', function_text)
        if match:
            tool_name = match.group(1).strip()
            args_text = match.group(2).strip()
            
            # Parse the arguments
            args = {}
            if args_text:
                # Split by commas, but respect quotes and nested structures
                param_parts = []
                current_part = ""
                in_quotes = False
                quote_char = None
                paren_level = 0
                bracket_level = 0
                brace_level = 0
                
                for char in args_text:
                    if char in '"\'' and (not in_quotes or quote_char == char):
                        in_quotes = not in_quotes
                        if in_quotes:
                            quote_char = char
                        else:
                            quote_char = None
                        current_part += char
                    elif char == '(' and not in_quotes:
                        paren_level += 1
                        current_part += char
                    elif char == ')' and not in_quotes:
                        paren_level -= 1
                        current_part += char
                    elif char == '[' and not in_quotes:
                        bracket_level += 1
                        current_part += char
                    elif char == ']' and not in_quotes:
                        bracket_level -= 1
                        current_part += char
                    elif char == '{' and not in_quotes:
                        brace_level += 1
                        current_part += char
                    elif char == '}' and not in_quotes:
                        brace_level -= 1
                        current_part += char
                    elif char == ',' and not in_quotes and paren_level == 0 and bracket_level == 0 and brace_level == 0:
                        param_parts.append(current_part.strip())
                        current_part = ""
                    else:
                        current_part += char
                
                if current_part.strip():
                    param_parts.append(current_part.strip())
                
                # Process each parameter
                for part in param_parts:
                    if "=" not in part:
                        continue  # Skip invalid parameters
                    
                    key, val = part.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    
                    # Try parsing as literal, fallback to string
                    try:
                        parsed_val = ast.literal_eval(val)
                    except Exception:
                        # If it's a raw string without quotes, add quotes
                        if not (val.startswith('"') or val.startswith("'")):
                            try:
                                parsed_val = ast.literal_eval(f'"{val}"')
                            except Exception:
                                parsed_val = val
                        else:
                            parsed_val = val
                    
                    args[key] = parsed_val
            
            print(f"[parser] Parsed: {tool_name} → {args}")
            return tool_name, args
    
    # Try to parse as JSON format
    try:
        # Look for JSON-like structure in the response
        json_match = re.search(r'\{.*\}', response)
        if json_match:
            json_str = json_match.group(0)
            data = json.loads(json_str)
            
            # Handle various JSON formats
            if 'tool_name' in data and 'parameters' in data:
                tool_name = data['tool_name']
                args = data['parameters']
            elif 'tool' in data and 'tool_input' in data:
                tool_name = data['tool']
                args = data['tool_input']
            elif 'tool' in data and isinstance(data['tool'], str):
                tool_name = data['tool']
                # Remove the tool key and use the rest as arguments
                args = {k: v for k, v in data.items() if k != 'tool'}
            else:
                raise ValueError(f"Unknown JSON format: {data}")
                
            print(f"[parser] Parsed JSON: {tool_name} → {args}")
            return tool_name, args
    except Exception as e:
        print(f"[parser] ❌ JSON parse failed: {e}")
    
    # If we get here, we couldn't parse the function call
    raise ValueError(f"Could not parse function call from: {response}")

