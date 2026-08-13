import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = "http://127.0.0.1:8765/mcp"

async def main():
    async with streamable_http_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("=== MCP TOOLS ===")

            tools = await session.list_tools()

            for tool in tools.tools:
                print(f"- {tool.name}")
                print(f"  description: {tool.description}")

            print("\n=== CALL get_database_health ===")

            result = await session.call_tool(
                "get_database_health",
                arguments={},
            )

            print(result)

            print("\n=== CALL get_workers ===")

            result = await session.call_tool(
                "get_workers",
                arguments={},
            )

            print(result)

if __name__ == "__main__":
    asyncio.run(main())