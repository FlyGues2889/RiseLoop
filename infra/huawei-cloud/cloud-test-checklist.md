# 一次性云链路测试配置清单

## 0. 边界

- 初赛只提交 `docs/submission`（文档 + 宣传片），无答辩、无常驻环境。
- 本清单只服务**一次**公网链路测试：开通 → 验证 → 当天删除。
- 测试完即释放，不作为上云验收环境，也不作为决赛/答辩环境。
- 不购买年付、不购买 ModelArts 专属资源池、不开 OBS/KMS/CCE。

价格口径：华北-北京四（cn-north-4），2026-11-27 控制台实测，仅作预算参考，以下单页为准。

## 0.1 开通前检查（2026-11-27 控制台实查）

| 条件 | 结果 |
|---|---|
| 实名认证 | ✅ 个人认证成功（2026-10-23） |
| 区域 | ✅ 华北-北京四 |
| VPC | ✅ 2 个可用：`vpc-default-smb`（172.31.0.0/16）、`vpc-default`（192.168.0.0/16） |
| 子网 | ✅ `subnet-default-smb` 可用 IP 4,091；`subnet-default` 251 |
| 现有云主机 | ✅ 0 台；Flexus L 未购买 |
| RDS 配额 | ✅ 0/50 实例；PostgreSQL 18 单机 2C4G 可售 |
| DCS 配额 | ✅ 0/160 实例、0/64,000 GB；Redis 7.0 单机 1GB 可售 |
| EIP | ✅ 0 个闲置/待续费；Flexus 自带公网 IP |
| 镜像 | ✅ Ubuntu 24.04 默认可选（22.04+ 均可） |
| 代金券 | ✅ 0 张；积分 1,030，¥100 券（1,000 分）可兑，库存 201 |
| 余额 | ⚠️ 控制台默认掩码，未读取；RDS/DCS 按量约 ¥1.44/3 小时，需保证余额或授信可扣 |

## 1. 配置清单

| 顺序 | 资源 | 规格 | 计费 | 数量 | 预估 |
|---|---|---|---|---|---:|---:|
| 1 | Flexus L 实例 | 2 vCPU / 4 GiB，系统盘 50 GiB，3 Mbps，400 GB/月流量，Ubuntu 22.04 / 24.04 | 包月 | 1 | ¥62.25 |
| 2 | RDS for PostgreSQL | PostgreSQL 18，单机，通用型 2 vCPU / 4 GiB，SSD 40 GiB | 按需 | 1 | ¥0.40/小时 |
| 3 | DCS for Redis | Redis 7.0，基础版，单机，1 GB，x86 | 按需 | 1 | ¥0.08/小时 |
| 4 | 公网流量 | 走 Flexus 自带公网 IP 与 400 GB 流量包 | 超出部分按量 | — | ¥0.80/GB |
| 5 | ModelArts（可选） | CPU 8 vCPU / 32 GiB，公共资源池，在线服务 1 副本 | 按需 | 1 | ¥3.40/小时 |

说明：

- Flexus L 不支持按需，12 小时测试也要付整月 ¥62.25；删除不保证按比例退款。
- RDS 与 DCS 必须和 Flexus 在**同一 VPC、同一子网**，否则云主机连不上内网地址。RDS/DCS 的「快速购买」默认落到 `vpc-default`，Flexus 可能落在 `vpc-default-smb`；下单时改用「自定义购买」，手动选择 Flexus 实例详情里显示的 VPC/子网。
- 本次链路测试默认用 `cloud_provider=mock` 的智能体分支，ModelArts 可不买；要验真实推理再加第 5 项。
- EIP 未绑定实例时有保有费；Flexus 自带公网 IP，不需要单独买 EIP。

## 2. 预算

按 3 小时测试计时：

| 组合 | 金额 |
|---|---:|
| Flexus + RDS + DCS（不含姿态推理） | **¥63.69** |
| 再加 ModelArts 3 小时 | **¥73.89** |
| 流量（远低于 400 GB） | ¥0 |

按 4 小时：¥64.17；含 ModelArts 4 小时：¥77.77。

## 3. 代金券

当前成长中心 1,030 积分，兑换比例 10 积分 = 1 元：

| 方案 | 用券 | 实付（3 小时，不含 ModelArts） | 剩余积分 |
|---|---|---:|---:|
| A（更省积分） | 500 分换 ¥50，抵扣 Flexus 订单 | **约 ¥13.69** | 530 |
| B（按你现在的选择） | 1000 分换 ¥100，抵扣 Flexus 订单 | 约 ¥1.44 | 30 |

- 券 30 天过期，一次支付只能用一张，不能叠加。
- 单用户每天限兑 1 张，部分面额有年度上限，兑换前看弹窗。
- 券只支持按需/包月计费；Flexus 月付、RDS/DCS 按需都符合。
- 方案 B 会把 ¥100 券用在 ¥62.25 的订单上，剩余 ¥37.75 作废，不建议。

## 4. 开通顺序

1. 确认账号余额或代金券已到账。
2. 开通 Flexus L（2C4G，Ubuntu 22.04，1 个月），记录公网 IP。
3. 在同一 VPC/子网开通 RDS PostgreSQL（单机 2C4G 40GB，按需），记录内网地址、库名、账号、口令。
4. 在同一 VPC/子网开通 DCS Redis（7.0 基础版 单机 1GB，按需），记录地址、端口、密码。
5. 在 Flexus 实例防火墙放行：TCP 22（你的公网 IP）、TCP 8000（测试来源 IP 或 0.0.0.0/0）。
6. 部署见 `README.md` §2–§5。

不要在 VPC 安全组里找 8000 的放行；Flexus L 的放行在实例自己的防火墙。

## 5. 必填环境变量

只列变量名，值写进 `infra/docker/.env`，不进仓库、不进镜像：

```dotenv
RISELOOP_ENV=prod
RISELOOP_JWT_SECRET=
RISELOOP_CLOUD_PROVIDER=huawei
RISELOOP_RDS_DSN=
RISELOOP_REDIS_URL=
```

可选（买了 ModelArts 才填）：

```dotenv
RISELOOP_MODELARTS_ENDPOINT=
RISELOOP_MODELARTS_API_KEY=
RISELOOP_MODELARTS_AUTH_HEADER=
```

## 6. 验证

```bash
curl -s http://<公网IP>:8000/health/ready
curl -s http://<公网IP>:8000/health/capabilities
python3 infra/huawei-cloud/smoke.py http://<公网IP>:8000
```

判定：

- `/health/ready` 为 200，`rds.reachable=true`、`redis.reachable=true`。
- `/health/capabilities` 为 `store_backend=sql`、`cloud_provider=huawei`。
- `smoke.py` 最后一行 `OK`，反馈含 `from_state` / `to_state` / `transition_type`。
- RDS 可见 `users`、`assessments`、`state_transitions`；Redis 可见 `session:*`。

失败分支：

| 操作 | 期望 |
|---|---|
| 删掉 `.env` 的 RDS DSN 重启 | 容器退出，日志含 `requires RISELOOP_RDS_DSN` |
| 停掉 RDS | `/health/ready` 503；业务请求 503 `store_unavailable` |
| 停掉 ModelArts | `/posture/infer` 503 `modelarts_unavailable`，客户端不崩 |

## 7. 删除

按顺序，全部在控制台完成：

1. 删除 RDS 实例（按需，删完停止计费）。
2. 删除 DCS 实例。
3. 释放 Flexus L 实例；确认公网 IP 已释放。
4. 检查费用中心：无残留按需资源、无未释放 EIP。

Flexus 的月费已发生，删除不退；RDS/DCS 按小时结算，删除后不再累计。

## 8. 明确不做

- 不买年付 Flexus。
- 不买 ModelArts 专属资源池。
- 不把 5432 / 6379 开到公网。
- 不上 OBS、KMS、CCE。
- 不把本次测试写成「已上云验收」；它只证明公网链路可跑。
