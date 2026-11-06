import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from mcp.server.mcpserver import MCPServer

import action_tools
from common import build_backend

server = MCPServer(
    "sitloop-action-library",
    title="SitLoop 动作库 MCP",
    instructions="按状态、部位与时长为 SitLoop 选择动作库条目，仅返回动作数据，不做状态迁移。",
)

_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = build_backend()
    return _backend


@server.tool(description="按状态/部位/时长筛选动作库，默认返回最长时长最短的 3 条")
async def get_actions_by_state(
    state: str,
    body_parts: list[str] | None = None,
    max_minutes: int | None = None,
    limit: int = 3,
) -> list[dict]:
    return await action_tools.get_actions_by_state(
        backend(),
        state=state,
        body_parts=body_parts,
        max_minutes=max_minutes,
        limit=limit,
    )


if __name__ == "__main__":
    server.run("stdio")