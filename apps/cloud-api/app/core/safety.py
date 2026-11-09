import json
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

MEDICAL_DISCLAIMER = (
    "本产品为健康行为指导工具，不提供医疗诊断或治疗建议。"
    "如出现持续疼痛、放射痛、麻木加重、肢体无力或外伤后剧痛，请及时就医。"
)

RED_FLAG_MESSAGES = {
    "radiating_pain": "放射痛",
    "numbness_worse": "麻木加重",
    "dizziness": "眩晕",
    "leg_weakness": "下肢无力",
    "cotton_wool_gait": "踩棉花感",
    "bowel_bladder": "大小便异常",
    "perineal_numbness": "会阴麻木",
    "post_trauma_severe_pain": "外伤后剧痛",
}

RED_FLAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "radiating_pain": (
        "放射痛", "串电", "放射到", "窜痛",
        "radiating pain", "shooting pain", "pain radiates", "electric shock pain",
    ),
    "numbness_worse": (
        "麻木加重", "越来越麻", "麻木扩散", "手麻加重",
        "numbness worse", "worsening numbness", "numbness spreading", "tingling worse",
    ),
    "dizziness": ("眩晕", "头晕目眩", "天旋地转", "dizziness", "dizzy", "vertigo"),
    "leg_weakness": (
        "下肢无力", "腿没劲", "腿发软", "站不住",
        "leg weakness", "weak legs", "legs give way", "cannot stand",
    ),
    "cotton_wool_gait": (
        "踩棉花", "走路发飘", "脚下没根",
        "cotton wool gait", "walking on cotton", "unsteady gait",
    ),
    "bowel_bladder": (
        "大小便失禁", "大小便异常", "排尿困难", "尿不出来",
        "incontinence", "bladder dysfunction", "bowel dysfunction", "cannot urinate",
    ),
    "perineal_numbness": (
        "会阴麻", "会阴部麻木", "鞍区麻",
        "saddle anesthesia", "perineal numbness", "saddle numbness",
    ),
    "post_trauma_severe_pain": (
        "外伤后剧痛", "摔伤后剧痛", "撞击后剧痛",
        "severe pain after trauma", "pain after a fall", "severe pain after impact",
    ),
}

SAFETY_PROTECTED_PATHS = (
    "/assessment",
    "/sitting/heartbeat",
    "/intervention/feedback",
    "/qa/ask",
    "/posture/risk",
    "/posture/infer",
)


def detect_red_flags(text: str) -> list[str]:
    haystack = text.lower()
    hits: list[str] = []
    for flag, keywords in RED_FLAG_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            hits.append(flag)
    return hits


def detect_in_payload(payload: Any) -> list[str]:
    found: set[str] = set()
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            if current in RED_FLAG_KEYWORDS:
                found.add(current)
            found.update(detect_red_flags(current))
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, (list, tuple, set)):
            stack.extend(current)
    return sorted(found)


def safety_payload(red_flags: list[str]) -> dict:
    return {
        "error": "safety_short_circuit",
        "message": "检测到需要就医的高风险信号，已停止运动推荐。",
        "red_flags": red_flags,
        "red_flag_labels": [RED_FLAG_MESSAGES.get(flag, flag) for flag in red_flags],
        "stop_exercise": True,
        "to_state": "S0",
        "medical_advice": True,
        "disclaimer": MEDICAL_DISCLAIMER,
    }


class SafetyCheckMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.red_flags = []
        if request.method != "POST" or not any(
            request.url.path.endswith(path) for path in SAFETY_PROTECTED_PATHS
        ):
            return await call_next(request)

        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive
        payload: Any = None
        if body:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None

        red_flags = detect_in_payload(payload) if payload is not None else []
        request.state.red_flags = red_flags
        if red_flags:
            await self._record(request, red_flags, source=request.url.path)
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=safety_payload(red_flags))
        return await call_next(request)

    async def _record(self, request: Request, red_flags: list[str], source: str) -> None:
        store = getattr(request.app.state, "store", None)
        if store is None:
            return
        try:
            await store.record_safety_event(
                user_id=None, source=source, red_flags=red_flags, action_taken="short_circuit"
            )
        except Exception:
            return