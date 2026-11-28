# 云端接口清单（api-surface）

> 更新：2026-11-28。这份文件回答一个问题：**接口还缺什么、云资源当前是什么状态**。
> 代码口径以 `apps/cloud-api/app/api/routes/*` 为准；本文件与代码不一致时以代码为准并回写本文件。

## 1. 现状一句话

接口层已经完整：从注册登录到评估、计时、姿态、干预、反馈、问答、周复盘全部有路由、有 schema、有测试。
云资源已在 2026-11-28 完成一次真实部署：RDS、DCS、ModelArts 均为 `huawei`，OBS 用于模型包，KMS 未接线。姿态模型已部署 v3 head A 版（16 维，OOF macro-F1 0.7759、forward_head F1 0.7142），`/posture/infer` 实测返回 `source=huawei`；指标只作内部评估。实测配置见 [`infra/huawei-cloud/deployed-config.md`](../../infra/huawei-cloud/deployed-config.md)。
`GET /health/capabilities` 是自查入口：返回各依赖的 `provider / configured / reachable` 与限流参数。

## 2. 路由全表

除标注"公开"的以外，全部要求 `Authorization: Bearer <access_token>`。

| 方法 | 路径 | 说明 | 主要错误码 |
|---|---|---|---|
| GET | `/` | 服务名、版本、环境、云厂商模式 | — |
| GET | `/health/live` | 存活探针（公开） | — |
| GET | `/health/deps` | 各云依赖连通性（公开） | — |
| GET | `/health/ready` | 就绪探针，RDS/Redis 任一不可达返回 503（公开） | — |
| GET | `/health/capabilities` | 能力与限流自查（公开） | — |
| POST | `/auth/register` | 注册，返回访问令牌 + 刷新令牌（公开） | `email_exists`(409)、`rate_limited`(429) |
| POST | `/auth/login` | 登录（公开） | `invalid_credentials`(401) |
| POST | `/auth/refresh` | 用刷新令牌换新的一对令牌，旧刷新令牌立即作废（公开） | `invalid_refresh_token`、`refresh_expired`、`token_revoked`(401) |
| POST | `/auth/logout` | 吊销当前访问令牌；body 带 `refresh_token` 时一并吊销 | `token_revoked`(401) |
| DELETE | `/auth/account` | 删除账号与其全部数据 | `user_not_found`(404) |
| POST | `/assessment` | 评估，产出初始状态与两周方案；红旗命中直接 403 | `safety_short_circuit`(403) |
| POST | `/sitting/heartbeat` | 上报久坐时间，到阈值推最多 3 个动作 | — |
| GET | `/actions/{state}` | 按状态取动作，可加 `body_part`、`max_minutes` | — |
| POST | `/ingest/wearable` | 穿戴设备上报，**未实现**，固定 501 | `not_implemented`(501) |
| POST | `/posture/risk` | 姿态特征 + 久坐/疼痛 → BRLI 风险与推荐动作、 citations | — |
| POST | `/posture/infer` | 关键点 → ModelArts 姿态四分类（低置信度返回 `undetermined`）；v3 head A 版已部署，实测 `source=huawei` | `modelarts_unavailable`(503) |
| POST | `/posture/baseline` | 3–120 帧中立位 → 10 字段个人基线（服务端取中位数） | 422 |
| GET | `/intervention/current` | 当前待完成动作 | `no_pending_intervention`(404)、`action_not_found`(404) |
| POST | `/intervention/feedback` | 反馈触发状态迁移（完成/部分/跳过 + 障碍归因） | `safety_short_circuit`(403) |
| POST | `/qa/ask` | 循证问答，返回答案与引用 id | — |
| GET | `/review/weekly` | 近 N 天周复盘（默认 7） | — |

## 3. 鉴权生命周期

```text
register / login        → access(1h) + refresh(30d)
业务请求                 → Authorization: Bearer <access>
access 过期(401 token_expired) → POST /auth/refresh（换新一对，旧的刷新令牌作废）
主动退出                 → POST /auth/logout（jti 进黑名单，refresh 一并作废）
删账号                   → DELETE /auth/account（清用户 + 全部业务数据）
```

- 令牌是自签 HS256 JWT，claims：`sub / typ(access|refresh) / iat / exp / jti`。
- 客户端收到 401 后自动用刷新令牌换新的一对并重放原请求（`api-client` 内建，业务调用方无感）；并发的多个 401 只续期一次。
- 吊销只存 `jti` 与到期时间（`revoked_tokens` 表 / 内存字典），到期自动清理，不存用户内容。
- 刷新令牌不能当访问令牌用（`typ` 校验），避免登出后仍能续期。

## 4. 限流

| 桶 | 默认 | 键 |
|---|---|---|
| 登录类（`/auth/login`、`/auth/register`、`/auth/refresh`） | 10 次 / 60 秒 | 无 token 时按来源 IP |
| 其它业务接口 | 120 次 / 60 秒 | 有 token 按 token 指纹，否则按 IP |

超限返回 `429`，body `{"detail": "rate_limited"}`，带 `Retry-After`（秒）。
健康检查与 `OPTIONS` 不计数。计数在进程内存里；横向扩容时要换成 DCS `INCR`（`app/core/ratelimit.py` 已把实现收口在一个中间件里）。

## 5. mock 与 huawei 怎么切

全部通过环境变量（前缀 `RISELOOP_`，见 `app/core/config.py`）：

| 变量 | 作用 |
|---|---|
| `RISELOOP_CLOUD_PROVIDER=mock\|huawei` | 适配层总开关 |
| `RISELOOP_RDS_DSN` 或 `RDS_HOST/RDS_USER/RDS_DB/RDS_PASSWORD` | 配了就走 SQL 存储，否则内存存储 |
| `RISELOOP_REDIS_URL` 或 `REDIS_HOST` | 配了实时状态走 DCS，否则进程内存 |
| `RISELOOP_MODELARTS_ENDPOINT / _API_KEY / _PROJECT_ID / _MODEL_NAME` | 姿态推理；不配时 `/posture/infer` 返回 503，端侧显式降级 |
| `RISELOOP_CODEARTS_ENDPOINT / _API_KEY / _PLANNING_AGENT_ID / _EXECUTING_AGENT_ID` | 问答与规划智能体 |
| `RISELOOP_OBS_*`、`RISELOOP_KMS_*` | 对象存储与密钥托管，业务尚未接线 |
| `RISELOOP_JWT_SECRET` | **上线必须换**，默认值是本地开发用的 |
| `RISELOOP_JWT_TTL_SECONDS / JWT_REFRESH_TTL_SECONDS` | 访问 1 小时 / 刷新 30 天 |
| `RISELOOP_RATE_LIMIT_REQUESTS / _WINDOW_SECONDS / _AUTH_REQUESTS` | 限流参数 |

密钥只进 `.env` 或环境变量，不写仓库、不下发客户端。

## 6. 资源开通清单（2026-11-28 已按此顺序开通）

| 顺序 | 资源 | 用途 | 开通后要验的接口 |
|---|---|---|---|
| 1 | DCS Redis | session 状态、久坐计时、待响应干预 | `/health/deps` 中 `redis.provider=huawei-dcs`；断 Redis 时降级为内存且不崩 |
| 2 | RDS PostgreSQL | 用户、评估、迁移、执行记录、问答日志、安全事件、姿态摘要 | `/health/capabilities` 显示 `store_backend=sql`；重启后数据仍在 |
| 3 | ModelArts 在线服务 | 关键点 → 姿态四分类（v3 head A 版已部署） | `/posture/infer` 返回 `source=huawei`；超时 2.5s 返回 503 并端侧降级 |
| 4 | OBS | 模型包 / 导出物 / 证据材料 | 已建桶 `riseloop-models-20261128` 用于模型包；业务分发未接线 |
| 5 | KMS | 密钥托管与字段加密 | 同上 |
| — | AgentArts（可选） | 问答与方案解释的编排替身 | `/qa/ask` 返回真实答案与 citations |

开通后必须补的三项验证：断网、关摄像头、ModelArts 超时回退（见 PROGRESS §5 手测清单）。

初赛阶段已完成一次性链路测试：云主机 + DCS + RDS + ModelArts + OBS（2026-11-28）；KMS/AgentArts 未接。规格、预算、开通与删除步骤见 [`infra/huawei-cloud/cloud-test-checklist.md`](../../infra/huawei-cloud/cloud-test-checklist.md)，实测配置见 [`deployed-config.md`](../../infra/huawei-cloud/deployed-config.md)。

## 7. 客户端接入状态

| 能力 | 状态 |
|---|---|
| 注册 / 登录 / 凭证进钥匙串 | ✅ 已接 |
| 评估、久坐时间、动作、姿态、反馈、问答、周复盘 | ✅ 已接 |
| 错误码 → 人话 | ✅ `packages/api-client` 的 `CODE_VIEWS`，新增 `token_revoked`、`rate_limited` 等 |
| 刷新令牌自动续期 | ⬜ 服务端已就绪；客户端要 Rust 钥匙串加一个槽位 + 401 时重试一次 |
| 登出 / 删账号 | ⬜ 服务端已就绪；界面只有"清除本机数据"，未调这两个接口 |
