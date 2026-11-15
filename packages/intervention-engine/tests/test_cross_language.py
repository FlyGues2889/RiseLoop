"""跨语言状态机一致性测试（Python vs JS 对拍）。

验证 `packages/local-engine`（JS 镜像）与 `packages/intervention-engine`（Python 权威）
在同一批场景下输出完全一致：to_state / transition_type / reason / duration /
intensity / stop_exercise / medical_advice / counters 全字段比对。

场景表覆盖四分支与 hold 的全部判定路径；任意一侧改动迁移规则，
本测试会立即失败，用于替代"人工同步两套引擎"的口头约定。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from intervention_engine import EngineInput, StateCounters, decide

REPO_ROOT = Path(__file__).resolve().parents[3]
DUMP_SCRIPT = REPO_ROOT / "scripts" / "engine_dump.mjs"

FIELDS = (
    "from_state",
    "to_state",
    "transition_type",
    "reason",
    "duration_minutes",
    "intensity",
    "stop_exercise",
    "medical_advice",
    "counters",
)


def _feedback(
    completion: str = "completed",
    feeling: str = "same",
    pain_score: int = 0,
    next_day_worse: bool = False,
    red_flags: tuple[str, ...] | list[str] = (),
    obstacle: str | None = None,
) -> dict:
    return {
        "completion": completion,
        "feeling": feeling,
        "pain_score": pain_score,
        "next_day_worse": next_day_worse,
        "red_flags": list(red_flags),
        "obstacle": obstacle,
    }


SCENARIOS: list[dict] = [
    # -- upgrade --
    {"name": "S0 完成 2 次且评分达标 → S1", "state": "S0",
     "feedback": _feedback(pain_score=3), "counters": {"completed_streak": 1, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 1}},
    {"name": "S1 连续完成 5 次 → S2", "state": "S1",
     "feedback": _feedback(pain_score=2), "counters": {"completed_streak": 4, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 0}},
    {"name": "S2 连续完成 10 次 → S3", "state": "S2",
     "feedback": _feedback(), "counters": {"completed_streak": 9, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 0}},
    # -- hold（未达升级阈值）--
    {"name": "S0 首次完成未达 2 次", "state": "S0",
     "feedback": _feedback(pain_score=3)},
    {"name": "S0 完成 2 次但评分 >3", "state": "S0",
     "feedback": _feedback(pain_score=4), "counters": {"completed_streak": 1, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 1}},
    {"name": "S1 连续完成 4 次未达阈值", "state": "S1",
     "feedback": _feedback(), "counters": {"completed_streak": 3, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 0}},
    {"name": "S2 连续完成 9 次未达阈值", "state": "S2",
     "feedback": _feedback(), "counters": {"completed_streak": 8, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 0}},
    {"name": "S3 完成保持维持", "state": "S3", "feedback": _feedback()},
    # -- rollback（症状加重）--
    {"name": "S1 首次加重只观察不回退", "state": "S1", "feedback": _feedback(feeling="worse")},
    {"name": "S1 连续 2 次加重 → S0", "state": "S1",
     "feedback": _feedback(feeling="worse"), "counters": {"completed_streak": 0, "skipped_streak": 0, "worse_streak": 1, "s0_completed": 0}},
    {"name": "S2 连续 2 次加重 → S1", "state": "S2",
     "feedback": _feedback(next_day_worse=True), "counters": {"completed_streak": 0, "skipped_streak": 0, "worse_streak": 1, "s0_completed": 0}},
    {"name": "S3 连续 2 次加重 → S2", "state": "S3",
     "feedback": _feedback(feeling="worse"), "counters": {"completed_streak": 0, "skipped_streak": 0, "worse_streak": 1, "s0_completed": 0}},
    {"name": "S0 连续 2 次加重原地回退并清零", "state": "S0",
     "feedback": _feedback(feeling="worse"), "counters": {"completed_streak": 0, "skipped_streak": 0, "worse_streak": 1, "s0_completed": 2}},
    # -- degrade（连续跳过）--
    {"name": "S1 跳过 1 次只 hold", "state": "S1", "feedback": _feedback(completion="skipped")},
    {"name": "S1 连续 3 次跳过 → degrade（无障碍归因）", "state": "S1",
     "feedback": _feedback(completion="skipped"), "counters": {"completed_streak": 0, "skipped_streak": 2, "worse_streak": 0, "s0_completed": 0}},
    {"name": "S2 连续 3 次跳过 → degrade（动作太难）", "state": "S2",
     "feedback": _feedback(completion="skipped", obstacle="too_hard"),
     "counters": {"completed_streak": 0, "skipped_streak": 2, "worse_streak": 0, "s0_completed": 0}},
    {"name": "S0 连续 3 次跳过 → degrade（太忙）", "state": "S0",
     "feedback": _feedback(completion="skipped", obstacle="busy"),
     "counters": {"completed_streak": 0, "skipped_streak": 2, "worse_streak": 0, "s0_completed": 1}},
    {"name": "S3 连续 3 次跳过 → degrade（忘了）", "state": "S3",
     "feedback": _feedback(completion="skipped", obstacle="forgot"),
     "counters": {"completed_streak": 0, "skipped_streak": 2, "worse_streak": 0, "s0_completed": 0}},
    # -- partial --
    {"name": "S1 部分完成不计入连续", "state": "S1", "feedback": _feedback(completion="partial")},
    # -- short_circuit（8 类红旗优先级最高）--
    {"name": "S1 放射痛短路", "state": "S1", "feedback": _feedback(red_flags=("radiating_pain",))},
    {"name": "S3 跳过但命中眩晕，红旗优先", "state": "S3",
     "feedback": _feedback(completion="skipped", red_flags=("dizziness",))},
    {"name": "S2 完成但命中会阴麻木，红旗优先", "state": "S2",
     "feedback": _feedback(pain_score=5, red_flags=("perineal_numbness",)),
     "counters": {"completed_streak": 9, "skipped_streak": 0, "worse_streak": 0, "s0_completed": 0}},
    {"name": "S0 多红旗叠加（大小便异常+踩棉花感）", "state": "S0",
     "feedback": _feedback(red_flags=("bowel_bladder", "cotton_wool_gait"))},
    {"name": "S1 外伤后剧痛短路", "state": "S1", "feedback": _feedback(red_flags=("post_trauma_severe_pain",))},
    # -- 计数器联动：完成会重置跳过/加重 --
    {"name": "S1 跳过 2 次后转为完成 → hold 并清零跳过", "state": "S1",
     "feedback": _feedback(pain_score=1), "counters": {"completed_streak": 0, "skipped_streak": 2, "worse_streak": 0, "s0_completed": 0}},
    {"name": "S1 加重 1 次后转为完成 → hold 并清零加重", "state": "S1",
     "feedback": _feedback(pain_score=1), "counters": {"completed_streak": 0, "skipped_streak": 0, "worse_streak": 1, "s0_completed": 0}},
]


def _python_outputs() -> list[dict]:
    outputs = []
    for case in SCENARIOS:
        payload = EngineInput(
            state=case["state"],
            feedback=case["feedback"],
            counters=_counters_of(case),
        )
        outputs.append(decide(payload).model_dump(mode="json"))
    return outputs


def _js_outputs() -> list[dict]:
    node = shutil.which("node")
    assert node is not None, "node 不可用时不应进入本测试"
    assert DUMP_SCRIPT.exists(), f"缺少桥接脚本：{DUMP_SCRIPT}"
    stdin = json.dumps(
        [
            {"state": case["state"], "feedback": case["feedback"], "counters": case.get("counters")}
            for case in SCENARIOS
        ]
    )
    proc = subprocess.run(
        [node, str(DUMP_SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    assert proc.returncode == 0, f"node 桥接脚本失败：{proc.stderr}"
    return json.loads(proc.stdout)


def _counters_of(case: dict) -> "StateCounters":
    raw = case.get("counters")
    return StateCounters(**raw) if raw else StateCounters()


@pytest.mark.skipif(shutil.which("node") is None, reason="未安装 node，跳过跨语言对拍")
def test_python_and_js_state_machine_agree():
    py_outputs = _python_outputs()
    js_outputs = _js_outputs()

    assert len(js_outputs) == len(SCENARIOS)
    for case, py_out, js_out in zip(SCENARIOS, py_outputs, js_outputs):
        for field in FIELDS:
            assert py_out[field] == js_out[field], (
                f"场景「{case['name']}」字段 {field} 不一致："
                f"python={py_out[field]!r} js={js_out[field]!r}"
            )


@pytest.mark.skipif(shutil.which("node") is None, reason="未安装 node，跳过跨语言对拍")
def test_cross_language_scenarios_cover_all_branches():
    expected = {"upgrade", "rollback", "degrade", "short_circuit", "hold"}
    seen = set()
    for case in SCENARIOS:
        out = decide(EngineInput(
            state=case["state"],
            feedback=case["feedback"],
            counters=_counters_of(case),
        ))
        seen.add(out.transition_type.value)
    assert expected <= seen, f"场景表未覆盖分支：{expected - seen}"
