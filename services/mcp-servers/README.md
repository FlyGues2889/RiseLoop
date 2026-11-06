# Rise Loop MCP Servers

固定 3 个工具，按 AGENTS.MD 红线不可扩展。

| 工具 | 所属 Server | 职责 | 数据源 |
|---|---|---|---|
| `read_realtime_state` | health-data-mcp | 读当前状态、久坐计时、待响应干预 | DCS Redis |
| `get_actions_by_state` | action-library-mcp | 按状态/部位/时长筛选动作 | RDS `actions` |
| `write_intervention_result` | health-data-mcp | 写执行记录与迁移历史，同步实时状态 | RDS + Redis |

## 启动

```bash
pip install "mcp>=2" asyncpg redis

export RISELOOP_REDIS_URL=redis://:<password>@<dcs-host>:6379/0
export RISELOOP_RDS_DSN=postgresql://<user>:<password>@<rds-host>:5432/riseloop

python services/mcp-servers/health-data-mcp/server.py
python services/mcp-servers/action-library-mcp/server.py
```

两个 Server 均以 `stdio` 传输，由 CodeArts 智能体作为 MCP 客户端拉起。容器部署时改为 `streamable-http`。

## 约束

- 不提供第 4 个工具；动作筛选的排序、降级策略放 Skill 内部。
- Server 不做状态迁移判断，`to_state` 一律由调用方（状态机）给出。
- 只写 `intervention_logs`、`state_transitions`，不改 `users` / `assessments`。
- 返回值不含用户邮箱、JWT、DSN 等敏感字段。

## 测试

```bash
python -m pytest services/mcp-servers/tests -q
```