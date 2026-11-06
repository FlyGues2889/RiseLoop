import json
from pathlib import Path

_DEFAULT_ACTIONS: list[dict] = [
    {
        "id": "s0-neck-release",
        "name": "坐姿颈部缓慢放松",
        "state": "S0",
        "body_parts": ["neck", "shoulder"],
        "duration_minutes": 1,
        "intensity": "gentle",
        "steps": ["坐直，肩膀自然下沉", "呼气时缓慢低头保持 5 秒", "左右侧屈各 5 秒", "重复 3 轮"],
        "caution": "出现眩晕、放射痛立即停止并就医",
    },
    {
        "id": "s1-stand-break",
        "name": "起身站立微活动",
        "state": "S1",
        "body_parts": ["low_back", "hip"],
        "duration_minutes": 3,
        "intensity": "normal",
        "steps": ["起身站立，双脚与髋同宽", "双手上举伸展 3 次", "原地抬膝 20 次"],
        "caution": "起身放慢，避免体位性眩晕",
    },
    {
        "id": "s2-core-activation",
        "name": "坐姿核心激活",
        "state": "S2",
        "body_parts": ["low_back", "core"],
        "duration_minutes": 6,
        "intensity": "normal",
        "steps": ["坐骨压实，脊柱延展", "呼气收腹保持 5 秒共 8 次", "骨盆前后倾 10 次"],
        "caution": "腰部锐痛立即停止",
    },
    {
        "id": "s3-posture-reset",
        "name": "维持期体态重置",
        "state": "S3",
        "body_parts": ["neck", "shoulder", "low_back"],
        "duration_minutes": 3,
        "intensity": "normal",
        "steps": ["靠墙站立贴墙 30 秒共 3 次", "回到坐姿深呼吸 5 次"],
        "caution": "不必强求全部接触墙面",
    },
]


def _candidate_paths() -> list[Path]:
    module = Path(__file__).resolve()
    return [
        module.parents[4] / "data" / "actions" / "actions.json",
        module.parents[2] / "data" / "actions" / "actions.json",
        Path.cwd() / "data" / "actions" / "actions.json",
    ]


def load_seed_actions() -> list[dict]:
    for path in _candidate_paths():
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, list) and data:
                return data
    return [dict(item) for item in _DEFAULT_ACTIONS]