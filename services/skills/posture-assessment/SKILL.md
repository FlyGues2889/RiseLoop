# posture-assessment

## 职责

把首次评估输入（不适部位、久坐时长、可用时间、疼痛评分、急性不适）转换为初始状态、风险等级与两周计划。只决定"进入哪个状态"，不做后续迁移。

## 输入

```json
{
  "body_parts": ["neck", "shoulder"],
  "sedentary_minutes": 480,
  "available_minutes": 10,
  "pain_score": 6,
  "acute_discomfort": true
}
```

## 输出

```json
{
  "initial_state": "S0",
  "risk_level": "high",
  "duration_range": "2-2 分钟",
  "intensity": "gentle",
  "plan": { "push_threshold_minutes": 45, "min_completions_per_week": 5 }
}
```

## 判定规则

| 条件 | 初始状态 | 风险 |
|---|---|---|
| `acute_discomfort = true` 或 `pain_score ≥ 7` | S0 | high |
| `pain_score` 4–6 | S0 | medium |
| 其余 | S1 | low |

## 边界

- 不诊断疾病、不解释疼痛成因、不推荐用药。
- 命中高危信号时由 `safety-check` 短路，本 Skill 不得继续输出运动建议。
- 不访问数据库/Redis；用户级读写必须经 MCP 工具。
- 可用时间 < 10 分钟时推送阈值降为 30 分钟，但不改变初始状态。

## 示例

> 输入：颈肩不适、久坐 8 小时、疼痛 6 分、无急性发作
> 输出：S0 / medium / 2 分钟 / gentle，两周计划 45 分钟阈值、每周至少 5 次