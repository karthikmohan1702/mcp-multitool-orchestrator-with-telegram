# modules/tools.py

from typing import List, Any, Dict, Optional


def summarize_tools(tools: List[Any]) -> str:
    """
    Create a summary of available tools for the LLM to use in planning
    """
    if not tools:
        return "No tools available."
    
    tool_descriptions = []
    for tool in tools:
        name = getattr(tool, "name", "unknown")
        description = getattr(tool, "description", "No description available.")
        
        # Extract parameters
        parameters = getattr(tool, "parameters", {})
        param_descriptions = []
        example_params = []
        
        for param_name, param_info in parameters.items():
            param_type = param_info.get("type", "any")
            param_desc = param_info.get("description", "No description.")
            param_descriptions.append(f"- {param_name} ({param_type}): {param_desc}")
            
            # Create example parameter value based on type
            if param_type == "string":
                example_params.append(f'{param_name}="example value"')
            elif param_type == "integer" or param_type == "number":
                example_params.append(f'{param_name}=1')
            elif param_type == "boolean":
                example_params.append(f'{param_name}=true')
            elif param_type == "array":
                example_params.append(f'{param_name}=["item1", "item2"]')
            elif param_type == "object":
                example_params.append(f'{param_name}={{"key": "value"}}') 
            else:
                example_params.append(f'{param_name}="value"')
        
        # Format the tool description
        tool_desc = f"## {name}\n{description}\n"
        
        if param_descriptions:
            tool_desc += "\nParameters:\n" + "\n".join(param_descriptions)
            
            # Add example calls in multiple formats
            example_call1 = f"FUNCTION_CALL: {name}({', '.join(example_params)})"
            
            # Create pipe format example using a simpler approach
            pipe_params = []
            for param in example_params:
                parts = param.split('=', 1)
                name = parts[0]
                value = parts[1]
                
                # Handle different value types
                if value.startswith('"') and value.endswith('"'):
                    # For string values, remove the quotes
                    clean_value = value[1:-1]  # Remove first and last character (quotes)
                    pipe_params.append(f"{name}={clean_value}")
                else:
                    pipe_params.append(f"{name}={value}")
            example_call2 = f"FUNCTION_CALL: {name}|{' | '.join(pipe_params)}"
            
            # Create JSON format example
            json_params = {}
            for param in example_params:
                param_parts = param.split('=', 1)
                param_name = param_parts[0]
                param_value = param_parts[1]
                try:
                    # Try to evaluate the value as Python literal
                    import ast
                    param_value = ast.literal_eval(param_value)
                except:
                    # If it fails, keep as string
                    pass
                json_params[param_name] = param_value
                
            import json
            json_str = json.dumps({"tool_name": name, "parameters": json_params})
            example_call3 = f'FUNCTION_CALL: {json_str}'
            
            tool_desc += f"\n\nExample calls (use EXACTLY one of these formats):\n1. {example_call1}\n2. {example_call2}\n3. {example_call3}"
        
        tool_descriptions.append(tool_desc)
    
    return "\n\n".join(tool_descriptions)


def filter_tools_by_hint(tools: List[Any], hint: Optional[str] = None) -> List[Any]:
    """
    Filter tools based on a hint
    """
    if not hint:
        return tools
    
    hint = hint.lower()
    filtered_tools = []
    
    for tool in tools:
        name = getattr(tool, "name", "").lower()
        description = getattr(tool, "description", "").lower()
        
        # Check if the hint is in the name or description
        if hint in name or hint in description:
            filtered_tools.append(tool)
    
    # If no tools match the hint, return all tools
    return filtered_tools if filtered_tools else tools


def format_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Format a tool call for the LLM to use in planning
    """
    args_str = ", ".join([f'"{k}": "{v}"' if isinstance(v, str) else f'"{k}": {v}' for k, v in arguments.items()])
    return f'FUNCTION_CALL({tool_name}, {{{args_str}}})'
