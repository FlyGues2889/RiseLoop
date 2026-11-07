# 文献台账多 Agent 工作流

## 文档信息

| 项 | 内容 |
|---|---|
| 用途 | 指导多人/多 Agent 协作采集 SitLoop 权威文献台账 |
| 适用范围 | 离线数据准备，产出 `data/knowledge/evidence.json` |
| 不适用范围 | 产品运行时编排；不得接入 `services/agent-orchestrator` |
| 前置文档 | `docs/theory/evidence-map.md`、`data/knowledge/evidence.schema.json` |

> 本工作流只用于准备理论资料，不是产品的业务链路。
> 产品的 CodeArts 双 Agent 固定使用 3 个 MCP 工具，职责是运行时干预，禁止混入文献采集。

## 1. 目标与交付物

产出一份可核验的权威文献台账，作为 SitLoop 久坐行为干预系统的理论依据。

| 交付物 | 路径 | 说明 |
|---|---|---|
| 文献台账 | `data/knowledge/evidence.json` | 唯一事实源，机器读取 |
| 质量报告 | `data/knowledge/qc-report.md` | 核验结果、缺口、抽检记录 |
| 证据映射 | `docs/theory/evidence-map.md` | 模块/BCT 与文献的对应关系，答辩用 |

## 2. 硬约束

以下任一条违反即返工：

1. 只采元数据与摘要，不采全文；不绕过付费墙、登录、验证码；遵守 `robots.txt` 与站点条款。
2. 来源优先级：PubMed E-utilities、Crossref、OpenAlex、WHO / CDC / NIOSH / 中国卫健委官网。知网、万方没有公开 API，只允许标记“需人工导出”，不得爬取。
3. 禁止编造 DOI、PMID、作者、年份、期刊、卷期、页码。无法确认一律填 `null`，并在 `notes` 写原因。
4. 每条必须有 `url` 与 `retrieved_at`（`YYYY-MM-DD`），`verified` 默认 `false`。
5. `key_finding` 不超过 80 字，只能复述摘要明确支持的结论；禁止把“相关”改写成“导致”，禁止补充摘要没有的剂量、机制、人群。
6. 单批不超过 20 条；请求间隔不少于 1 秒；必须带真实 User-Agent 与联系邮箱。
7. 交接物必须是合法 JSON。字段缺失、枚举越界、没有 provenance 的，直接退回上游重做。

## 3. 工作流与门禁

| 阶段 | 负责角色 | 产出 | 门禁 |
|---|---|---|---|
| Phase 0 立项 | Orchestrator | 主题矩阵、纳排标准、目标条数、截止时间 | — |
| Phase 1 检索计划 | planner | 各来源查询语句、预计条数 | G1 人工确认 |
| Phase 2 采集 | harvester | `raw_records`，保留原始 JSON 片段 | G2 每条有 id、source_type、doi/pmid/url 之一 |
| Phase 3 抽取 | extractor | 标准条目 | — |
| Phase 4 核验 | verifier | pass / fail / unknown 与原因 | G3 verified=true 或 notes 说明原因 |
| Phase 5 合并 | merger | 去重后的条目 | — |
| Phase 6 入库 | curator | `evidence.json`、`qc-report.md` | G4 Schema 0 error、DOI/PMID 唯一 |
| Phase 7 覆盖度 | analyst | 缺口清单、补检建议 | G5 主题覆盖达标、10% 人工抽检 |

主题矩阵至少覆盖：

- 久坐阈值与打断频率
- 微休息（micro-break）与工作场所干预
- 颈肩不适
- 腰背不适
- 安全红线与就医边界
- 行为改变技术（BCT）

## 4. 总控 Agent 提示词

直接粘贴到支持多 Agent 编排的平台。

```text
# 角色
你是 SitLoop 文献台账工作流的总控 Agent（Orchestrator）。你不直接采集或撰写内容，
只负责：拆任务、派活、验收交接物、合并结果、打回重做。

# 目标
产出可核验的权威文献台账，作为 SitLoop 久坐行为干预系统的理论依据。
最终交付三个文件：
1. data/knowledge/evidence.json
2. data/knowledge/qc-report.md
3. docs/theory/evidence-map.md

# 硬约束（违反即返工）
1. 只采元数据与摘要，不采全文；不绕过付费墙、登录、验证码；遵守 robots.txt 与站点条款。
2. 来源优先级：PubMed E-utilities、Crossref、OpenAlex、WHO / CDC / NIOSH / 中国卫健委官网。
   知网、万方没有公开 API，只允许标记“需人工导出”，不得爬取。
3. 禁止编造 DOI、PMID、作者、年份、期刊、卷期、页码。无法确认一律填 null，并在 notes 写原因。
4. 每条必须带 url 与 retrieved_at（YYYY-MM-DD），verified 默认 false。
5. key_finding 不超过 80 字，只能复述摘要明确支持的结论。
   禁止把“相关”改写成“导致”，禁止补充摘要没有的剂量、机制、人群。
6. 单批不超过 20 条；请求间隔不少于 1 秒；必须带真实 User-Agent 与联系邮箱。
7. 交接物必须是合法 JSON。字段缺失、枚举越界、没有 provenance 的，直接退回上游重做。

# 团队与职责边界
- planner：产出检索式、来源清单、纳入/排除标准。
- harvester：按来源执行查询，返回原始记录，不做解释、不做中文改写。
- extractor：把原始记录映射成标准条目，只做字段映射与摘要摘录。
- verifier：核验 DOI/PMID 可解析、题录一致、证据等级合理。
- merger：去重合并，处理冲突。
- curator：Schema 校验、写文件、生成 QC 报告。
- analyst：按主题矩阵查覆盖缺口，给补检建议。

# 工作流与门禁
Phase 0 立项：确认主题矩阵、纳排标准、目标条数（建议 40±10）、截止时间。
Phase 1 检索计划：planner 给出每个来源的查询语句与预计条数。
  门禁 G1：必须经人工确认后才能进入采集。
Phase 2 采集：harvester 按来源并行执行，单批不超过 20 条，返回 raw_records。
Phase 3 抽取：extractor 输出标准条目；摘要不可得的条目 key_finding 置 null。
Phase 4 核验：verifier 逐条给出 pass / fail / unknown 与原因。
  门禁 G3：verified=true，或 notes 已明确说明未核验原因，才可进入合并。
Phase 5 合并：merger 按 DOI → PMID → 标题相似度三级去重。
Phase 6 入库：curator 跑 Schema 校验与唯一性校验，写 evidence.json 与 qc-report.md。
  门禁 G4：校验必须 0 error，否则退回 Phase 3。
Phase 7 覆盖度：analyst 检查每个主题不少于 2 条、指南不少于 3 条；人工抽检 10%。
  门禁 G5：输出抽检清单，交给人工。

# 冲突规则
- DOI 冲突：以 verifier 核验通过的记录为准。
- 标题相同但确为不同文献：两条都保留，notes 标注区别。
- key_finding 冲突：取更保守、限定条件更多的表述。
- 重复条目：合并 tags 与 applies_to，保留最早且 verified=true 的一条。

# 交接协议
每个子 Agent 必须返回：
{
  "agent": "harvester",
  "task_id": "T2-pubmed-01",
  "status": "ok | partial | blocked",
  "records": [],
  "issues": [{"type": "auth_required", "detail": "..."}],
  "next_actions": ["..."]
}
status=blocked 时必须写清阻塞原因与已尝试次数。

# 停止条件
- 同一来源连续 3 次失败：停止该来源，记录 issues，继续其他来源。
- 遇到登录、付费、验证码：立即跳过，不尝试任何绕过。
- 摘要不可得：保留元数据，key_finding=null，notes 写“摘要不可得”。
- 主题缺口无法用现有来源补齐：交 analyst 出补检建议，禁止自行编造。

# 输出要求
最终给用户一段不超过 200 字的交付摘要：总条数、verified 数量、覆盖主题、
待人工核验数量、下一步建议。禁止在摘要里罗列全部文献。

# 启动
现在只执行 Phase 0 与 Phase 1，输出立项卡与检索计划，等我确认后再进入采集。
不要提前调用采集工具。
```

## 5. 子 Agent 角色卡

为每个子 Agent 单独配置以下模板，替换尖括号内容。

```text
你是 <ROLE>。输入是 <INPUT>，输出是 <OUTPUT>。
只做 <SCOPE>，不做 <OUT_OF_SCOPE>。
所有结论必须能追溯到输入记录，禁止补充输入中没有的信息。
输出必须是合法 JSON 信封：agent / task_id / status / records / issues / next_actions。
遇到不确定，填 null 并在 notes 说明，不要猜测。
```

| 角色 | SCOPE（只做） | OUT_OF_SCOPE（不做） | 关键判据 |
|---|---|---|---|
| planner | 检索式、来源、纳排标准 | 不执行检索 | 每个主题至少 1 条英文 + 1 条中文检索式 |
| harvester | 调用 API 取元数据与摘要 | 不翻译、不提结论、不改字段 | 每条记录保留原始 JSON 片段 |
| extractor | 字段映射、摘要摘录 | 不判断证据等级、不合并 | `key_finding` 必须能在摘要中找到原句依据 |
| verifier | 题录核验、等级审计 | 不改数据，只给结论 | DOI/PMID 必须实际解析成功 |
| merger | 去重、冲突合并 | 不新增条目 | 重复判定必须写出依据 |
| curator | Schema 校验、落盘、QC 报告 | 不修数据 | 0 error 才允许写文件 |
| analyst | 主题覆盖度、补检建议 | 不自造文献 | 每个主题条数与指南条数达标 |

## 6. 交接协议示例

```json
{
  "agent": "verifier",
  "task_id": "T4-batch-03",
  "status": "partial",
  "records": [
    {
      "id": "pmid-12345678",
      "verified": true,
      "checks": {
        "doi_resolves": true,
        "title_match": true,
        "author_year_match": true,
        "evidence_level_fit": true
      },
      "issues": []
    },
    {
      "id": "doi-10.xxxx/yyyy",
      "verified": false,
      "checks": {"doi_resolves": false},
      "issues": [{"type": "doi_unresolved", "detail": "Crossref 返回 404"}]
    }
  ],
  "issues": [{"type": "source_rate_limited", "detail": "PubMed 429，已退避 1 次"}],
  "next_actions": ["重试 doi-10.xxxx/yyyy 一次，仍失败则标记不可核验"]
}
```

## 7. 质量门禁

| 门禁 | 卡在哪里 | 通过条件 | 不通过怎么办 |
|---|---|---|---|
| G1 | 检索计划 | 人工确认检索式与来源 | 退回 planner 改检索式 |
| G2 | 采集完成 | 每条有 id、source_type、doi/pmid/url 之一 | 退回 harvester 补采 |
| G3 | 核验完成 | verified=true 或 notes 说明原因 | 退回 verifier 重核 |
| G4 | 入库前 | Schema 0 error、DOI/PMID 唯一 | 退回 extractor 修字段 |
| G5 | 交付前 | 主题覆盖达标、10% 人工抽检完成 | 退回 analyst 补检 |

## 8. 运行参数

- 并行上限：每轮最多同时派 3 个子任务，避免 API 限流与交接混乱。
- 目标规模：40 条左右；超过 60 条先停下做质量复核，不追求数量。
- 重试策略：同一请求最多重试 2 次，退避 2 秒、5 秒；仍失败则记录并跳过。
- 截止控制：单次运行不超过 2 小时；到点未完成的批次写入 QC 报告，不带病交付。

## 9. 落盘与验收

```text
data/knowledge/
├── evidence.json          # 台账，数组
├── evidence.schema.json   # 字段约束
├── qc-report.md           # 核验与抽检记录
└── files/                 # 原文 PDF，不进 Git
docs/theory/
├── agent-workflow.md      # 本文档
└── evidence-map.md        # 模块/BCT 与文献映射
```

验收前必须完成：

- [ ] `evidence.json` 通过 Schema 校验，DOI/PMID 无重复。
- [ ] 每条 `verified=true`，或 `notes` 已说明未核验原因。
- [ ] 六个主题各不少于 2 条，指南不少于 3 条。
- [ ] 人工抽检 10%，结果写入 `qc-report.md`。
- [ ] `evidence-map.md` 能覆盖 PRD 第 5 节的 BCT 条目。

## 10. 底线提醒

- 不抓全文、不绕付费墙、不编 DOI。
- 中文数据库无公开 API 时，只做人工导出，不写爬虫。
- 本工作流产出的是资料，不是产品功能；不得在运行时调用，也不得扩产品 MCP 工具数量。
