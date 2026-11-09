# 久坐累积负荷与风险融合（BRLI V1）

## 1. 定位

在端云协同姿态感知之上，把**姿态异常、久坐时长、恢复行为、主观反馈**融合为“行为风险负荷指数”（BRLI），用于干预决策支持。

> 这是**研究性行为风险指标**，不是医学诊断，也不替代 `safety-check` 的红旗征筛查。

## 2. 输入

| 维度 | 字段 | 说明 |
|---|---|---|
| 姿态 | `posture_class`、`confidence`、`deviation_deg`、`duration_minutes` | 来自 ModelArts 姿态分类；类别为 `baseline` / `forward_head` / `lateral_tilt` / `undetermined` |
| 久坐 | `continuous_sitting_minutes`、`daily_sitting_minutes`、`minutes_since_last_break` | 由 Rust 计时器 + 云端会话状态提供 |
| 恢复 | `micro_activity_minutes`、`rest_minutes`、`activity_density_2h` | 已完成微活动、休息时长、近 2 小时活动密度 |
| 症状 | `pain_score`、`fatigue_score`、`body_parts`、`red_flags` | 主观评分 0–10；红旗征由 `safety-check` 前置拦截 |

**隐私边界**：原始视频不出端，只上传姿态特征与时序特征；不传像素、人脸或身份信息。

## 3. 公式

```text
BRLI(t) = α·P(t) + β·T(t) − γ·R(t) + δ·S(t)
```

- `P(t)`：姿态负荷。由姿态类别、异常幅度、持续性与模型置信度生成。
- `T(t)`：时间负荷。由连续久坐、当日累计久坐、距上次中断时长生成。
- `R(t)`：恢复抵扣。由起身活动、微运动完成度、休息持续时间抵扣。
- `S(t)`：症状修正。由颈肩/腰背不适、疲劳评分修正。
- `α/β/γ/δ`：可配置权重；V1 默认值见第 5 节，需小样本校准。

当日累积负荷与短时风险：

```text
CL_day = Σ BRLI(t) · Δt
RW     = 近 30–60 分钟加权平均
```

## 4. 风险分级与干预策略

| 等级 | BRLI | 建议 |
|---|---|---|
| `low` | < 0.35 | 轻提示 / 姿态微调 |
| `medium` | 0.35–0.55 | 短时起身 / 局部放松 |
| `high` | 0.55–0.75 | S0–S1 干预动作推荐 |
| `very_high` | ≥ 0.75 | 降级策略 / 安全提醒；伴明显不适时建议暂停并就医 |

红旗征命中时，不走 BRLI 分级，直接由 `safety-check` 返回 403 + 就医提示。

## 5. 默认权重（工程初值，待校准）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `alpha` | 0.35 | 姿态负荷权重 |
| `beta` | 0.35 | 时间负荷权重 |
| `gamma` | 0.10 | 恢复抵扣权重 |
| `delta` | 0.20 | 症状修正权重 |
| `posture_cap_minutes` | 30 | 姿态持续 30 分钟达到满负荷 |
| `sitting_cap_minutes` | 45 | 连续久坐 45 分钟达到满负荷 |
| `daily_sitting_cap` | 480 | 当日累计 8 小时达到满负荷 |
| `break_gap_cap_minutes` | 60 | 距上次中断 60 分钟达到满负荷 |
| `recovery_cap_minutes` | 15 | 恢复 15 分钟达到满抵扣 |

> 这些是工程初值，不是临床阈值；必须通过小样本测试和运康专业审核后再冻结。

## 6. 输出契约

```json
{
  "brli": 0.63,
  "risk_level": "high",
  "short_term_risk": 0.58,
  "daily_load": 4.2,
  "factors": [
    { "code": "posture", "value": 0.72, "weight": 0.35, "contribution": 0.252, "evidence_ids": ["pmid-40111906"] },
    { "code": "sitting", "value": 0.85, "weight": 0.35, "contribution": 0.298, "evidence_ids": ["pmid-35147898"] },
    { "code": "recovery", "value": 0.20, "weight": -0.10, "contribution": -0.020, "evidence_ids": ["pmid-33906239"] },
    { "code": "symptom", "value": 0.40, "weight": 0.20, "contribution": 0.080, "evidence_ids": ["pmid-38219373"] }
  ],
  "needs_medical_advice": false,
  "disclaimer": "本产品为健康行为指导工具，不提供医疗诊断或治疗建议。"
}
```

## 7. 与现有系统的关系

- 姿态分类与 BRLI 都是 `intervention-engine` 的**输入**，不替代 S0–S3 迁移。
- 风险等级用于选择干预强度；迁移仍由 `decide()` 按既有规则执行。
- 红旗征仍由 `SafetyCheckMiddleware` 在请求入口拦截，BRLI 不处理急症。
- 证据 id 必须能在 `data/knowledge/evidence.json` 中找到，不编造。

## 8. MVP 步骤（2 周核心）

1. 定义姿态与久坐特征 JSON Schema（`risk.py` 的 Pydantic 模型）。
2. 先用规则融合实现 BRLI V1（纯函数 + 单测）。
3. 接入 RDS/DCS 与 S0–S3 状态机。
4. 通过小样本测试再迭代权重与阈值；未校准前不对外宣称“医学有效”。

## 9. 实现状态（2026-11-08）

- 纯函数已落地：`packages/intervention-engine/src/intervention_engine/risk.py`。
- 已导出：`RiskInput`、`BrliConfig`、`BrliOutput`、`compute_brli`、`cumulative_load`、`short_term_risk`。
- 单测：`packages/intervention-engine/tests/test_risk.py`，9 个用例；全仓 `pytest` 86 passed。
- 已接线：`POST /posture/risk` 与客户端实时风险展示；姿态面板每 2 秒上传特征并显示 BRLI、风险等级、推荐方案。
- 权威来源：风险响应带 `citations[]`，从 `data/knowledge/evidence.json` 解析，前端在风险报告与计时结束遮罩中展示。
- 未接线：`/posture/infer`（真实 ModelArts 推理）、RDS/DCS、S0–S3 融合。
- 权重与阈值仍是工程初值，未做小样本校准；未校准前只能用于内部联调，不对外宣称“医学有效”。

## 10. 待确认

- 姿态类别是否就按 `baseline / forward_head / lateral_tilt / undetermined` 冻结。
- 当日累计负荷按什么时间粒度累加（1 分钟 / 5 分钟）。
- 恢复抵扣是否区分“主动微运动”和“被动休息”。
- 权重与阈值由谁签字冻结（运康专业 + 项目负责人）。
