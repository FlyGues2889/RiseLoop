# Phase 1 检索计划：RiseLoop 文献台账

## 文档信息

| 项 | 内容 |
|---|---|
| 阶段 | Phase 1（已完成），G1 已通过（2026-11-07，匿名模式） |
| 上游 | `phase0-brief.md`（主题矩阵、纳排标准、目标 39 条） |
| 下游 | Phase 2 采集（G1 通过前禁止任何检索调用） |
| 生成日期 | 2026-11-07 |
| 执行约束 | 单批 ≤20 条记录；请求间隔 ≥1s；重试 2 次（退避 2s/5s）；单次运行 ≤2h |

## 1. 来源与访问方式

| 来源 | 访问方式 | 取哪些字段 | 速率 | 优先级 |
|---|---|---|---|---|
| PubMed E-utilities | `esearch` + `efetch`，`retmode=json` | 题录 + 摘要 | 1 req/s（无 key） | 1 |
| Crossref | `api.crossref.org/works` | 题录 + 摘要（部分有） | 1 req/s + mailto | 2 |
| OpenAlex | `api.openalex.org/works` | 题录 + `abstract_inverted_index`（需还原） | 1 req/s + mailto | 3 |
| WHO 官网 | 页面只读，URL 直取 | 指南题录 + key messages | 1 req/s | 1 |
| CDC 官网 | 页面只读 | 建议条目 | 1 req/s | 2 |
| NIOSH 官网 | 页面只读 | 工效学建议 | 1 req/s | 2 |
| 国家卫健委 | **人工导出**，不爬 | 中文指南题录 | — | 1 |
| 知网 / 万方 | **只标记“需人工导出”** | 不采集 | — | 3 |

统一请求头：`User-Agent: RiseLoop-lit-ledger/1.0 (mailto:<待 G1 确认的联系人邮箱>)`。
URL 参数统一带 `mailto`（Crossref / OpenAlex）与 `tool=RiseLoop-lit-ledger`（PubMed，如有 `email` 参数一并带）。

## 2. 分主题检索式

> 下列检索式为**候选语句**，G1 确认后按来源执行；每条都限定成人/人类与 2010 年之后。
> 中文检索式只用于卫健委/知网人工导出场景，不执行自动检索。

### T1 `sedentary-threshold` 久坐阈值与打断频率（目标 6）

- **PubMed**
  `("sedentary behavior"[MeSH Terms] OR "sedentary time"[Title/Abstract] OR "sitting time"[Title/Abstract] OR "prolonged sitting"[Title/Abstract]) AND ("breaks"[Title/Abstract] OR "breaking up"[Title/Abstract] OR interrupt*[Title/Abstract] OR "bout duration"[Title/Abstract]) AND (adult*[Title/Abstract] OR office[Title/Abstract] OR worker*[Title/Abstract]) AND 2010:2026[dp] AND humans[MeSH Terms]`
- **OpenAlex**
  `search=sedentary time breaking up sitting bout duration frequency`
  `filter=from_publication_date:2010-01-01,type:article|review,has_abstract:true`
- **Crossref**
  `query.bibliographic=breaking up sedentary time bout duration workplace`
  `filter=from-pub-date:2010-01-01,type:journal-article`
- **中文（人工导出）**：`久坐时间 打断 频率 指南`、`久坐行为 30 分钟 起身`
- **预计**：PubMed 命中 25–40，筛留 12；OpenAlex 20 筛留 8；Crossref 10 筛留 4；去重后候选 15–18 → 入库 6。

### T2 `micro-break-workplace` 微休息与工作场所干预（目标 7）

- **PubMed**
  `("micro-break"[Title/Abstract] OR microbreak*[Title/Abstract] OR "workplace intervention"[Title/Abstract] OR "sit-stand"[Title/Abstract] OR "standing desk"[Title/Abstract] OR "active workstation"[Title/Abstract]) AND (sedentary[Title/Abstract] OR sitting[Title/Abstract] OR desk[Title/Abstract]) AND 2010:2026[dp] AND humans[MeSH Terms]`
- **OpenAlex**：`search=micro-break workplace intervention sit-stand desk sedentary`
  `filter=from_publication_date:2010-01-01,type:article|review,has_abstract:true`
- **Crossref**：`query.bibliographic=microbreak workplace sedentary intervention office`
- **中文（人工导出）**：`工间操 久坐 干预 效果`、`微休息 办公 人群`
- **预计**：PubMed 30–45 筛留 14；OpenAlex 20 筛留 9；Crossref 12 筛留 5；去重后 18–20 → 入库 7。

### T3 `neck-shoulder` 颈肩不适（目标 7）

- **PubMed**
  `("neck pain"[MeSH Terms] OR "shoulder pain"[MeSH Terms] OR "neck pain"[Title/Abstract] OR "shoulder pain"[Title/Abstract] OR "neck-shoulder"[Title/Abstract]) AND ("office workers"[Title/Abstract] OR "computer workers"[Title/Abstract] OR sedentary[Title/Abstract] OR workplace[Title/Abstract]) AND 2010:2026[dp] AND humans[MeSH Terms]`
- **OpenAlex**：`search=neck shoulder pain office workers sedentary intervention exercise`
  `filter=from_publication_date:2010-01-01,type:article|review,has_abstract:true`
- **Crossref**：`query.bibliographic=neck shoulder pain office workers stretching intervention`
- **中文（人工导出）**：`颈肩痛 办公人群 久坐 干预`、`颈椎 拉伸 工间`
- **预计**：PubMed 35–50 筛留 14；OpenAlex 20 筛留 9；Crossref 12 筛留 5；去重后 18–22 → 入库 7。

### T4 `low-back` 腰背不适（目标 6）

- **PubMed**
  `("low back pain"[MeSH Terms] OR "low back pain"[Title/Abstract] OR "low-back pain"[Title/Abstract]) AND (sitting[Title/Abstract] OR sedentary[Title/Abstract] OR "prolonged sitting"[Title/Abstract] OR office[Title/Abstract]) AND (exercise[Title/Abstract] OR "physical activity"[Title/Abstract] OR posture[Title/Abstract] OR intervention[Title/Abstract]) AND 2010:2026[dp] AND humans[MeSH Terms]`
- **OpenAlex**：`search=low back pain prolonged sitting office exercise intervention`
  `filter=from_publication_date:2010-01-01,type:article|review,has_abstract:true`
- **Crossref**：`query.bibliographic=low back pain sitting workplace intervention exercise`
- **中文（人工导出）**：`下背痛 久坐 干预`、`腰痛 坐姿 运动 办公`
- **预计**：PubMed 30–45 筛留 12；OpenAlex 20 筛留 8；Crossref 10 筛留 4；去重后 15–18 → 入库 6。

### T5 `safety-redflag` 安全红线与就医边界（目标 6）

- **PubMed**
  `("red flag"[Title/Abstract] OR "red flags"[Title/Abstract] OR "cauda equina"[Title/Abstract] OR "radicular pain"[Title/Abstract] OR radiculopathy[MeSH Terms] OR numbness[Title/Abstract] OR dizziness[Title/Abstract] OR "vertebrobasilar insufficiency"[Title/Abstract]) AND ("guideline"[Publication Type] OR "practice guideline"[Publication Type] OR "systematic review"[Publication Type]) AND 2010:2026[dp] AND humans[MeSH Terms]`
- **OpenAlex**：`search=red flags neck pain low back pain guideline referral`
  `filter=from_publication_date:2010-01-01,type:article|review,has_abstract:true`
- **Crossref**：`query.bibliographic=red flags neck pain clinical practice guideline`
- **官方页面（直取）**：NICE NG59（下背痛与坐骨神经痛）、颈痛指南中关于红旗征/转诊的章节；WHO/CDC 身体活动指南中的“停止运动并就医”表述。
- **中文（人工导出）**：`颈椎病 诊疗指南 红旗征`、`腰痛 诊疗指南 转诊`
- **预计**：PubMed 20–30 筛留 8（指南/综述优先）；OpenAlex 15 筛留 6；官方页面 3–5 条；去重后 12–15 → 入库 6，**指南 ≥2**。

> 注意：本主题只用于“识别与转诊边界”，不得引用为产品可做诊断的依据。

### T6 `bct` 行为改变技术（目标 7）

- **PubMed**
  `("behavior change techniqu*"[Title/Abstract] OR "behaviour change techniqu*"[Title/Abstract] OR "BCT taxonomy"[Title/Abstract] OR "self-monitoring"[Title/Abstract] OR "action planning"[Title/Abstract] OR "problem solving"[Title/Abstract] OR "goal setting"[Title/Abstract]) AND (sedentary[Title/Abstract] OR sitting[Title/Abstract] OR "physical activity"[Title/Abstract]) AND 2010:2026[dp] AND (review[Publication Type] OR randomized controlled trial[Publication Type] OR intervention[Title/Abstract])`
- **OpenAlex**：`search=behavior change techniques self-monitoring action planning sedentary workplace`
  `filter=from_publication_date:2010-01-01,type:article|review,has_abstract:true`
- **Crossref**：`query.bibliographic=behavior change technique taxonomy sedentary workplace intervention`
- **中文（人工导出）**：`行为改变技术 分类 久坐`、`自我监测 目标设定 干预`
- **预计**：PubMed 30–45 筛留 12；OpenAlex 20 筛留 9；Crossref 10 筛留 4；去重后 16–20 → 入库 7。

## 3. 指南定向检索（G5 要求指南 ≥3）

| 序 | 目标文献 | 来源 | 取用方式 |
|---|---|---|---|
| 1 | WHO《Guidelines on physical activity and sedentary behaviour》(2020) | WHO 官网 | 页面直取，`source_type=who` |
| 2 | 《中国人群身体活动指南（2021）》/ 健康中国行动相关文件 | 国家卫健委官网 | 人工导出，`source_type=nhc` |
| 3 | CDC《Physical Activity Guidelines for Americans》相关建议页 | CDC 官网 | 页面直取 |
| 4 | NIOSH 久坐/站坐交替工效学建议 | NIOSH 官网 | 页面直取 |
| 5 | NICE NG59 或等效颈腰痛指南（红旗征章节） | 官方页面 | 页面直取 |

预计取得 4–5 条，满足“指南 ≥3”。

## 4. 分批与并行计划

| 批次 | 内容 | 记录上限 | 说明 |
|---|---|---|---|
| B1 | T1 + T5 + 指南定向 | 20 | 先拿阈值与安全边界，决定后续筛选口径 |
| B2 | T2 + T3 | 20 | 两个高相关主题，需控制去重成本 |
| B3 | T4 + T6 | 20 | 收尾并补齐缺口 |

并行上限 3 个子任务；每批完成后立即过 G2，不攒到最后一并处理。

## 5. 去重与入库前处理

1. 三级去重：DOI → PMID → 标题相似度（≤3 词差异视为同篇）。
2. 同篇多来源时保留 **PubMed**（有 PMID 与摘要）；仅保留一条 `provenance`，其余记入 `notes`。
3. 中英文同名指南以官方中文版为准，英文版作补充并在 `tags` 标注。
4. 入库前跑 `python scripts/validate_evidence.py`，0 error 才允许写 `evidence.json`。

## 6. G1 确认清单（需人工逐项确认）

> 执行清单已结构化为 `g1-plan.json`（Phase 2 唯一权威检索清单），门禁判定与关闭方式见 `g1-gate-record.md`；
> 本节保留为人读版，供讨论与答辩追溯。判定命令：`python scripts/literature/gate_check.py`。

- [ ] 六个主题与目标条数（6 / 7 / 7 / 6 / 6 / 7 = 39）是否认可；
- [ ] 纳排标准是否补充（例如是否纳入生物力学/工效学建模研究）；
- [ ] 上述英文检索式是否需要增删关键词；
- [ ] 中文来源处理方式：卫健委人工导出、知网万方仅标记，是否接受；
- [ ] 时间窗 2010-01-01 起是否合适（指南另按现行版本处理）；
- [ ] 确认采集身份：采用匿名模式（`contact=null`、1 req/s、UA 不含邮箱），不再要求项目邮箱；若连续两次 403/429 再按实名模式补邮箱重试；
- [ ] Phase 2–7 完成时间 2026-11-10 是否可行。

确认后回复“G1 通过”，即进入 Phase 2；未确认前不发起任何检索请求。
