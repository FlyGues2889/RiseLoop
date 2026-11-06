# 华为云接入指南（SitLoop）

本文件说明 SitLoop 云端需要接入哪些华为云服务、代码里已经预留的接口，以及从零开通到验证的步骤。

## 1. 接入清单

| 服务 | 用途 | 必要性 | 代码位置 | 当前状态 |
|---|---|---|---|---|
| RDS for PostgreSQL | 事实数据：用户、评估、迁移历史、执行记录、动作库、问答日志、安全事件 | 必须（硬门槛） | `app/cloud/rds.py` | 已实现连接与 `SELECT 1` 探活 |
| DCS for Redis | 实时状态：`session:*`、`sitting:*`、`pending_intervention:*`、`safety:*` | 必须（硬门槛） | `app/cloud/dcs.py` | 已实现 `ping/get/set/delete` |
| CodeArts 智能体 | 规划 Agent + 执行 Agent 编排 | 必须（硬门槛） | `app/cloud/codearts.py` | 已实现探活与 `invoke`，请求体适配点集中在 `invoke()` |
| OBS | Tauri 安装包、演示视频、静态资产分发 | 推荐 | `app/cloud/obs.py` | 已实现预签名（OBS V2 签名，无 SDK 依赖） |
| KMS | 健康字段加密 | 推荐（PRD 合规） | `app/cloud/kms.py` | 已实现 AES-256-GCM 字段加解密 |
| IAM | 子用户与 AK/SK、最小权限 | 必须（间接） | 无代码，控制台配置 | 待配置 |
| ECS / CCE + SWR | 部署 `cloud-api` 与 MCP Server | 必须（公网演示） | `infra/huawei-cloud/` | 待部署 |
| ELB / EIP + SSL 证书 | 公网 HTTPS 入口 | 必须 | `infra/huawei-cloud/` | 待部署 |
| LTS / APM | 日志与链路追踪 | 可选 | 无 | 未接入 |

## 2. 前置准备

1. 注册华为云账号并完成实名认证，记录使用的 Region（建议 `cn-north-4`，所有资源同 Region）。
2. 创建 VPC 与子网，后续 RDS、DCS、ECS 全部放入同一 VPC，走内网。
3. 在 IAM 创建**子用户**（不要用主账号 AK/SK），授予 RDS、DCS、OBS、KMS 的最小权限，生成 AK/SK。
4. 本地准备：Python 3.11+、Docker、`psql`、`redis-cli`（可选，用于连通性验证）。

## 3. 资源开通

### 3.1 RDS for PostgreSQL

1. 控制台 → 数据库 → RDS for PostgreSQL → 购买实例。
2. 规格：演示期 2 vCPU / 4 GB 起；**多可用区**、**自动备份**、**存储加密（KMS）** 三项必须开启。
3. 网络：选择上一步 VPC/子网；安全组仅放行 `cloud-api` 所在 ECS 的 5432 私网访问，不对公网开放。
4. 创建数据库 `sitloop` 与业务账号，记录内网地址、端口、库名、用户名、密码。
5. 验证：`psql "host=<内网地址> port=5432 dbname=sitloop user=<用户>"`。

### 3.2 DCS for Redis

1. 控制台 → 分布式缓存服务 DCS → 购买 Redis，选择**主备**模式。
2. 与 RDS 同 VPC；设置访问密码；安全组只放行 `cloud-api` 的 6379。
3. 记录内网地址、端口、密码。
4. 验证：`redis-cli -h <地址> -p 6379 -a <密码> ping`。

### 3.3 CodeArts 智能体

1. 在 CodeArts 控制台创建「规划 Agent」「执行 Agent」，分别配置提示词与可用 Skill/MCP 工具。
2. 发布后获取调用地址与鉴权信息（API Key / Token，以控制台发布页展示为准）。
3. 填入：
   - `SITLOOP_CODEARTS_ENDPOINT`：智能体调用地址
   - `SITLOOP_CODEARTS_API_KEY`：鉴权密钥
   - `SITLOOP_CODEARTS_PLANNING_AGENT_ID` / `SITLOOP_CODEARTS_EXECUTING_AGENT_ID`：两个 Agent 的 ID
4. 不同 CodeArts 版本的请求体字段可能不同。本项目把差异收敛在 `app/cloud/codearts.py`：
   - 鉴权头：`_headers()`
   - 请求体：`invoke()` 中的 `body = {"agent_id": ..., "input": ...}`
   按平台实际契约改这两处即可，不散落到业务代码。

### 3.4 OBS（推荐）

1. 创建**私有**桶，开启服务端加密；配置 CORS 允许 Tauri 下载域。
2. 上传安装包与演示视频；记录 endpoint、桶名、region。
3. `SITLOOP_OBS_ENDPOINT` 填**桶域名**（如 `https://sitloop.obs.cn-north-4.myhuaweicloud.com`）。`presign_put/presign_get` 使用 OBS V2 查询串签名，有效期默认 1 小时；`mock` 模式返回 `mock://` 占位地址，仅用于流程自测。

### 3.5 KMS（推荐）

1. 创建密钥，授权给子用户。
2. 记录 endpoint 与 key id；`SITLOOP_KMS_MASTER_KEY` 填 32 字节数据密钥的 Base64（生产由 KMS `GenerateDataKey` 注入，不落盘）。
3. `app/cloud/kms.py` 用 AES-256-GCM 做字段级加解密，输出 `v1:<base64(nonce+ciphertext)>`；用于 `assessments`、`intervention_logs` 中的健康字段。`mock` 模式由 `SITLOOP_JWT_SECRET` 派生本地密钥，仅限开发。

### 3.6 计算与公网入口

1. 创建 ECS（或 CCE 集群），与 RDS/DCS 同 VPC。
2. 构建镜像并推送 SWR：
   ```bash
   docker build -t <region>.myhuaweicloud.com/<组织>/sitloop-cloud-api:0.1.0 apps/cloud-api
   docker login <region>.myhuaweicloud.com
   docker push <region>.myhuaweicloud.com/<组织>/sitloop-cloud-api:0.1.0
   ```
3. ECS 上用环境变量文件或 CCE Secret 注入配置，启动：
   ```bash
   docker run -d --name sitloop-api -p 8000:8000 --env-file .env <镜像地址>
   ```
4. 绑定 ELB/EIP，配置域名与 SSL 证书，只暴露 443。安全组不要对公网开放 5432/6379。

## 4. 环境变量

复制 `apps/cloud-api/.env.example` 为 `apps/cloud-api/.env`，按实际值填写：

| 变量 | 说明 |
|---|---|
| `SITLOOP_CLOUD_PROVIDER` | `mock`（本地无云资源）或 `huawei` |
| `SITLOOP_RDS_DSN` / `SITLOOP_RDS_*` | 优先用完整 DSN；否则由 host/port/db/user/password 拼接 |
| `SITLOOP_REDIS_URL` / `SITLOOP_REDIS_*` | 优先用完整 URL |
| `SITLOOP_CODEARTS_*` | 智能体地址、密钥、两个 Agent ID |
| `SITLOOP_OBS_*` | 桶域名、桶名、AK/SK（预签名分发） |
| `SITLOOP_KMS_*` | endpoint、key id、32 字节主密钥、AK/SK（字段加密） |
| `SITLOOP_CORS_ORIGINS` | JSON 数组，Tauri 本地调试默认 `http://localhost:1420` |

`.env` 已在 `.gitignore` 中，禁止提交。生产环境用 CCE Secret 或 ECS 环境变量注入，不写入镜像。

## 5. 验证

```bash
cd apps/cloud-api
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| 端点 | 用途 | 期望 |
|---|---|---|
| `GET /health/live` | 进程存活 | `200 {"status":"ok",...}` |
| `GET /health/deps` | 五个依赖明细 | 不含任何密码/密钥 |
| `GET /health/ready` | 就绪检查 | RDS、Redis、CodeArts 全部可达时 200，否则 503 |

- 本地开发保持 `SITLOOP_CLOUD_PROVIDER=mock`，无需云资源即可跑通。
- 切到 `huawei` 后逐个填写配置，先看 `/health/deps` 的 `configured` 与 `reachable`，再联调业务接口。

## 6. 安全与合规

- 健康数据只进 RDS；Redis 只放实时状态，不落完整档案。
- AK/SK、CodeArts Key 只在服务端；Tauri 端禁止持有。
- 安全组最小放行：5432/6379 仅内网，公网只开 443。
- 日志不打印 DSN、密码、原始问卷；健康检查只返回状态与异常类型。

## 7. 验收对照

- [ ] RDS 多可用区、自动备份、KMS 加密已开启。
- [ ] DCS Redis 为主备模式，`/health/deps` 中 `redis.reachable=true`。
- [ ] CodeArts 两个 Agent 可被 `invoke` 调用并返回结果。
- [ ] `cloud-api` 在华为云公网 HTTPS 可达。
- [ ] OBS 预签名下载链接在有效期内可直接访问，过期后返回 403。
- [ ] KMS 字段加密后写库，读回可还原原文；篡改密文解密失败。