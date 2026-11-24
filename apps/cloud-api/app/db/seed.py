import json
from pathlib import Path

_DEFAULT_ACTIONS: list[dict] = [
    {
        "id": "s0-neck-release",
        "name": "坐姿颈部缓慢放松",
        "state": "S0",
        "body_parts": ["neck", "shoulder"],
        "duration_minutes": 2,
        "intensity": "gentle",
        "desk_friendly": True,
        "steps": [
            "坐直，双脚踩地，肩膀放松下沉",
            "呼气时缓慢低头，下巴靠近胸口，停 5 秒",
            "吸气回正，让头缓缓倒向左侧，停 5 秒",
            "回正后倒向右侧，同样停 5 秒",
            "抬头回正，做 3 次自然深呼吸收尾",
        ],
        "caution": "如出现眩晕或放射痛，请立即停止并就医",
    },
    {
        "id": "s1-stand-break",
        "name": "起身站立微活动",
        "state": "S1",
        "body_parts": ["low_back", "hip"],
        "duration_minutes": 3,
        "intensity": "normal",
        "desk_friendly": False,
        "steps": [
            "起身站立，双脚与髋同宽，膝盖微屈",
            "双手十指交叉向上举过头顶，伸展 10 秒",
            "放下手臂，原地抬膝 20 次，左右交替",
            "停下后自然呼吸 3 次，感受身体放松",
        ],
        "caution": "起身放慢，避免体位性眩晕",
    },
    {
        "id": "s2-core-activation",
        "name": "坐姿核心激活",
        "state": "S2",
        "body_parts": ["low_back", "core"],
        "duration_minutes": 2,
        "intensity": "normal",
        "desk_friendly": True,
        "steps": [
            "坐骨压实椅面，脊柱向上延展，双脚踩地",
            "呼气时收腹，感觉肋骨下沉，保持 5 秒",
            "吸气放松，再做 8 次这样的收腹呼吸",
            "最后做骨盆前后倾 10 次，幅度小一点",
        ],
        "caution": "出现锐痛时，请立即停止",
    },
    {
        "id": "s3-posture-reset",
        "name": "靠墙体态重置",
        "state": "S3",
        "body_parts": ["neck", "shoulder", "low_back"],
        "duration_minutes": 2,
        "intensity": "normal",
        "desk_friendly": False,
        "steps": [
            "找一面空墙，后脑、肩胛、骨盆依次贴墙站立",
            "收下巴，让后颈延长，保持 30 秒",
            "保持贴墙，缓慢做 5 次深呼吸",
            "离开墙面，回到坐姿，感受背部位置",
        ],
        "caution": "不必强求全部接触墙面",
    },
]


def _candidate_paths() -> list[Path]:
    module = Path(__file__).resolve()
    parents = list(module.parents)
    candidates = [
        parents[index] / "data" / "actions" / "actions.json"
        for index in (4, 2)
        if index < len(parents)
    ]
    candidates.append(Path.cwd() / "data" / "actions" / "actions.json")
    return candidates


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