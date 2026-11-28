# AI 建议链路测试清单

> 目标：确认“姿态推理 → BRLI → 推荐动作 → 问答 → 周复盘”在公网云环境里真的起作用，而不是 mock 或前端假数据。
> 适用：2026-11-28 部署的 `cloud_provider=huawei` 环境。接口地址用 `http://<ECS 公网 IP>:8000`。

## 1. 一键检查

```powershell
D:\Anaconda\python.exe infra\huawei-cloud\ai_checks.py http://<ECS 公网 IP>:8000
```

脚本只依赖标准库，会注册一个 `ai-check-<时间戳>@riseloop.app` 临时账号并写入测试数据。最后一行必须是：

```text
OK: AI 建议链路全部通过
```

2026-11-28 实测结果：

```text
[1] health              ready, provider=huawei, store=sql, modelarts=True, maas=True
[2] auth                ai-check-...@riseloop.app
[3] assessment          state=S1 risk=low
[4] heartbeat           triggered, actions=3, first=s1-calf-pump (2 min)
[5] baseline            frames=3 head_scale=0.6
[6] posture infer       posture=undetermined conf=0.999 source=huawei latency=65.09ms brli=0.2408
[7] risk suggestion     brli=0.5841 level=high plan=standard actions=3 citations=8
[8] qa hit              model=pangu citations=['knowledge:neck-shoulder-break', 'knowledge:micro-break-timing']
[9] qa miss             no citations, answer=资料中没有直接对应的条目...
[10] feedback           S1 -> S1 hold
[11] weekly review      interventions=1 posture_samples=1 suggestions=1 highlights=1
[12] safety short      403, 推荐被拦截
```

## 2. 接口级判定

| # | 能力 | 请求 | 通过标准 | 失败含义 |
|---|---|---|---|---|
| 1 | 云环境 | `GET /health/capabilities` | `cloud_provider=huawei`、`store_backend=sql`、`modelarts.configured=true`、`maas.configured=true` | 还是 mock/内存，先修部署；`maas=false` 只影响问答生成，不影响姿态 |
| 2 | 姿态推理 | `POST /posture/infer` | 200；`source=huawei`；有 `latency_ms`、`features`、`risk` | 503 表示 ModelArts 停止/超时/证书失败；`source=mock` 表示没走真实模型 |
| 3 | 风险融合 | `POST /posture/risk` | `brli` 有值；`factors` 4 个；`citations` ≥1 | 只返回低风险 `maintain` 时检查输入是否足够高 |
| 4 | 推荐动作 | 同上 | `recommended_plan` 不是 `maintain`；`actions` ≥1；动作带 `steps` 与 `match_reason` | 无动作说明当前状态/部位匹配不到 |
| 5 | 久坐干预 | `POST /sitting/heartbeat`（`force=true`） | `triggered=true`；`actions` 1–3 条 | 检查阈值、冷却与动作库 |
| 6 | 问答命中 | `POST /qa/ask` 问颈肩问题 | `citations` 非空；答案包含具体动作 | 空引用说明知识库未匹配或未打包进镜像 |
| 6.1 | 问答生成 | 同上看 `ai_checks.py` 的 `[8]` | `model=pangu`；回答 1–2 秒；引用非空 | `model=template` 表示 MaaS 未配置或调用失败，已退回知识库原文 |
| 7 | 问答兜底 | `POST /qa/ask` 问无关问题 | `citations=[]`；答案以“资料中没有”开头 | 编造答案说明检索逻辑被绕过 |
| 8 | 周复盘 | `GET /review/weekly` | `interventions.total≥1`；`posture.samples≥1`；`suggestions` 非空 | 没有数据说明反馈/姿态摘要没落库 |
| 9 | 安全短路 | `POST /intervention/feedback` 带 `red_flags` | 403；不返回动作 | 200 说明中间件漏拦，必须修 |

## 3. 客户端界面检查

启动客户端并指向云端：

```powershell
cd apps\desktop-tauri
$env:VITE_API_BASE="http://<ECS 公网 IP>:8000"
pnpm tauri dev
```

| 界面 | 操作 | 应看到 |
|---|---|---|
| 登录 | 注册/登录 | 只有邮箱登录，无本地模式入口 |
| 评估 | 颈/肩、疼痛 3 分 | 初始状态与两周计划 |
| 久坐计时 | 点「现在开始」 | 立即出动作卡，不需等 45 分钟 |
| 姿态检查 | 打开摄像头，先「校准坐姿 · 10 秒」 | 状态显示已连接云端；结果区出现姿态、置信度、负荷与建议方案 |
| 风险报告 | 动作卡下方「风险与姿势报告」 | 风险等级、BRLI、最近姿势/置信度、建议方案、最近风险姿势 |
| 问答 | 问“开会太久颈肩紧张怎么办” | 回答带 1–2 条引用，不编造 |
| 近 7 天 | 打开周报 | 完成率、活动次数、疼痛趋势、姿态块、建议列表 |
| 红旗 | 反馈里选放射痛/麻木加重 | 弹就医提示，停止动作推荐 |

判定原则：界面上出现具体姿态类别、BRLI 和动作，并且服务端 `/posture/infer` 同时看到 `source=huawei`，才算 AI 建议链路真的通了；只有界面数字、没有服务端调用，视为前端假数据。

## 4. 降级也要测

| 操作 | 期望 |
|---|---|
| 停止 ModelArts 在线服务 | `/posture/infer` 503 `modelarts_unavailable`；客户端提示云端不可用，不显示假类别 |
| 断网 | 客户端提示连接失败，不崩；恢复后可继续 |
| 关摄像头 | 姿态区显示权限/设备提示，不影响其他功能 |
| 数据库不可达 | `/health/ready` 503；业务 503 `store_unavailable` |

## 5. 口径说明

- `posture=undetermined` 不代表失败：脚本发的是合成中立关键点，模型判定为“关键点不足/不可判”属正常；真实摄像头帧应得到 baseline / forward_head / lateral_tilt 之一。
- 问答是“知识库检索 → MaaS 盘古生成 → 引用校验”：只有命中条目才调用模型；未命中不调用、不编造；未配置、超时、非 2xx 或空回复回退知识库原文。
- 盘古只收到问题、当前阶段与命中条目，不收到用户标识、健康档案或日志；回答 ≤120 字，不做诊断、用药、康复周期或影像解读。
- 模型为 `openpangu-2.0-flash`（MaaS 预置模型，服务在西南-贵阳一，北京四跨区调用）；`enable_thinking=false` 时约 1.5s / 240 tokens，开启思考约 10s / 800+ tokens。
- 周报的 `suggestions` 是规则生成，不是大模型；姿态分类、BRLI、状态迁移与安全短路仍由纯 Python / 状态机完成，未外移给大模型。
- 姿态模型只有 14 人、单一设备/场景，`source=huawei` 证明链路真实，不等于精度达标。
- 脚本会留下测试账号与记录，测试库可忽略；正式环境需清理。
