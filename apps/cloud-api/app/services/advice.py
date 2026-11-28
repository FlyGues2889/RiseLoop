"""个性化建议：按界面场景让 MaaS 生成一段话，失败就用前端传来的现文案。

约束：
- 只发结构化摘要，不发健康档案原文、身份信息或日志；
- 一段话、不列步骤、≤80 字，不诊断、不给用药或康复周期；
- 同一用户同一场景缓存 5 分钟，切页不会重复计费。
"""

from __future__ import annotations

from time import monotonic

from ..cloud.registry import CloudRegistry
from ..core.config import Settings
from ..schemas.advice import AdviceRequest, AdviceResponse

CACHE_SECONDS = 300

SURFACE_HINTS = {
    "weekly": "根据本周完成率、疼痛趋势和安全中断，给一句下周怎么做的话。",
    "posture": "根据当前坐姿风险和负荷，给一句马上能做的调整。",
    "transition": "根据这次阶段迁移的结果，用一句人话说清为什么变、接下来做什么。",
    "timer": "根据当前阶段和久坐时长，给一句提醒自己起身活动的话。",
}

SYSTEM_PROMPT = (
    "你是久坐与颈肩不适干预产品的提示文案助手。"
    "只输出一段中文，不列编号、不用分点、不加标题，不超过 80 字。"
    "语气平实，先给动作，再给一句原因。"
    "不做诊断，不给用药、康复周期或影像解读建议。"
)

_cache: dict[tuple[str, str], tuple[float, str]] = {}


def _build_user_prompt(request: AdviceRequest) -> str:
    hint = SURFACE_HINTS.get(request.surface, "")
    facts = "；".join(f"{key}={value}" for key, value in request.context.items() if value is not None)
    return f"场景：{hint}\n当前阶段：{request.state or '未知'}\n数据：{facts or '暂无'}"


async def build_advice(
    cloud: CloudRegistry,
    settings: Settings,
    user_id: str,
    request: AdviceRequest,
) -> AdviceResponse:
    if not request.fallback and not cloud.maas.configured:
        return AdviceResponse(text=request.fallback, source="template")

    key = (user_id, request.surface)
    cached = _cache.get(key)
    if cached and monotonic() - cached[0] < CACHE_SECONDS:
        return AdviceResponse(text=cached[1], source="model")

    if settings.cloud_provider != "huawei" or not cloud.maas.configured:
        return AdviceResponse(text=request.fallback, source="template")

    try:
        text = await cloud.maas.complete(
            system=SYSTEM_PROMPT,
            user=_build_user_prompt(request),
            max_tokens=160,
        )
    except Exception:
        return AdviceResponse(text=request.fallback, source="template")

    text = " ".join(text.split())
    if not text:
        return AdviceResponse(text=request.fallback, source="template")
    _cache[key] = (monotonic(), text)
    return AdviceResponse(text=text, source="model")
