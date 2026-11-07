# G1 门禁记录：检索计划确认（匿名模式）

## 文档信息

| 项 | 内容 |
|---|---|
| 门禁 | G1（Phase 1 → Phase 2） |
| 确认单 | `docs/theory/run-2026-11-07/g1-plan.json`（机器判定，Phase 2 唯一权威清单） |
| 可读版 | `docs/theory/run-2026-11-07/phase1-search-plan.md` |
| 判定工具 | `python scripts/literature/gate_check.py` |
| 判定时间 | 2026-11-07 |
| 结论 | **通过**（`gate_check.py` exit 0），采集身份为匿名模式 |

## 1. 确认结论

| 项 | 结论 |
|---|---|
| 主题与目标条数 | 6 / 7 / 7 / 6 / 6 / 7，合计 39 条（区间 30–50），指南下限 3 条 |
| 检索式 | 每主题 PubMed / OpenAlex / Crossref / 中文人工四类齐备；T1、T5、T6 按 D3 微调 |
| 来源 | 8 个来源，均已声明速率；卫健委、知网万方 `crawl_allowed=false` |
| 时间窗 | 2010-01-01 起，指南须现行版本 |
| 分批 | B1/B2/B3 三批，每批 ≤20 条记录 |
| 采集身份 | **匿名**：`contact=null`，User-Agent 仅含工具名，1 req/s，不进入 polite pool |
| 确认人 / 时间 | RiseLoop 项目负责人（GitHub @FlyGues2889） / 2026-11-07 |

## 2. 匿名模式定义

| 约束 | 取值 | 说明 |
|---|---|---|
| `api_mode` | `anonymous` | 与 `identified` 二选一，由 `g1-plan.json` 声明 |
| `contact` | `null` | 不采集、不发送邮箱；Schema 中该字段为可选，匿名时固定 null |
| `user_agent` | `RiseLoop-lit-ledger/1.0` | 不含 `mailto`、不含 `@`，校验器会检查 |
| `rate_limit_per_second` | 1 | 所有 api / web-read 来源同速；`gate_check.py` 拒绝 >1 |
| `batch_size` | 20 | 单批记录上限 |
| polite pool | 不启用 | Crossref / OpenAlex 走公共池，限流概率高于实名 |

**已知代价**：匿名请求在 Crossref / OpenAlex 上更容易触发 429；PubMed 亦然（按 IP 限流）。因此加兜底规则，见第 4 节。

## 3. 机器判定输出（2026-11-07）

```text
[PASS] status=confirmed
[PASS] confirmed_by=RiseLoop 项目负责人（GitHub @FlyGues2889）
[PASS] confirmed_at=2026-11-07
[PASS] api_mode=anonymous，contact=null
[PASS] rate_limit_per_second=1
[PASS] batch_size=20
[PASS] user_agent=RiseLoop-lit-ledger/1.0
[PASS] 六主题齐全
[PASS] 目标合计 39 条（区间 30–50）
[PASS] 来源清单与模式一致
G1 通过 — 可进入 Phase 2 采集（匿名模式，1 req/s，单批 ≤20）
```

连通性冒烟：`python scripts/literature/smoke_pubmed.py` → HTTP 200，1.12 s，T1 检索式命中 710 条，返回 PMID 42925061、42841540。记录见 `g1-smoke-test.md`。

## 4. 匿名模式兜底规则

1. **连续两次 403 / 429**：立即暂停全部采集，不再对该来源重试；把状态写入 `data/knowledge/qc-report.md`。
2. 暂停后要求提供项目邮箱，按 `identified` 模式重新签字：

   ```bash
   python scripts/literature/gate_check.py --sign --by "<确认人>" --mode identified --email "<邮箱>"
   python scripts/literature/gate_check.py
   ```

3. 单次运行超过 2 小时或同一来源连续 3 次失败：停该来源、记录 issues、继续其他来源，不带病交付。
4. 匿名模式不得用于绕过站点条款；仍遵守 robots.txt、不抓全文、不绕付费墙与验证码。

## 5. 禁止的放行方式

- **不得**用 `example.com` / `noreply` 等占位域名凑 `identified` 模式；匿名模式就是 `contact=null`，不许写假邮箱。
- **不得**由子 Agent 自行改 `status=confirmed`；签字只接受人提供的署名（实名模式另需真实邮箱）。
- **不得**跳过 `gate_check.py` 直接联网采集：脚本非 0 时采集入口必须拒绝运行。
- **不得**把本工作流接入 `services/agent-orchestrator` 或产品运行时。

## 6. 影响面

G1 通过后仍有以下前置未完成，进入 Phase 2 前需逐项确认：

- 采集执行脚本尚未落地（当前只有 `smoke_pubmed.py` 单请求冒烟）；
- `data/knowledge/evidence.json` 尚未生成（Phase 3–6 产出，禁止先建空文件）；
- 六主题已入库条数均为 0，指南 0/3。
