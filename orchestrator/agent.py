# agent.py

import asyncio
import yaml
import os
from core.loop import AgentLoop
from core.session import MultiMCP
from core.context import AgentProfile


def log(stage: str, msg: str):
    """Simple timestamped console logger."""
    import datetime
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")


async def main():
    print("🧠 Telegram Agent Ready")
    user_input = input("🧑 What do you want to solve today? → ")

    # Load MCP server configs from profiles.yaml
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "profiles.yaml")
    
    with open(config_path, "r") as f:
        profile = yaml.safe_load(f)
        mcp_servers = profile.get("mcp_servers", [])

    multi_mcp = MultiMCP(server_configs=mcp_servers)
    print("Agent before initialize")
    await multi_mcp.initialize()

    agent = AgentLoop(
        user_input=user_input,
        dispatcher=multi_mcp
    )

    try:
        final_response = await agent.run()
        print("\n💡 Final Answer:\n", final_response.replace("FINAL_ANSWER:", "").strip())

    except Exception as e:
        log("fatal", f"Agent failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
