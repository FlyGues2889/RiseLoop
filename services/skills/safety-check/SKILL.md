# safety-check

## 职责

在任何运动推荐、状态迁移、智能问答之前识别高危信号，并给出统一的就医提示。权威实现在 `apps/cloud-api/app/core/safety.py`，以中间件形式强制生效；本 Skill 只是该规则的语义说明与词表维护入口。

## 输入

- 用户的自由文本描述（问答、反馈备注）
- 结构化红旗字段 `red_flags[]`

## 输出（命中时）

```json
{
  "error": "safety_short_circuit",
  "red_flags": ["radiating_pain"],
  "red_flag_labels": ["放射痛"],
  "stop_exercise": true,
  "to_state": "S0",
  "medical_advice": true,
  "disclaimer": "本产品为健康行为指导工具，不提供医疗诊断或治疗建议……"
}
```

## 红旗清单（词表必须与代码一致）

| code | 语义 | 关键词示例 |
|---|---|---|
| `radiating_pain` | 放射痛 | 放射痛、串电、串到手指 |
| `numbness_worse` | 麻木加重 | 麻木加重、越来越麻 |
| `dizziness` | 眩晕 | 眩晕、天旋地转 |
| `leg_weakness` | 下肢无力 | 下肢无力、腿没劲 |
| `cotton_wool_gait` | 踩棉花感 | 踩棉花、走路发飘 |
| `bowel_bladder` | 大小便异常 | 失禁、排尿困难 |
| `perineal_numbness` | 会阴麻木 | 会阴麻、鞍区麻 |
| `post_trauma_severe_pain` | 外伤后剧痛 | 摔伤后剧痛、撞击后剧痛 |

## 边界

- 必须由代码层中间件强制，禁止依赖 Agent 或提示词自觉。
- 命中即返回 403 语义，不进入 Agent、不进入状态机、不调用动作库。
- 不输出任何鉴别诊断、不推荐药物、不承诺康复时间。
- 命中事件写 `safety_events`，仅记录状态与红旗代码，不落原文。

## 示例

> 输入："做完以后手麻加重，还串电到手指"
> 输出：403 + `numbness_worse`、`radiating_pain`，停止推荐并给出就医提示