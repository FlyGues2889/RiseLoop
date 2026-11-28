# 华为云接入（Rise Loop）

三件核心，其余围绕它们按需接入：

- **DCS for Redis** —— 实时状态
- **RDS for PostgreSQL** —— 事实数据
- **ModelArts 在线服务** —— 姿态推理（AI 创新的唯一硬证据）

部署步骤见 [`infra/huawei-cloud/README.md`](../../infra/huawei-cloud/README.md)。本文只回答三件事：接什么、契约长什么样、怎么算验完。

## 1. 接入清单

| 服务 | 用途 | 定位 | 代码 | 当前状态 |
|---|---|---|---|---|
| DCS for Redis | `session:*`、`sitting:*`、`pending_intervention:*`、`safety:*` 四类实时 Key | 核心，可降级 | `app/cloud/dcs.py` | `ping/get/set/delete` 已实现 |
| RDS for PostgreSQL | 用户、评估、迁移、执行记录、问答日志、安全事件、姿态摘要 | 核心 | `app/cloud/rds.py` | 连接与 `SELECT 1` 探活已实现 |
| ModelArts 在线服务 | 33 关键点 → 姿态四分类 + 置信度 | 核心（AI） | `app/cloud/modelarts.py` | v3 head A 版已部署（2026-11-28）：16 维、3,300 参数，OOF macro-F1 0.7759；`/posture/infer` 实测 `source=huawei`、约 101 ms；调用、超时、显式降级已实现 |
| 云主机（Linux + Docker Compose） | 跑 `cloud-api` 容器 | 必须 | `infra/docker/` | 已部署 Flexus L（2026-11-28） |
| IAM 子用户 + AK/SK | OBS/KMS 签名，最小权限 | 必须（间接） | 无（IAM 侧配置） | 已创建访问密钥，AK/SK 只存 DEW 凭据 |
| OBS | 安装包、演示视频分发 | 推荐 | `app/cloud/obs.py` | 已建桶 `riseloop-models-20261128` 用于模型包；业务分发未接线 |
| KMS | 健康字段加密 | 可选 | `app/cloud/kms.py` | AES-256-GCM 已实现 |
| CodeArts | 代码补全、流水线 | 研发工具，**不进运行时** | 无 | — |
| AgentArts | 问答/方案解释的编排替身 | 可选 | 待接入 | 未接 |
| ELB + SSL 证书 | 域名与 HTTPS | 不做（直接用 `host:8000`） | — | — |
| LTS / APM | 日志与链路追踪 | 暂不上 | — | — |

## 2. 三件核心为什么不能省

**DCS**：实时状态是状态机的输入，也是双存储结构的其中一半。它是**可降级项**：不配 `RISELOOP_REDIS_URL` 时代码自动降级到进程内存（`app/repositories/sql_store.py:365-380`），功能不中断，只是重启后实时状态丢失。

**RDS**：事实数据是可追溯的基础。托管实例自带备份与快照，容器内自建 PostgreSQL 要自己承担备份与恢复；两条路代码一致，只改 `.env` 里的 DSN。

**ModelArts**：`/posture/infer` 已接 `app/cloud/modelarts.py`。2026-11-28 已部署 v3 head A 版在线服务，`source=huawei`，端到端约 101 ms；模型输入 16 维（公开 9 特征 + 7 个头部几何 delta），个人基线经 `/posture/baseline` 取 10 字段中位数。`mock` 几何规则只在本地联调使用，可用 `RISELOOP_POSTURE_MOCK_POLICY=unavailable` 关闭。赛题要求 AI 创新，这一件是唯一能拿出真实推理结果的环节；精度仍受 14 人样本限制，不能对外写成真实准确率。

## 3. 接入前置条件

**Region 与网络**：云主机、DCS、RDS、ModelArts 放同一 Region。实测为华北-北京四，云主机、RDS、DCS 同处 `vpc-default-smb` / `subnet-default-smb`。云主机入站放行 TCP 8000——Flexus L 在实例自己的防火墙里放行，不在 VPC 安全组里；RDS 5432 与 DCS 6379 只对云主机私网地址放行。

### 3.1 DCS for Redis

- 版本 Redis 6 / 7，开启访问密码，不用免密。
- 6379 只对云主机私网地址放行，不对公网开放。
- 需要记录：连接地址（形如 `xxx.dcs.huaweicloud.com`）、端口 6379、密码。
- 连通性验证（在云主机上）：`docker run --rm -it redis:7-alpine redis-cli -h <地址> -p 6379 -a '<密码>' ping` → `PONG`。

### 3.2 RDS for PostgreSQL

- 协议与 PostgreSQL 兼容，`asyncpg` 驱动不用改。
- 5432 只对云主机私网地址放行。
- 需要记录：内网地址、端口 5432、库名 `riseloop`、账号、口令。
- 连通性验证：`psql "host=<内网地址> port=5432 dbname=riseloop user=<用户>" -c "select 1"`。
- 表结构在服务启动时由 `create_schema` 建（`app/main.py`），无需手工建表。
- `cloud_provider=huawei` 但 RDS 配置缺失时进程启动即失败，不退回内存存储（`app/main.py`）。

### 3.3 ModelArts 在线服务

分三步，顺序不能反：**有模型 → 有服务 → 有 endpoint**。2026-11-28 已完成：v3 head A 版打包上传 OBS，部署为 1 副本在线服务，`source=huawei`。实测坑位：DEW 凭据必须是 `accessKeyId` / `secretAccessKey`；挂载路径 `/home/ma-user/infer/model/1`；容器协议 HTTP、端口 8080；启动命令要带 `TF_MODEL_ARGS`；endpoint 末尾带 `/`。

1. **训模型**：v1（特征契约 v2）是合成数据历史包，输入 5 个派生特征，B 版另加 33 点坐标共 137 维；报告在 `scripts/modelarts/reports/v1/`。**v3 改为 9 个公开 2D 特征 + 模型内部 7 个头部几何 delta（A 版 16 维、3,300 参数；B 版 148 维），部署包按 A 版生成并已于 2026-11-28 部署；指标仍不能当作真实准确率。**
2. **样本**：`reports/v1/` 仍来自 1440 帧合成关键点（12 受试者、seed 20261117、`framing=upper_body`），只验证管线；真实采集第一批已有 14 名受试者、3,974 帧带段落标签（2026-11-26，去重后），已按 v3 重生成并通过 `dataset_check`；v3 报告在 `scripts/modelarts/reports/v3-loso-head/`，A 版 forward_head F1 0.7142、召回 0.649，仍未达到对外发布条件。
3. **部署**：把 `customize_service.py`、`posture_runtime.py`、`model.py`、`model.pt`、`feature_spec.json` 打成模型包，上传 OBS 后部署为**在线服务**（CPU、1 副本）。2026-11-28 实测：OBS 桶 `riseloop-models-20261128`，服务 `service-af70`，8C32G，挂载 `/home/ma-user/infer/model/1`，调用地址见 `infra/huawei-cloud/deployed-config.md`。可用 `python scripts/modelarts/package_model.py --artifacts data/posture/reports/v3-loso-head --out <上传目录>` 生成包与 `MANIFEST.json`。
4. **填入 `.env`**：见 §4。

## 4. ModelArts 调用契约

适配层固定在 `apps/cloud-api/app/cloud/modelarts.py`，业务代码不直连。

**请求**（`ModelArtsService.predict`，`modelarts.py:142`）：

```http
POST <RISELOOP_MODELARTS_ENDPOINT>
Content-Type: application/json
X-Auth-Token: <RISELOOP_MODELARTS_API_KEY>

{"model": "riseloop-posture-v3", "source": "mediapipe-pose-33",
 "keypoints": [{"name": "nose", "x": 0.51, "y": 0.42, "z": 0.0, "visibility": 0.99}, ...],
 "baseline": {"shoulder_tilt_deg": 0.0, "neck_ratio": 0.67, "head_offset_ratio": 0.0,
              "head_scale": 0.386, "eye_scale": 0.208, "face_height": 0.106,
              "ear_shoulder_y": 0.775, "head_roll_deg": 1.23, "nose_ear_y": 0.268,
              "ear_mid_offset": -0.0045},
 "features": {"shoulder_tilt_deg": 3.2, "neck_ratio": 0.58, "neck_ratio_delta": -0.09, ...},
 "project_id": "<可选>"}
```

> **包络已实测**：2026-11-28 的真实调用为裸 JSON，ModelArts 直接交给 `customize_service`，未包 `{"data": ...}`；响应由 `parse_prediction` 正常解析。

**响应**：三种都能解析（`parse_prediction`，`modelarts.py:63`）——`{"posture": "forward_head", "confidence": 0.82}`、`{"label": ..., "confidence": ...}`、或 `{"probabilities": {"baseline": 0.1, ...}}`。

**鉴权头**：`RISELOOP_MODELARTS_AUTH_HEADER` 四选一（`x-auth-token` 默认 / `authorization` / `x-api-key` / `x-apig-appcode`）。实测 API KEY 认证使用 `authorization: Bearer <API Key>`；`x-apig-appcode` 不适用。HTTPS 证书默认校验；IP + 自签证书的测试环境才设 `RISELOOP_MODELARTS_TLS_VERIFY=false`。

**失败语义**：超时 2.5 秒（`RISELOOP_MODELARTS_TIMEOUT_SECONDS`）或 HTTP 非 2xx → 抛 `ModelArtsError` → `/posture/infer` 返回 503 `modelarts_unavailable` → 端侧降级。**不伪造云端结果。**

## 5. 环境变量

```bash
RISELOOP_CLOUD_PROVIDER=huawei          # 只有 huawei 才真连 DCS/RDS/ModelArts
RISELOOP_RDS_DSN=postgresql+asyncpg://<用户>:<口令>@<RDS内网地址>:5432/riseloop
RISELOOP_REDIS_URL=redis://:<DCS密码>@<DCS地址>:6379/0
RISELOOP_MODELARTS_ENDPOINT=https://<在线服务地址>/v2/infer/<服务ID>/
RISELOOP_MODELARTS_API_KEY=<API Key>
RISELOOP_MODELARTS_AUTH_HEADER=authorization
RISELOOP_MODELARTS_MODEL_NAME=serve
RISELOOP_MODELARTS_TLS_VERIFY=false      # 仅 IP + 自签证书的测试环境
RISELOOP_POSTURE_MOCK_POLICY=heuristic   # 演示前改 unavailable，让 /posture/infer 明确 503
```

其余 `RISELOOP_OBS_*`、`RISELOOP_KMS_*`、`RISELOOP_JWT_SECRET` 见 `apps/cloud-api/.env.example`。`.env` 不进仓库、不打进镜像。

`huawei` 模式下 `RISELOOP_RDS_DSN` 是硬前置：缺失则启动失败（`RuntimeError`，退出码非 0），不退回内存存储。只缺 DCS 时可以启动，实时状态落进程内存，重启即丢。

## 6. 验证

| 端点 | 看什么 |
|---|---|
| `GET /health/live` | 进程活着，不依赖外部 |
| `GET /health/deps` | 六项明细，`redis.provider=huawei-dcs`、`rds.provider=huawei-rds`、`modelarts.configured=true`（2026-11-28 实测） |
| `GET /health/capabilities` | `store_backend=sql` |
| `POST /posture/infer` | 返回真实 `posture` + `confidence` + `source=huawei` |

就绪口径：`/health/ready` 只要求 `rds` + `redis`（`app/api/routes/health.py:13`）。ModelArts 未配置不阻塞启动，但 `/posture/infer` 会明确返回 503——这是有意的分离，避免模型没就绪就整体不可用。

RDS 运行中失联时，`/health/ready` 返回 503，业务请求返回 `503 {"detail":"store_unavailable"}`，客户端按 ready 状态判定即可；不会返回带堆栈的 500，也不会把 DSN 写进响应。

## 7. 接入阶段

| 阶段 | 内容 | 能验证什么 |
|---|---|---|
| 最小可跑 | 云主机 + DCS | 公网链路、实时状态双存储 |
| 完整证据 | 上面 + RDS + ModelArts | 事实数据持久化、真实姿态推理 |
| 加分项 | 上面 + OBS + KMS | 分发与健康字段加密 |

每阶段用 §6 的端点自检。未接入的服务在 `/health/deps` 显示为未配置，不影响其他链路。

初赛阶段已按「云主机 + RDS + DCS + ModelArts + OBS」完成一次限时测试（2026-11-28），测完应按清单释放；KMS 不在本次范围。实测配置见 [`infra/huawei-cloud/deployed-config.md`](../../infra/huawei-cloud/deployed-config.md)，开通前配置与预算见 [`cloud-test-checklist.md`](../../infra/huawei-cloud/cloud-test-checklist.md)。

## 8. 安全与合规

- 健康数据只进 RDS；Redis 只放实时状态，不落完整档案。
- AK/SK、ModelArts Token 只在服务端；Tauri 端禁止持有。
- 安全组最小放行：6379/5432 仅内网，公网只开 8000（或后续 443）。
- 日志不打印 DSN、密码、关键点原始数组。

## 9. 验收对照

- [x] DCS 已接入，`/health/deps` 中 `redis.provider=huawei-dcs` 且 `reachable=true`。
- [x] Redis 里能 `--scan --pattern 'session:*'` 看到真实 key。
- [x] RDS 里重启容器后数据仍在；`/health/capabilities` 显示 `store_backend=sql`。
- [x] `/posture/infer` 返回 `source=huawei`，且在线服务侧能看到调用量与延迟。
- [ ] 模型包版本对得上：响应含 `posture` / `confidence` / `probabilities`，四类齐全，与 `feature_spec.json` 的类别顺序一致。
- [x] 首次真实调用确认请求包络（裸 JSON vs `{"data": ...}`），差异已收口在 `modelarts.py`。
- [ ] 停掉 ModelArts 服务后 `/posture/infer` 返回 503 并提示降级，客户端不崩。
- [ ] 断网、关摄像头、ModelArts 超时三种降级都能演示。
