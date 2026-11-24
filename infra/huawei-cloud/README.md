# 华为云部署（Flexus L + Docker Compose）

目标：一台云主机上用 Compose 起 `cloud-api`，`/health/ready` 返回 200，并从公网跑通
注册 → 评估 → 上报久坐时间 → 反馈 → 状态迁移。

本文只写技术前提、步骤与验证。资源规格与采购属于团队内部事项，不进项目文档。

## 1. 前置条件

- Flexus L 实例：x86_64，Ubuntu 22.04+，2 vCPU / 4 GiB，系统盘 ≥40 GiB，有公网 IP。
- 云主机、RDS、DCS 在**同一 Region、同一 VPC、同一子网**；RDS 与 DCS 默认只有内网地址。
- 端口放行在 **Flexus L 实例自己的防火墙**（控制台 → 实例详情 → 防火墙）里做，不在 VPC 安全组里找：

  | 端口 | 来源 | 用途 |
  |---|---|---|
  | TCP 22 | 你的公网 IP | 运维 |
  | TCP 8000 | `0.0.0.0/0`（或评审机器 IP） | API |

  RDS 5432 与 DCS 6379 只对云主机私网地址放行，不要对公网开放。

需要提前拿到的值：

| 依赖 | 需要的值 | 形态 |
|---|---|---|
| DCS for Redis | 连接地址、端口、密码 | `xxx.dcs.huaweicloud.com:6379` |
| RDS for PostgreSQL | 内网地址、端口、库名、账号、口令 | `<地址>:5432/riseloop` |
| ModelArts 在线服务（可选） | 调用 URL、鉴权值、鉴权头名 | `https://...` |

## 2. 装 Docker

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker compose version
```

## 3. 传代码

镜像构建上下文是**仓库根**，所以以下四项必须保持原有层级一起上传：

```text
apps/cloud-api/
packages/intervention-engine/
data/actions/actions.json
infra/docker/
infra/huawei-cloud/smoke.py
```

```bash
# 本地（仓库根）
tar -czf riseloop-dist.tgz apps/cloud-api packages/intervention-engine \
  data/actions/actions.json infra/docker infra/huawei-cloud/smoke.py
scp riseloop-dist.tgz root@<公网IP>:~/

# 服务器
mkdir -p ~/riseloop && tar -xzf ~/riseloop-dist.tgz -C ~/riseloop
```

`packages/intervention-engine` 在镜像里以可安装包进入 site-packages；`data/actions/actions.json`
是动作库来源，缺了会在容器里回退到 4 条内置动作。两者缺一都会导致本地与线上行为不一致。

## 4. 配置 .env

```bash
cd ~/riseloop/infra/docker
cp env.example .env
chmod 600 .env
openssl rand -hex 32        # 填进 RISELOOP_JWT_SECRET
```

必改项：

```dotenv
RISELOOP_ENV=prod
RISELOOP_JWT_SECRET=<openssl 生成的那串>
```

然后按场景二选一：

**场景 A：全托管（推荐，验收用这个）**

```dotenv
RISELOOP_CLOUD_PROVIDER=huawei
RISELOOP_RDS_DSN=postgresql+asyncpg://<RDS用户>:<口令>@<RDS内网地址>:5432/riseloop
RISELOOP_REDIS_URL=redis://:<DCS密码>@<DCS地址>:6379/0
```

**场景 B：本机容器内 PG + Redis（只用于本地冒烟，不算上云）**

```dotenv
RISELOOP_CLOUD_PROVIDER=mock
RISELOOP_RDS_DSN=postgresql+asyncpg://riseloop:<POSTGRES_PASSWORD>@postgres:5432/riseloop
RISELOOP_REDIS_URL=redis://redis:6379/0
```

口径说明：

- `cloud_provider=mock` 时所有云依赖直接返回可达，不发起任何真实连接。`/health/ready` 也会是 200，
  但这只证明进程与业务链路可跑，**不能作为上云证据**。
- `cloud_provider=huawei` 时 RDS DSN 是硬前置：**缺失则启动即失败**（见 §6），不会退回内存存储。
  DCS 缺失仍可启动（会话状态落进程内存），但 `/health/ready` 会因 `redis` 未配置返回 503。
- RDS DSN 已填但连不上：进程照常启动，`schema init skipped` warning，`/health/ready` 503，
  业务请求返回 `503 {"detail":"store_unavailable"}`，不会静默 500。
- `.env` 只被 compose 读取，不进镜像、不进 git。

## 5. 起栈

```bash
cd ~/riseloop/infra/docker
docker compose -f docker-compose.cloud.yml up -d --build
docker compose -f docker-compose.cloud.yml ps
docker compose -f docker-compose.cloud.yml logs -f api
```

场景 A 时 compose 里的 `postgres` / `redis` 容器仍会启动但 API 不会连它们；它们只是场景 B 的本地替身。
需要释放内存可在 api 起来后 `docker compose -f docker-compose.cloud.yml stop postgres redis`；
下次 `up` 时 compose 会因 `depends_on` 重新拉起它们，属正常。

## 6. 启动失败语义（fail-fast）

`RISELOOP_CLOUD_PROVIDER=huawei` 且没有可用 RDS 配置时，进程主动退出，不进入内存降级：

```text
ERROR:riseloop.cloud:refusing to start: RISELOOP_CLOUD_PROVIDER=huawei requires RISELOOP_RDS_DSN
RuntimeError: RISELOOP_CLOUD_PROVIDER=huawei requires RISELOOP_RDS_DSN (or RISELOOP_RDS_HOST +
RISELOOP_RDS_USER + RISELOOP_RDS_DB); in-memory store is not allowed in huawei mode
ERROR:    Application startup failed. Exiting.
```

compose 对 api 使用 `restart: on-failure:5`，最多重试 5 次后停下，避免无意义 crash-loop。
先改 `.env`，再 `docker compose -f docker-compose.cloud.yml up -d --force-recreate api`。

## 7. 验证

### 7.1 健康检查

```bash
curl -s http://<公网IP>:8000/health/live
curl -s http://<公网IP>:8000/health/ready
curl -s http://<公网IP>:8000/health/capabilities
```

期望（场景 A）：

- `/health/live`：`{"status":"ok",...}`
- `/health/ready`：HTTP 200，`status=ready`，`rds.reachable=true`、`redis.reachable=true`
- `/health/capabilities`：`store_backend=sql`、`cloud_provider=huawei`，
  `redis.provider=huawei-dcs`、`rds.provider=huawei-rds`
- `/health/deps` 六项里 `codearts` / `obs` / `kms` / `modelarts` 未配置属正常，不影响 ready

`/health/*` 不回显 DSN、口令或密钥；不要为排障把这些字段加进响应。

### 7.2 完整业务链路

```bash
python3 ~/riseloop/infra/huawei-cloud/smoke.py http://<公网IP>:8000
```

只依赖标准库。输出示例（本地 mock 实测）：

```text
/health/live          200 0.1.0
/health/ready         200 ready
/health/capabilities  store_backend=memory cloud_provider=mock
/auth/register        201 smoke-1795436852@riseloop.app
/assessment           200 state=S1 risk=low
/sitting/heartbeat    200 triggered=True action=s1-calf-pump (2 min)
/intervention/current 200 s1-calf-pump
/intervention/feedback 200 S1 -> S1 hold (已完成但未达升级阈值，维持当前状态)
OK
```

场景 A 时第 3 行应为 `store_backend=sql cloud_provider=huawei`，其余流程一致。
脚本自带断言：ready 非 200、久坐时间未触发提醒、反馈缺字段都会直接非零退出。

### 7.3 落库与实时状态

```bash
docker run --rm -e PGPASSWORD='<口令>' postgres:16-alpine \
  psql "host=<RDS内网地址> port=5432 dbname=riseloop user=<用户>" -c '\dt'

docker run --rm redis:7-alpine redis-cli -h <DCS地址> -p 6379 -a '<密码>' --scan --pattern 'session:*'
```

注册只写 RDS；打过一次 `/sitting/heartbeat` 才会出现 `session:*`，空列表不代表故障。

## 8. 接 ModelArts（可选）

顺序不能反：**训模型 → 部署在线服务 → 填 endpoint**。请求/响应契约见
[`docs/architecture/huawei-cloud-integration.md`](../../docs/architecture/huawei-cloud-integration.md) §4。

```dotenv
RISELOOP_MODELARTS_ENDPOINT=<在线服务URL>
RISELOOP_MODELARTS_API_KEY=<鉴权值>
RISELOOP_MODELARTS_AUTH_HEADER=x-auth-token
```

未配置或服务停掉时 `/posture/infer` 返回 503 `modelarts_unavailable`，不影响启动与 ready。

## 9. 客户端接入

`apps/desktop-tauri/src/config/modes.js` 的地址在构建期注入，改地址必须重新构建：

```bash
cd apps/desktop-tauri
VITE_API_BASE=http://<公网IP>:8000 pnpm build
```

PowerShell：`$env:VITE_API_BASE="http://<公网IP>:8000"` 后再 `pnpm build`。

## 10. 排错对照

| 现象 | 原因与处理 |
|---|---|
| 启动即退出，`requires RISELOOP_RDS_DSN` | `cloud_provider=huawei` 但 `.env` 没有 RDS DSN，或 compose 没读到 `.env` |
| 构建报 `No module named 'intervention_engine'` | 构建上下文不是仓库根，或没上传 `packages/intervention-engine`；检查 compose 的 `context: ../..` |
| 构建报 `No module named 'cryptography'` | 用了旧镜像；重新 `build --no-cache` |
| `/health/ready` 503，`redis.configured=false` | `RISELOOP_REDIS_URL` 未填 |
| `/health/ready` 200，但 `store_backend=memory` | `.env` 仍是 `cloud_provider=mock`，属于本地冒烟态 |
| 业务接口 503 `store_unavailable` | RDS 连不上：内网地址、端口、库名、账号或放行规则 |
| 启动日志 `schema init skipped: ConnectionRefusedError` | 同上；进程能起但 ready 会一直 503 |
| 公网 curl 不通，本机 `curl 127.0.0.1:8000` 正常 | Flexus L 实例防火墙没放行 8000，不要去改 VPC 安全组 |
| `session:*` 扫不到 | 还没打过 `/sitting/heartbeat` |
| 客户端连不上 | 公网 IP 变了，`VITE_API_BASE` 是构建期常量，需重新构建 |

## 11. 验收清单

- [ ] 干净机器按 §2–§5 复现，`/health/ready` 返回 200。
- [ ] `/health/capabilities` 显示 `store_backend=sql`、`cloud_provider=huawei`。
- [ ] `smoke.py` 公网跑通，最后一行 `OK`，反馈含 `from_state`/`to_state`/`transition_type`。
- [ ] RDS 里能看到 `users`、`assessments`、`state_transitions` 等表与新记录。
- [ ] 停掉 RDS 后：`/health/ready` 503，业务请求 503 `store_unavailable`，恢复后无需重启即可再通。
- [ ] 删掉 `.env` 里的 RDS DSN 重启：容器按 §6 fail-fast 退出，日志含明确原因。
