import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from mcp.server.mcpserver import MCPServer

import health_tools
from common import build_backend

server = MCPServer(
    "sitloop-health-data",
    title="SitLoop 健康数据 MCP",
    instructions="提供 SitLoop 实时状态读取与干预结果写入，禁止用于任何医疗诊断。",
)

_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = build_backend()
    return _backend


@server.tool(description="读取用户在 DCS Redis 中的当前状态、久坐计时与待响应干预")
async def read_realtime_state(user_id: str) -> dict:
    return await health_tools.read_realtime_state(backend(), user_id)


@server.tool(description="写入干预执行结果到 RDS，并同步迁移历史与 Redis 实时状态")
async def write_intervention_result(
    user_id: str,
    action_id: str,
    state: str,
    completion: str,
    feeling: str,
    pain_score: int,
    obstacle: str | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    reason: str | None = None,
    transition_type: str | None = None,
) -> dict:
    return await health_tools.write_intervention_result(
        backend(),
        user_id=user_id,
        action_id=action_id,
        state=state,
        completion=completion,
        feeling=feeling,
        pain_score=pain_score,
        obstacle=obstacle,
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        transition_type=transition_type,
    )


if __name__ == "__main__":
    server.run("stdio")