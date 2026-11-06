# intervention-state-machine

## 职责

根据"当前状态 + 本次反馈 + 连续计数"决定下一个状态与干预参数。迁移逻辑以 `packages/intervention-engine` 的纯函数 `decide()` 为唯一权威实现，本 Skill 只负责组织输入、解释输出，不得自行推导状态。

## 输入

```json
{
  "state": "S1",
  "feedback": {
    "completion": "completed",
    "feeling": "better",
    "pain_score": 2,
    "next_day_worse": false,
    "red_flags": [],
    "obstacle": null
  },
  "counters": { "completed_streak": 4, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 2 }
}
```

## 输出

```json
{
  "from_state": "S1",
  "to_state": "S2",
  "transition_type": "upgrade",
  "reason": "连续完成 5 次，进入强化",
  "duration_minutes": [5, 8],
  "intensity": "normal",
  "stop_exercise": false,
  "medical_advice": false
}
```

## 四分支

| transition_type | 触发条件 | 处理 |
|---|---|---|
| `upgrade` | 满足各状态退出条件 | 升一级，时长按新状态区间 |
| `rollback` | 连续 2 次症状加重 | 回退一级并缩短时长 |
| `degrade` | 连续 3 次跳过/没感觉且无加重 | 不降状态，换更低强度、更短动作 |
| `short_circuit` | 任一高危红旗 | 立即回 S0 + 就医提示，停止推荐 |

## 边界

- 函数必须显式返回 `transition_type`，包括内部的 `hold`。
- 禁止在 Agent 提示词里二次判断状态；提示词只允许复述引擎结果。
- 禁止读写数据库；迁移历史由 `write_intervention_result` 落库。
- 红旗判定不在此 Skill 内完成，必须由 `safety-check` 前置。

## 示例

> 输入：S1、第 5 次连续完成、评分 2
> 输出：upgrade → S2，5–8 分钟，intensity=normal