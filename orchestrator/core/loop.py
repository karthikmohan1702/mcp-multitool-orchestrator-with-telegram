# core/loop.py

import asyncio
import json
from core.context import AgentContext
from core.session import MultiMCP
from core.strategy import decide_next_action

# We'll implement these modules later
from modules.perception import extract_perception, PerceptionResult
from modules.action import ToolCallResult, parse_function_call
from modules.memory import MemoryItem


class AgentLoop:
    """
    Main execution loop for the agent
    """
    def __init__(self, user_input: str, dispatcher: MultiMCP):
        self.context = AgentContext(user_input)
        self.mcp = dispatcher
        self.tools = dispatcher.get_all_tools()
        # We don't use task patterns or step-to-tool mappings anymore
        # Instead, we let the LLM determine the appropriate tools based on the context

    def get_task_requirements(self, user_input: str) -> dict:
        """
        Determine the task requirements based on the user input.
        Returns a dictionary of step names and whether they are required.
        """
        # Let the LLM determine the requirements based on the user input
        # This avoids hardcoding specific task patterns and requirements
        return {}
    
    def get_completed_steps(self, memories):
        """
        Determine which steps have been completed based on the memory items.
        Returns a set of completed tool names.
        """
        completed_tools = set()
        
        for memory in memories:
            if hasattr(memory, 'tool_name'):
                completed_tools.add(memory.tool_name)
        
        return completed_tools
    
    def get_next_prompt(self, user_input, completed_tools):
        """
        Generate a prompt for the next step based on the user input and completed tools.
        This approach lets the LLM determine the next appropriate action.
        """
        # Create a context about what's been done so far
        completed_context = ""
        if completed_tools:
            completed_context = "\n\nYou have already used these tools: " + ", ".join(completed_tools)
        
        # Let the LLM decide what to do next based on the task and what's been done
        return f"Original user task: {user_input}{completed_context}\n\nWhat is the next step to complete this task? Return a FUNCTION_CALL to the appropriate tool."

    def tool_expects_input(self, tool_name: str) -> bool:
        """Check if a tool expects a simple 'input' parameter"""
        tool = next((t for t in self.tools if getattr(t, "name", None) == tool_name), None)
        if not tool:
            return False
        parameters = getattr(tool, "parameters", {})
        return list(parameters.keys()) == ["input"]

    async def run(self) -> str:
        """
        Run the agent loop until a final answer is reached or max steps are exceeded
        """
        print(f"[agent] Starting session: {self.context.session_id}")

        try:
            max_steps = self.context.agent_profile.max_steps
            query = self.context.user_input

            for step in range(max_steps):
                self.context.step = step
                print(f"[loop] Step {step + 1} of {max_steps}")

                # 🧠 Perception
                perception_raw = await extract_perception(query)

                # ✅ Exit cleanly on FINAL_ANSWER
                # ✅ Handle string outputs safely before trying to parse
                if isinstance(perception_raw, str):
                    pr_str = perception_raw.strip()
                    
                    # Clean exit if it's a FINAL_ANSWER
                    if pr_str.startswith("FINAL_ANSWER:"):
                        self.context.final_answer = pr_str
                        break

                    # Detect LLM echoing the prompt
                    if "Your last tool produced this result" in pr_str or "Original user task:" in pr_str:
                        print("[perception] ⚠️ LLM likely echoed prompt. No actionable plan.")
                        self.context.final_answer = "FINAL_ANSWER: [no result]"
                        break

                    # Try to decode stringified JSON if it looks valid
                    try:
                        perception_raw = json.loads(pr_str)
                    except json.JSONDecodeError:
                        print("[perception] ⚠️ LLM response was neither valid JSON nor actionable text.")
                        self.context.final_answer = "FINAL_ANSWER: [no result]"
                        break

                # ✅ Try parsing PerceptionResult
                if isinstance(perception_raw, PerceptionResult):
                    perception = perception_raw
                else:
                    try:
                        # Attempt to parse stringified JSON if needed
                        if isinstance(perception_raw, str):
                            perception_raw = json.loads(perception_raw)
                        perception = PerceptionResult(**perception_raw)
                    except Exception as e:
                        print(f"[perception] ⚠️ LLM perception failed: {e}")
                        print(f"[perception] Raw output: {perception_raw}")
                        break

                print(f"[perception] Intent: {perception.intent}, Hint: {perception.tool_hint}")

                # 💾 Memory Retrieval
                retrieved = self.context.memory.retrieve(
                    query=query,
                    top_k=self.context.agent_profile.memory_config["top_k"],
                    type_filter=self.context.agent_profile.memory_config.get("type_filter", None),
                    session_filter=self.context.session_id
                )
                print(f"[memory] Retrieved {len(retrieved)} memories")

                # 📊 Planning (via strategy)
                plan = await decide_next_action(
                    context=self.context,
                    perception=perception,
                    memory_items=retrieved,
                    all_tools=self.tools
                )
                print(f"[plan] {plan}")

                if "FINAL_ANSWER:" in plan:
                    # For multi-step tasks, check if we need to do more before allowing a final answer
                    # Get the tools that have been used so far
                    completed_tools = self.get_completed_steps(self.context.memory.memories)
                    
                    # Let the LLM decide if more steps are needed
                    # This avoids hardcoding specific tool names or task types
                    final_lines = [line for line in plan.splitlines() if line.strip().startswith("FINAL_ANSWER:")]
                    if final_lines:
                        self.context.final_answer = final_lines[-1].strip()
                    else:
                        self.context.final_answer = "FINAL_ANSWER: [result found, but could not extract]"
                    break

                # Check for backtick-enclosed JSON function calls
                if "```" in plan and ("tool_code" in plan or "json" in plan):
                    print(f"[loop] Detected backtick-enclosed function call format")
                    # We'll let parse_function_call handle this format
                
                # ⚙️ Tool Execution
                try:
                    tool_name, arguments = parse_function_call(plan)

                    if self.tool_expects_input(tool_name):
                        tool_input = {'input': arguments} if not (isinstance(arguments, dict) and 'input' in arguments) else arguments
                    else:
                        tool_input = arguments

                    try:
                        response = await self.mcp.call_tool(tool_name, tool_input)
                        
                        # ✅ Safe TextContent parsing
                        raw = getattr(response.content, 'text', str(response.content))
                        try:
                            result_obj = json.loads(raw) if raw.strip().startswith("{") else raw
                        except json.JSONDecodeError:
                            result_obj = raw

                        result_str = result_obj.get("markdown") if isinstance(result_obj, dict) else str(result_obj)
                        print(f"[action] {tool_name} → {result_str}")

                        # 🧠 Add memory
                        memory_item = MemoryItem(
                            text=f"{tool_name}({arguments}) → {result_str}",
                            type="tool_output",
                            tool_name=tool_name,
                            user_query=query,
                            tags=[tool_name],
                            session_id=self.context.session_id
                        )
                        self.context.add_memory(memory_item)

                        # 🔁 Next query
                        query = f"""Original user task: {self.context.user_input}

Your last tool produced this result:

{result_str}

If this fully answers the task, return:
FINAL_ANSWER: your answer

Otherwise, return the next FUNCTION_CALL."""
                    except Exception as tool_error:
                        print(f"[error] Tool execution error: {tool_error}")
                        error_message = f"Error executing {tool_name}: {str(tool_error)}"
                        
                        # Add error to memory
                        memory_item = MemoryItem(
                            text=f"{tool_name}({arguments}) → ERROR: {error_message}",
                            type="tool_error",
                            tool_name=tool_name,
                            user_query=query,
                            tags=[tool_name, "error"],
                            session_id=self.context.session_id
                        )
                        self.context.add_memory(memory_item)
                        
                        # Continue with error feedback to the LLM
                        query = f"""Original user task: {self.context.user_input}

Your last tool call to {tool_name} failed with error: {error_message}

Please try a different approach or tool. Return the next FUNCTION_CALL or FINAL_ANSWER if you cannot proceed."""
                        continue  # Continue to next step instead of breaking
                except Exception as e:
                    print(f"[error] Function parsing failed: {e}")
                    self.context.final_answer = f"FINAL_ANSWER: I encountered an error while processing your request: {str(e)}"
                    break

        except Exception as e:
            print(f"[agent] Session failed: {e}")

        return self.context.final_answer or "FINAL_ANSWER: [no result]"
