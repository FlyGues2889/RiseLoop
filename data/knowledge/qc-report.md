# QC 报告：RiseLoop 文献台账

## 文档信息

| 项 | 内容 |
|---|---|
| 运行 ID | 2026-11-07 |
| 工作流 | `docs/theory/literature-workflow.json`（规范：`docs/theory/agent-workflow.md`） |
| 采集身份 | **匿名模式（anonymous）**：`contact=null`，User-Agent `RiseLoop-lit-ledger/1.0`，1 req/s，单批 ≤20，不启用 polite pool |
| 当前阶段 | Phase 0–1 完成，G1 通过；Phase 2 采集未开始 |
| 台账状态 | `evidence.json` 尚未生成（阶段未到，不建空文件） |
| 更新方式 | 每批采集后追加一节，Phase 7 补齐抽检记录 |

## 1. 匿名模式声明

本次采集不使用、不收集联系人邮箱。匿名模式的直接代价是 Crossref / OpenAlex 走公共池，限流概率高于实名；PubMed 按 IP 限流。为控制风险，工作流固定 1 req/s、单批 ≤20 条、单次运行 ≤2 小时。

## 2. 兜底规则（匿名模式）

1. **连续两次 403 / 429** → 立即暂停全部采集，不再重试该来源，并在本报告登记时间、来源、状态码。
2. 暂停后要求提供项目邮箱，按实名模式重新签字后重试：
   `python scripts/literature/gate_check.py --sign --by "<确认人>" --mode identified --email "<邮箱>"`
3. 同一来源连续 3 次失败 → 停该来源、记 issues、继续其他来源。
4. 运行超过 2 小时 → 未完成批次写入本报告，不带病交付。

## 3. 门禁执行记录

| 门禁 | 时间 | 结果 | 依据 |
|---|---|---|---|
| G1 检索计划 | 2026-11-07 | 通过（匿名） | `gate_check.py` exit 0；`g1-gate-record.md` |
| G1 连通性冒烟 | 2026-11-07 | 通过 | PubMed HTTP 200，1.12 s，count=710，见 `g1-smoke-test.md` |
| G2 采集完整性 | 未执行 | — | Phase 2 未开始 |
| G3 核验 | 未执行 | — | — |
| G4 入库校验 | 未执行 | — | `python scripts/validate_evidence.py` 待跑 |
| G5 覆盖度 | 未执行 | — | — |

## 4. 主题覆盖与缺口

| 主题 | 目标 | 已入库 | 指南 | 缺口 |
|---|---|---|---|---|
| `sedentary-threshold` | 6 | 0 | 0 | 6 |
| `micro-break-workplace` | 7 | 0 | 0 | 7 |
| `neck-shoulder` | 7 | 0 | 0 | 7 |
| `low-back` | 6 | 0 | 0 | 6 |
| `safety-redflag` | 6 | 0 | 0 | 6 |
| `bct` | 7 | 0 | 0 | 7 |
| 合计 | 39（区间 30–50） | 0 | 0 / 3 | 39 |

## 5. 核验失败与异常

暂无。Phase 2 起逐批登记：来源、任务 ID、失败类型（`rate_limited` / `doi_unresolved` / `auth_required` / `abstract_missing`）、已试次数、处置。

## 6. 人工抽检

未开始。G5 要求按 10% 抽样（39 条约 4 条），抽检清单与结论在本节补齐。

## 7. 当前结论

G1 已通过、链路已打通，但台账为空。下一步是 Phase 2 采集（B1：T1 + T5 + 指南定向），需先落地采集脚本；在脚本产出并通过 G2 前，本报告不宣称任何文献结论。
