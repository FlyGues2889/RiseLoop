# Phase 0 立项卡：RiseLoop 文献台账

## 文档信息

| 项 | 内容 |
|---|---|
| 工作流 | `docs/theory/literature-workflow.json`（规范：`docs/theory/agent-workflow.md`） |
| 运行 ID | 2026-11-07 |
| 阶段 | Phase 0 立项（已完成）→ Phase 1 检索计划（已完成）→ **停在 G1 等人工确认** |
| 负责角色 | Orchestrator |
| 生成日期 | 2026-11-07 |
| 状态 | 待 G1 确认，未进入采集 |

## 1. 这个工作流要做什么

产出一份**可核验**的权威文献台账，回答三件事：

1. 久坐阈值 45 分钟（可配 30–60）、单次干预 2–10 分钟这些数字从哪来；
2. S0–S3 四个状态的进入/退出条件、回退与降级规则是否有文献依据；
3. 安全短路那 8 条症状红线、以及 `safety-check` 中间件的就医边界，是否有指南支撑。

**不做什么**：不做产品功能、不接入运行时、不新增 MCP 工具、不做医疗诊断依据论证。

## 2. 交付物

| 交付物 | 路径 | 阶段 | 验收方式 |
|---|---|---|---|
| 文献台账 | `data/knowledge/evidence.json` | Phase 6 | `python scripts/validate_evidence.py` 返回 0 error |
| 字段契约 | `data/knowledge/evidence.schema.json` | Phase 0 前置（已建） | 合法 JSON，被校验器读取 |
| 质量报告 | `data/knowledge/qc-report.md` | Phase 6–7 | 含缺口、核验失败项、10% 抽检记录 |
| 证据映射 | `docs/theory/evidence-map.md` | 骨架已建，Phase 6 回填 | 覆盖 PRD 第 5 节全部 BCT 条目 |
| 运行记录 | `docs/theory/run-2026-11-07/` | Phase 0–1 | 本卡 + 检索计划 |

## 3. 主题矩阵

六个主题合计目标 39 条，落在 40±10 区间；其中指南类不少于 3 条。

| 主题 id | 名称 | 目标条数 | 支撑的系统模块 | 检索重点 |
|---|---|---|---|---|
| `sedentary-threshold` | 久坐阈值与打断频率 | 6 | `sitting-trigger` | 久坐时长与全因风险、打断频率、30–60 分钟窗口、久坐行为指南 |
| `micro-break-workplace` | 微休息与工作场所干预 | 7 | `intervention-engine`、`action-library` | 微休息剂量、工间操、sit-stand、工作场所干预依从性 |
| `neck-shoulder` | 颈肩不适 | 7 | `posture-assessment`、`action-library` | 办公人群颈肩痛患病率、拉伸/等长训练、姿势干预 |
| `low-back` | 腰背不适 | 6 | `posture-assessment`、`action-library` | 久坐与下背痛、坐姿骨盆运动、步行打断 |
| `safety-redflag` | 安全红线与就医边界 | 6 | `safety-check` | 颈腰痛红旗征、神经症状、颈动脉/眩晕禁忌、运动禁忌指南 |
| `bct` | 行为改变技术 | 7 | `weekly-review`、`intervention-engine`、`qa-responder` | BCT 分类学、自我监测、目标设定、行动计划、问题解决 |

> 主题与参数的逐条对应见 `docs/theory/evidence-map.md`。缺一条主题，G5 不通过。

## 4. 纳入与排除标准

**纳入**

- 人群：成人（≥18 岁）、办公/久坐人群、一般人群（仅指南类）；
- 类型：指南与立场声明、系统综述/Meta 分析、RCT、队列/横断面（仅用于描述性结论）、官方机构建议；
- 时间：2010-01-01 之后；指南不限发表年，但必须是现行版本（WHO 2020、中国 2021 等）；
- 语言：英文或中文；
- 可核验：DOI / PMID / 官方 URL 至少其一，且题录可解析；
- 相关性：至少命中一个主题。

**排除**

- 动物实验、纯体外/生物力学建模（不足以支撑人体推荐）；
- 以儿童青少年、孕期、住院术后人群为主（人群不符）；
- 药物、手术、注射、影像诊断类研究；
- 会议摘要、预印本、学位论文、二手网页转述、商业软文；
- 题录无法核验，或摘要不可得且无官方页面可替代；
- 同一文献的重复版本（以期刊正式版为准）。

**筛选方式**：题名/摘要两级筛，记录排除原因；安全红线类允许放宽到指南与综述，不强制 RCT。

## 5. 角色与门禁

| 阶段 | 角色 | 产出 | 门禁 |
|---|---|---|---|
| P0 立项 | Orchestrator | 本卡 | — |
| P1 检索计划 | planner | `phase1-search-plan.md` | **G1 人工确认** |
| P2 采集 | harvester | `raw_records` | G2 每条有 id / source_type / doi-pmid-url |
| P3 抽取 | extractor | 标准条目 | — |
| P4 核验 | verifier | pass / fail / unknown + 原因 | G3 verified=true 或 notes 说明 |
| P5 合并 | merger | 去重条目 | — |
| P6 入库 | curator | `evidence.json`、`qc-report.md`、回填 `evidence-map.md` | G4 0 error、DOI/PMID 唯一 |
| P7 覆盖度 | analyst | 缺口清单、补检建议、抽检清单 | G5 覆盖达标 + 10% 抽检 |

任一子 Agent 交接必须返回：`agent / task_id / status / records / issues / next_actions`；`status=blocked` 必须写原因与已试次数。

## 6. 时间与规模

| 项 | 取值 |
|---|---|
| 目标规模 | 39 条（区间 40±10；到 60 条先停做质量复核） |
| 单次运行上限 | 2 小时 |
| 每轮并行子任务 | ≤3 |
| 单批记录 | ≤20 |
| 请求间隔 | ≥1 秒，真实 User-Agent + 联系邮箱 |
| 重试 | 最多 2 次，退避 2s / 5s |
| 计划节点 | G1 确认：2026-11-08；Phase 2–7 完成：2026-11-10 |

## 7. 假设与待确认项

1. `agent-workflow.md` 中的 “SitLoop” 为旧名，产出统一写 **RiseLoop**，原文不改。
2. **联系邮箱未提供**，`literature-workflow.json` 的 User-Agent 里是占位符，须在 G1 补齐（PubMed/Crossref/OpenAlex 的 polite pool 要求）。
3. 知网、万方无公开 API：只登记“需人工导出”，不采集、不爬取；中文指南从国家卫健委官网人工导出。
4. 时间窗按 2010-01-01 起；若某主题候选不足，由 analyst 出补检建议，不降低标准。
5. 本工作流只在离线准备资料，**不改动** `apps/`、`services/agent-orchestrator`、`services/mcp-servers`。

## 8. 风险

| 风险 | 应对 |
|---|---|
| PubMed 限流（429） | 1 req/s + 退避 2s/5s；单来源连续 3 次失败即停该来源 |
| OpenAlex 摘要为倒排索引 | extractor 按 `abstract_inverted_index` 还原，还原失败按“摘要不可得”处理 |
| 中文指南无 API | 人工导出 + `source_type=manual` / `nhc`，`provenance.source_api=manual-export` |
| 摘要不可得导致 `key_finding` 缺失 | 允许 null，notes 写明，G3 仍可通过但计入 QC 报告 |
| 主题覆盖不足 | 不编造、不降标准；G5 卡住并输出补检建议 |
