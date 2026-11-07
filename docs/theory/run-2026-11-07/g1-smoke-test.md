# G1 连通性冒烟记录

## 文档信息

| 项 | 内容 |
|---|---|
| 目的 | 证明匿名模式下 PubMed 可达、T1 检索式可被解析，为 Phase 2 采集建立链路基线 |
| 执行时间 | 2026-11-07 |
| 执行命令 | `python scripts/literature/smoke_pubmed.py` |
| 采集身份 | 匿名：`User-Agent: RiseLoop-lit-ledger/1.0`，无 `mailto`、无邮箱 |
| 请求 | `esearch.fcgi?db=pubmed&term=<T1 检索式>&retmax=2&retmode=json&tool=RiseLoop-lit-ledger` |

## 结果

| 项 | 值 |
|---|---|
| HTTP 状态 | **200** |
| 耗时 | 1.12 s |
| 命中总数（count） | 710 |
| 返回 PMID | 42925061、42841540 |
| warninglist | 无 |
| esearch error | 无 |

结论：匿名 UA 可正常访问 PubMed E-utilities，T1 检索式的字段标签与布尔逻辑均被正确解析（count 非 0 即为解析成功）。本次请求只取 2 个 ID 做冒烟，**未采集任何记录**，不构成 Phase 2 采集。

## 备注

- 首次用 PowerShell 直接发同一长检索式时，60 s 超时；改用 Python 标准库 + 45 s 超时后 1.12 s 返回，属于客户端超时设置问题，不是服务端拒绝。
- 该次请求按 1 req/s 执行，符合匿名模式约束。
- 其他来源（Crossref / OpenAlex / WHO / CDC / NIOSH）尚未冒烟；Phase 2 开始前需各自跑一次，失败则按兜底规则处理。
