# 演示模式（本地数据，不上云）

## 入口

桌面端登录页底部「没有云端环境？本地演示模式」。

点击后客户端会把 API 基地址切到本机 `http://127.0.0.1:8000`，自动注册/登录演示账号 `demo@sitloop.app`，直接进入首次评估。界面顶部显示「演示模式 · 本地数据不上云」徽标。

## 一键启动

```bash
pnpm demo
```

脚本做三件事：

1. 探测 8000 端口是否已有服务，有则复用；
2. 没有则用 `SITLOOP_CLOUD_PROVIDER=mock` 启动 `apps/cloud-api`（数据只在本机内存）；
3. 等健康检查通过后启动 `pnpm tauri dev`。

也可以手动分两步：

```bash
cd apps/cloud-api && SITLOOP_CLOUD_PROVIDER=mock python -m uvicorn app.main:app --port 8000
cd apps/desktop-tauri && pnpm tauri dev
```

## 演示模式下可用

- 首次评估与初始状态判定（S0/S1）
- Rust 侧久坐计时、托盘常驻、阈值调整、系统通知
- 动作库推送与执行指引
- 反馈提交与四分支状态迁移（`upgrade / rollback / degrade / short_circuit`）
- 安全红线短路与就医提示
- 会话内操作记录

## 演示模式下不可用

| 能力 | 原因 |
|---|---|
| 智能问答 | 依赖 CodeArts 智能体与知识库 |
| AI 建议 / 周度洞察 | 依赖 CodeArts 双 Agent 编排 |
| 云端周度聚合 | `cloud_rds` 事实数据不在本机持久化 |
| 跨设备同步 | 无云端账号体系 |

界面会在进入演示模式时把上述限制写入会话记录，避免误认为云端能力已就绪。

## 数据边界

- 存储：`cloud-api` 的内存 Store（用户、评估、迁移历史、执行记录、会话状态）。
- 生命周期：进程退出即清空；退出演示模式会清除钥匙串中的令牌。
- 不上传：演示模式不连接任何华为云资源，`cloud_provider=mock` 下 RDS/Redis/CodeArts 都不参与。
- 不持久化：重启后从「首次评估」重新开始，适合反复录屏。

## 与架构红线的关系

演示模式的业务逻辑仍然跑在 `apps/cloud-api` + `packages/intervention-engine`，只是换成本机 mock 后端：

- 端侧（Tauri/Vue）没有新增状态迁移代码，只换了 API 基地址；
- 动作库仍由云端 `actions` 表提供，端侧不硬编码；
- 状态迁移仍由 `intervention-engine` 计算，端侧只展示结果；
- 因此「端侧禁止状态迁移 / 禁止硬编码动作库」两条红线未被突破。

## 演示模式进不去时的排查

客户端会把失败原因分成「标题 / 原因 / 建议」三段显示在登录按钮上方，按提示处理即可：

| 界面提示 | 含义 | 处理 |
|---|---|---|
| 无法连接本地演示服务 | 8000 端口没有响应 | 在项目根目录运行 `pnpm demo`，或手动启动 `apps/cloud-api` |
| 请求失败（401）invalid_credentials | 8000 上运行着旧库，演示账号密码不一致 | 重启 mock 后端（内存库会重置），或手动注册该邮箱 |
| 8000 端口已被其他服务占用 | `pnpm demo` 探测到非 SitLoop 服务 | 释放端口，或改 `VITE_DEMO_API_BASE` 指向其他端口 |
| 令牌未写入系统钥匙串 | Keychain 不可用 | 不阻断演示，令牌本次会话保存在内存 |

脚本启动阶段还会校验 `/health/live` 返回的 `service` 是否为 `SitLoop Cloud API`，防止误连到占用了 8000 端口的其他程序。

## 现场保底

1. 提前 `pnpm demo` 跑通一次，确认 Python 依赖齐全（`fastapi`、`uvicorn`、`sqlalchemy`、`redis`、`asyncpg`）。
2. 会场网络不可用时，演示模式仍可完整展示本地闭环。
3. 需要展示华为云能力时，用云端模式 + 录屏，演示模式不替代上云验收。