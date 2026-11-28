# 华为云实测配置（2026-11-28）

> 一次真实部署的记录，用于复现与排查。**本文不含口令、AK/SK、API Key**；实际值只存在于服务器 `infra/docker/.env`。
> 资源按包月/按小时计费；不再使用请按 §7 释放（若已释放可忽略），并按 §6 轮换测试期凭据。

## 1. 拓扑

```text
Tauri 客户端
  │ HTTP :8000（测试期公网）
  ▼
Flexus L  Ubuntu 24.04 / 2C4G / 172.31.3.34
  └─ docker compose
       ├─ riseloop-api  0.0.0.0:8000
       ├─ RDS PostgreSQL 18  172.31.11.251:5432  db=riseloop
       └─ DCS Redis 7.0      172.31.13.31:6379
  │
  └─ OBS riseloop-models-20261128
       └─ ModelArts 在线服务 service-af70（8C32G，1 副本）
```

同一 Region：华北-北京四（cn-north-4）；同一 VPC / 子网：`vpc-default-smb` / `subnet-default-smb`。

## 2. 资源清单

### 2.1 云主机

| 项 | 实测值 |
|---|---|
| 产品 | Flexus L |
| 主机名 | `hcss-ecs-d7a5` |
| 规格 | 2 vCPU / 4 GiB / 系统盘 50 GiB |
| 镜像 | Ubuntu 24.04 |
| 带宽 / 流量 | 3 Mbps / 400 GB 每月 |
| 公网 IP | `119.3.214.105` |
| 私网 IP | `172.31.3.34` |
| VPC / 子网 | `vpc-default-smb` / `subnet-default-smb` |
| 安全组 | `sg-default-smb` |
| 入方向 | TCP 8000 来自 `0.0.0.0/0`（测试期）；22 未开放 |
| 计费 | 包月 ¥62.25 |

### 2.2 数据库与缓存

| 项 | RDS | DCS |
|---|---|---|
| 产品 | RDS for PostgreSQL 18 | DCS for Redis 7.0 基础版 |
| 实例 | `rds-3123`，单机，通用型 2C4G，SSD 40 GiB | `dcs-om8w`，单机，1 GiB，x86 |
| 地址 | `172.31.11.251:5432` | `172.31.13.31:6379` |
| 库 / 账号 | `riseloop` / `root` | 密码访问 |
| 网络 | 安全组放行 `172.31.3.34/32` 的 5432 | 白名单 `172.31.3.34` |
| 计费 | 按需 ¥0.40/小时 | 按需 ¥0.08/小时 |

### 2.3 模型与推理

| 项 | 实测值 |
|---|---|
| OBS | `riseloop-models-20261128`（华北-北京四，私有） |
| 模型包 | `v3-loso-head` A 版：`customize_service.py`、`posture_runtime.py`、`model.py`、`model.pt`、`feature_spec.json`、`MANIFEST.json` |
| 在线服务 | `service-af70` / 部署 `deploy-cbf1` |
| 资源池 | 公共资源池，1 副本，8 vCPU / 32 GiB（`modelarts.vm.cpu.8u.32g`） |
| 镜像 | PyTorch 2.1.0 / Python 3.10 / x86 |
| 模型来源 | 自定义模型，`obs://riseloop-models-20261128/` |
| 挂载路径 | `/home/ma-user/infer/model/1` |
| 容器 | 协议 HTTP，端口 8080 |
| 启动命令 | `bash -lc 'source /home/ma-user/anaconda3/etc/profile.d/conda.sh && conda activate PyTorch-2.1.0 && cd /home/ma-user/infer && export TF_MODEL_ARGS="--model_path=/home/ma-user/infer/model/1 --model_name=serve --service_file=/home/ma-user/infer/model/1/customize_service.py" && export MODEL_SERVER_ARGS="$TF_MODEL_ARGS" && exec modelarts_server -w 1 --threads 5 -t 120 -b 0.0.0.0:8080 app:app'` |
| 调用地址 | `https://120.46.74.129/v2/infer/776b8f5c-1af9-47f2-b399-e5a0a6d88700/`（**末尾斜杠必须保留**） |
| 认证 | `Authorization: Bearer <API Key>` |
| 证书 | IP + 自签证书，测试期 `RISELOOP_MODELARTS_TLS_VERIFY=false` |
| 计费 | 按需 ¥3.40/小时，必须设自动停止 |

### 2.4 接口

| 项 | 实测值 |
|---|---|
| 公网地址 | `http://119.3.214.105:8000`（测试期 HTTP，无 ELB/证书） |
| 容器 | `riseloop-api`，`Up (healthy)`，`0.0.0.0:8000->8000` |
| 存储模式 | `store_backend=sql`、`cloud_provider=huawei` |
| 部署方式 | `docker compose -f docker-compose.cloud.yml up -d --build` |

## 3. 环境变量（只列名字）

```dotenv
RISELOOP_ENV=prod
RISELOOP_JWT_SECRET=<openssl rand -hex 32>
RISELOOP_CLOUD_PROVIDER=huawei
RISELOOP_RDS_DSN=postgresql+asyncpg://<用户>:<口令>@<RDS内网地址>:5432/riseloop
RISELOOP_REDIS_URL=redis://:<DCS密码>@<DCS地址>:6379/0
RISELOOP_MODELARTS_ENDPOINT=https://<在线服务地址>/v2/infer/<服务ID>/
RISELOOP_MODELARTS_API_KEY=<API Key>
RISELOOP_MODELARTS_AUTH_HEADER=authorization
RISELOOP_MODELARTS_MODEL_NAME=serve
RISELOOP_MODELARTS_TLS_VERIFY=false
```

两个易错点：

- 口令含 `@` 时必须写成 `%40`，否则 DSN/URL 解析会截断。
- `RISELOOP_MODELARTS_ENDPOINT` 末尾必须带 `/`，否则 APIG 返回 307，httpx 不跟随。

## 4. 实测结果

| 检查 | 结果 |
|---|---|
| `GET /health/ready` | 200，`status=ready`；`rds.provider=huawei-rds` 8.0 ms；`redis.provider=huawei-dcs` 1.57 ms |
| `GET /health/capabilities` | `store_backend=sql`、`cloud_provider=huawei` |
| `smoke.py http://119.3.214.105:8000` | `OK`；注册 201、评估 200、久坐时间 `triggered=true`、反馈 `S1 -> S1 hold` |
| `POST /posture/baseline` | 200，返回 10 字段中位数 |
| `POST /posture/infer` | 200，`source=huawei`、`model=serve`、`latency_ms=101.1`、`recorded=true` |
| RDS | `riseloop` 库 10 张表：`users`、`assessments`、`state_transitions`、`sitting_events`、`intervention_logs`、`posture_summaries`、`qa_logs`、`safety_events`、`revoked_tokens`、`actions` |
| DCS | `session:<userId>:state` 可扫描到 |

真实推理的返回示例：

```json
{
  "posture": "undetermined",
  "confidence": 1.0,
  "source": "huawei",
  "model": "serve",
  "latency_ms": 101.1,
  "recorded": true,
  "risk": { "brli": 0.0, "risk_level": "low", "recommended_plan": "maintain" }
}
```

`undetermined` 来自测试用的中立关键点，不代表模型质量；真实摄像头帧由客户端发送。

## 5. 复现要点

1. 先开 Flexus L，进实例详情记下 VPC / 子网 / 可用区；RDS 与 DCS 必须手动选同一个 VPC。
2. RDS 建库 `riseloop`；安全组只放行云主机私网地址的 5432。
3. DCS 白名单只加云主机私网地址；DCS 创建后不能改 VPC。
4. 云主机装 Docker（国内网络需配 `registry-mirrors`），上传构建上下文，`docker compose up -d --build`。
5. ModelArts 的坑按顺序排：DEW 凭据必须含 `accessKeyId` / `secretAccessKey`（不是 `apiKey`）；挂载路径 `/home/ma-user/infer/model/1`；容器端口 8080；启动命令要带 `TF_MODEL_ARGS`；endpoint 末尾带 `/`；自签证书测试期关闭校验。
6. 验证顺序：`/health/ready` → `/health/capabilities` → `smoke.py` → `/posture/infer` → RDS/Redis 落库。

## 6. 已知限制与安全

- **HTTP + 8000 全开**：没有 HTTPS/ELB，8000 对 `0.0.0.0/0`；测试结束应关闭端口或改成只允许固定 IP。
- **自签证书**：ModelArts 调用地址是 IP + 自签证书，测试期关闭 TLS 校验；正式环境应换域名或把 CA 装进镜像。
- **单副本**：ModelArts 与 API 都是单实例，无高可用；8C32G 按小时计费，必须设自动停止。
- **凭据轮换**：测试期口令与 API Key 已经过聊天/日志链路，测试结束后应重置 RDS/DCS 口令、重建 ModelArts API Key、重新生成 JWT secret。
- **精度边界**：v3 head A 版只有 14 名受试者、单一设备/场景，LOSO macro-F1 0.7759 只能作内部评估，不能对外写成真实准确率。
- **不要提交 `.env`**：镜像与仓库都不应包含 DSN、口令、AK/SK。

## 7. 释放顺序

1. ModelArts：停止并删除在线服务（或至少确认自动停止生效）。
2. RDS：删除实例，停止按小时计费。
3. DCS：删除实例。
4. OBS：按需保留模型包或删除桶。
5. Flexus L：释放实例，确认公网 IP 已释放；月费不退。
6. 费用中心确认无残留按需资源与未释放 EIP。
