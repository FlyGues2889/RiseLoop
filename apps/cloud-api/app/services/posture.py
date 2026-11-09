from intervention_engine import State, compute_brli, RiskInput
from intervention_engine.risk import DISCLAIMER

from ..repositories.store import Store
from ..schemas.posture import PostureRiskRequest, PostureRiskResponse
from ..schemas.sitting import ActionPayload
from .guidelines import citations_for
from .heartbeat import LOWER_STATE, _match_reason, _rank_actions, _to_payload

PLAN_LABELS = {"quick": "快速", "standard": "标准", "intense": "强化"}


def _sort_for_plan(actions: list[ActionPayload], plan: str) -> list[ActionPayload]:
    if plan == "quick":
        return sorted(
            actions,
            key=lambda action: (0 if action.intensity == "gentle" else 1, action.duration_minutes),
        )
    if plan == "intense":
        return sorted(
            actions,
            key=lambda action: (0 if action.intensity == "normal" else 1, -action.duration_minutes),
        )
    return actions


async def handle_posture_risk(
    store: Store, user_id: str, request: PostureRiskRequest
) -> PostureRiskResponse:
    session = await store.get_session(user_id)
    state = session.state if session else State.S1
    body_parts = [part.value for part in request.body_parts]

    risk_input = RiskInput(
        posture_class=request.posture_class,
        posture_confidence=request.confidence,
        deviation_deg=request.deviation_deg,
        posture_duration_minutes=request.posture_duration_minutes,
        continuous_sitting_minutes=request.sitting_minutes,
        daily_sitting_minutes=request.daily_sitting_minutes,
        minutes_since_last_break=request.minutes_since_last_break,
        micro_activity_minutes=request.micro_activity_minutes,
        rest_minutes=request.rest_minutes,
        activity_density_2h=request.activity_density_2h,
        pain_score=request.pain_score,
        fatigue_score=request.fatigue_score,
        body_parts=tuple(request.body_parts),
        red_flags=tuple(request.red_flags),
    )
    result = compute_brli(risk_input)
    citations = citations_for(
        evidence_id for factor in result.factors for evidence_id in factor.evidence_ids
    )

    if request.red_flags:
        return PostureRiskResponse(
            brli=result.brli,
            risk_level=result.risk_level,
            recommended_plan="maintain",
            actions=[],
            factors=list(result.factors),
            citations=citations,
            needs_medical_advice=True,
            reason="检测到需要就医的信号，已停止动作推荐。",
            disclaimer=DISCLAIMER,
        )

    if result.risk_level == "low":
        return PostureRiskResponse(
            brli=result.brli,
            risk_level=result.risk_level,
            recommended_plan="maintain",
            actions=[],
            factors=list(result.factors),
            citations=citations,
            needs_medical_advice=False,
            reason="当前负荷不高，先不打断你继续工作。",
            disclaimer=DISCLAIMER,
        )

    current_actions = await store.list_actions(state.value)
    if not current_actions:
        return PostureRiskResponse(
            brli=result.brli,
            risk_level=result.risk_level,
            recommended_plan=request.plan,
            actions=[],
            factors=list(result.factors),
            citations=citations,
            needs_medical_advice=result.needs_medical_advice,
            reason="这个阶段暂时没有合适的动作，过一会儿可以再检查一次。",
            disclaimer=DISCLAIMER,
        )

    candidates = [(action, state) for action in current_actions]
    if body_parts:
        matched = [action for action in current_actions if set(action.body_parts) & set(body_parts)]
        if len(matched) < 2:
            lower = LOWER_STATE.get(state)
            if lower is not None:
                lower_actions = await store.list_actions(lower.value, body_parts)
                candidates.extend((action, lower) for action in lower_actions[:2])

    ranked = _rank_actions(candidates, state, body_parts)
    payloads = [
        _to_payload(action, _match_reason(action, source_state, state, body_parts))
        for action, source_state in ranked
    ]
    payloads = _sort_for_plan(payloads, request.plan)[:3]
    plan_label = PLAN_LABELS.get(request.plan, "标准")

    return PostureRiskResponse(
        brli=result.brli,
        risk_level=result.risk_level,
        recommended_plan=request.plan,
        actions=payloads,
        factors=list(result.factors),
        citations=citations,
        needs_medical_advice=result.needs_medical_advice,
        reason=(
            f"按{plan_label}方案挑了 {len(payloads)} 个动作，先做第一个就好。"
        ),
        disclaimer=DISCLAIMER,
    )
