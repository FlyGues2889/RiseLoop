# Rise Loop Cloud API

Base URL：本地 `http://127.0.0.1:8000`，线上为 ELB 绑定的 HTTPS 域名。OpenAPI：`/docs`、`/openapi.json`。

## 鉴权

除 `/health/*`、`/auth/*` 外全部需要 `Authorization: Bearer <JWT>`。JWT 由 `cloud-api` 签发，客户端存 OS Keychain，不进 localStorage、不下发原始凭据。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health/live` | 存活探针，不依赖外部 |
| GET | `/health/deps` | 逐项依赖状态（rds/redis/codearts/obs/kms） |
| GET | `/health/ready` | 必需依赖不可达返回 503 |
| POST | `/auth/register` | 注册并返回 token |
| POST | `/auth/login` | 登录并返回 token |
| POST | `/assessment` | 首次评估，返回初始状态与两周计划 |
| POST | `/sitting/heartbeat` | 久坐心跳，返回是否触发及最多 3 个自动匹配动作 |
| POST | `/posture/risk` | 姿态特征 + 久坐/症状 → BRLI、风险等级、方案匹配动作 |
| GET | `/intervention/current` | 当前待执行干预 |
| POST | `/intervention/feedback` | 提交反馈，返回下一状态 |
| GET | `/actions/{state}` | 当前状态可用动作 |
| POST | `/qa/ask` | 知识库问答，返回答案、引用与免责声明 |
| GET | `/review/weekly` | 周度复盘：完成率、疼痛趋势、迁移次数、阻碍分布 |
| POST | `/ingest/wearable` | 预留，返回 501 |

`/sitting/heartbeat` 触发时返回 `actions[]`（最多 3 条）和兼容字段 `action`；每条动作带 `body_parts` 与 `match_reason`，用于说明“为什么匹配”。排序规则：当前状态优先，同状态内按部位重合度，再按时长升序；当前状态匹配不足 2 个时补一个更温和的下一级动作作为备选。

`/posture/risk` 只接收姿态类别、置信度、持续时长与久坐/症状上下文，**不接收原始图像**；返回 BRLI、`risk_level`、`recommended_plan`、`actions[]`（最多 3 条）与 `citations[]`。`citations` 从 `data/knowledge/evidence.json` 按风险因子的 `evidence_ids` 解析，前端直接展示权威来源。低风险返回 `maintain` 且 `actions=[]`，不打断用户。

## 示例

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@riseloop.app","password":"demo-pass-1"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -X POST localhost:8000/assessment \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"body_parts":["neck","shoulder"],"sedentary_minutes":480,"available_minutes":10,"pain_score":2}'

curl -s -X POST localhost:8000/sitting/heartbeat \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"sitting_minutes":50,"threshold_minutes":45}'

curl -s -X POST localhost:8000/qa/ask \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"开会时颈肩紧张，怎么快速缓解？"}'

curl -s "localhost:8000/review/weekly?days=7" -H "Authorization: Bearer $TOKEN"
```

## 安全短路

`/assessment`、`/sitting/heartbeat`、`/intervention/feedback`、`/qa/ask`、`/posture/risk` 由 `SafetyCheckMiddleware` 强制扫描自由文本与 `red_flags[]`（中英双语关键词）。命中返回 **403**：

```json
{
  "error": "safety_short_circuit",
  "red_flags": ["numbness_worse"],
  "red_flag_labels": ["麻木加重"],
  "stop_exercise": true,
  "to_state": "S0",
  "medical_advice": true,
  "disclaimer": "本产品为健康行为指导工具……"
}
```

命中后不进入状态机、不查动作库、不调用 CodeArts。

## 错误码

| 状态码 | 场景 |
|---|---|
| 401 | 缺失或无效 JWT |
| 403 | 安全红线短路 |
| 404 | 无待执行干预 / 动作不存在 |
| 409 | 邮箱已注册 |
| 422 | 参数校验失败（如阈值超出 30–60） |
| 501 | 可穿戴接入未实现 |

## 本地运行（mock 模式，无需云资源）

```bash
pip install -e apps/cloud-api
uvicorn app.main:app --app-dir apps/cloud-api --reload --port 8000
python -m pytest -q
```

问答走 `data/knowledge/articles.json` 检索；`mock` 模式本地生成答案，`huawei` 模式优先调用 CodeArts 规划 Agent，失败回退本地。知识库无命中时明确返回“资料中没有”，不编造。