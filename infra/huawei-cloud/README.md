# 华为云部署（自测环境）

本文只写技术前提、部署步骤与验证方法。资源规格、计费方式与采购安排属于团队内部事项，不进项目文档。

## 1. 前置条件

一台 Linux 主机（x86_64，Ubuntu 22.04+，≥2 vCPU / 4 GiB，系统盘 ≥40 GiB），装 Docker 24+ 与 Docker Compose v2，有公网 IP，入站放行 TCP 8000。

需要提前拿到的连接参数：

| 依赖 | 需要的值 | 形态 |
|---|---|---|
| DCS for Redis | 连接地址、端口、密码 | `xxx.dcs.huaweicloud.com:6379` |
| RDS for PostgreSQL | 内网地址、端口、库名、账号、口令 | `<地址>:5432/riseloop` |
| ModelArts 在线服务（可选） | 调用 URL、鉴权值、鉴权头名 | `https://...` |

网络前提：主机、DCS、RDS 必须在同一 Region、同一 VPC、同一子网。DCS 与 RDS 默认只有内网入口，跨 VPC 或跨子网都连不上。入站放行 TCP 22 用于运维、TCP 8000 用于 API；6379 与 5432 只对主机私网地址放行，不对公网开放。

## 2. 装 Docker

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker compose version
```

## 3. 传代码

服务器只需要 `apps/cloud-api` 与 `infra/docker`，目录层级必须保持，compose 的构建上下文是 `../../apps/cloud-api`。

```bash
# 本地
scp -r apps/cloud-api infra/docker root@<公网IP>:~/riseloop-dist/
# 服务器
mkdir -p ~/riseloop/apps ~/riseloop/infra
mv ~/riseloop-dist/cloud-api ~/riseloop/apps/
mv ~/riseloop-dist/docker ~/riseloop/infra/
```

## 4. 配置 .env

```bash
cd ~/riseloop/infra/docker
cp env.example .env
openssl rand -hex 32        # 填进 RISELOOP_JWT_SECRET
```

```
RISELOOP_ENV=prod
RISELOOP_CLOUD_PROVIDER=huawei
RISELOOP_JWT_SECRET=<openssl 生成的那串>
RISELOOP_RDS_DSN=postgresql+asyncpg://<RDS用户>:<口令>@<RDS内网地址>:5432/riseloop
RISELOOP_REDIS_URL=redis://:<DCS密码>@<DCS连接地址>:6379/0
```

`cloud_provider` 必须是 `huawei` 才能证明真连上了：`apps/cloud-api/app/cloud/dcs.py:23-30` 在 `mock` 下直接返回「可达」，不发起任何连接。`huawei` 模式下 RDS 也必须能连，DSN 填错会在启动时抛 `RDS is not configured`。

## 5. 起栈

```bash
docker compose -f docker-compose.cloud.yml up -d --build
docker compose -f docker-compose.cloud.yml ps
```

## 6. 验证

```bash
curl http://<公网IP>:8000/health/live
curl http://<公网IP>:8000/health/deps         # redis.provider=huawei-dcs, rds.reachable=true, modelarts.configured
curl http://<公网IP>:8000/health/capabilities # store_backend=sql
```

注册账号，确认事实数据落 RDS、实时状态落 DCS：

```bash
curl -X POST http://<公网IP>:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@riseloop.app","password":"riseloop-test-1"}'

docker run --rm -it -e PGPASSWORD='<口令>' postgres:16-alpine \
  psql "host=<RDS内网地址> port=5432 dbname=riseloop user=<用户>" -c '\dt'

docker run --rm -it redis:7-alpine redis-cli -h <DCS连接地址> -p 6379 -a '<密码>' --scan --pattern 'session:*'
```

注册后打一次 `/sitting/heartbeat` 才会写 `session:*`，空列表不代表故障。

> `/health/ready` 只要求 `rds` + `redis` 两项（`app/api/routes/health.py:13`）。ModelArts 没接不影响 ready，但 `/posture/infer` 会返回 503 `modelarts_unavailable`。

## 7. 接 ModelArts

顺序不能反：**训模型 → 部署在线服务 → 填 endpoint**。

1. **训模型**：输入 33 点归一化坐标 + 派生特征，输出 `baseline` / `forward_head` / `lateral_tilt` / `undetermined` 四分类。小模型够用（GBDT / MLP），CPU 训练与推理。
2. **样本**：用 `apps/cloud-api/app/cloud/modelarts.py:45` 的 mock 几何规则批量打标，人工修正 100–200 帧。
3. **部署**：模型导入 ModelArts 模型管理，部署为**在线服务**（实时服务、CPU 规格、1 副本），从服务详情取调用 URL 与鉴权方式。
4. **填 `.env`**：
   ```
   RISELOOP_MODELARTS_ENDPOINT=<在线服务URL>
   RISELOOP_MODELARTS_API_KEY=<鉴权值>
   RISELOOP_MODELARTS_AUTH_HEADER=x-auth-token
   ```
5. 重启 api，验证真链路：
   ```bash
   curl -X POST http://<公网IP>:8000/posture/infer -H 'Authorization: Bearer <JWT>' \
     -H 'Content-Type: application/json' \
     -d '{"keypoints":[{"x":0.5,"y":0.4,"z":0.0}, ...33 个点...]}'
   # 期望：source=huawei，posture 为四类之一，latency_ms 有值
   ```
6. 反向验一次降级：停掉在线服务，`/posture/infer` 应返回 503 `modelarts_unavailable`，客户端提示「云端不可用」且不崩。

请求体与响应格式见 [`docs/architecture/huawei-cloud-integration.md`](../../docs/architecture/huawei-cloud-integration.md) §4。

## 8. 客户端接入

`apps/desktop-tauri/src/config/modes.js:1` 的地址在构建期注入，改地址要重新构建：

```bash
cd apps/desktop-tauri
VITE_API_BASE=http://<公网IP>:8000 pnpm build
```

PowerShell 下先 `$env:VITE_API_BASE="http://<公网IP>:8000"` 再 `pnpm build`。

## 9. 排错

| 现象 | 原因 |
|---|---|
| 启动即崩 `RuntimeError: RDS is not configured` | `cloud_provider=huawei` 但 `RISELOOP_RDS_DSN` 为空，见 `app/repositories/sql_store.py:40` |
| `/health/deps` 显示 redis 可达却没真连 | `RISELOOP_CLOUD_PROVIDER` 仍是 `mock`，mock 下不发起连接 |
| `/health/ready` 503 | `rds` 或 `redis` 有一项不可达 |
| `/posture/infer` 503 `modelarts_unavailable` | endpoint 或密钥未填，或在线服务已停 |
| `session:*` 扫不到 | 还没打过 `/sitting/heartbeat` |
| 客户端连不上 | 公网 IP 变了要重新 `build`，`VITE_API_BASE` 是构建期常量 |
