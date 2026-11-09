from intervention_engine import State

from ..core.config import Settings
from ..repositories.store import SessionState, Store
from ..schemas.sitting import ActionPayload, HeartbeatRequest, HeartbeatResponse

BODY_PART_LABELS = {
    "neck": "颈部",
    "shoulder": "肩部",
    "upper_back": "上背",
    "low_back": "腰背",
    "hip": "髋部",
    "core": "核心",
}

LOWER_STATE: dict[State, State | None] = {
    State.S0: None,
    State.S1: State.S0,
    State.S2: State.S1,
    State.S3: State.S2,
}


def _to_payload(action, match_reason: str = "") -> ActionPayload:
    return ActionPayload(
        id=action.id,
        name=action.name,
        duration_minutes=action.duration_minutes,
        intensity=action.intensity,
        body_parts=list(action.body_parts),
        steps=list(action.steps),
        caution=action.caution,
        match_reason=match_reason,
    )


def _overlap(action, body_parts: list[str] | None) -> int:
    if not body_parts:
        return 0
    return len(set(action.body_parts) & set(body_parts))


def _match_reason(
    action, source_state: State, current_state: State, body_parts: list[str] | None
) -> str:
    labels = [
        BODY_PART_LABELS[part]
        for part in action.body_parts
        if body_parts and part in body_parts and part in BODY_PART_LABELS
    ]
    if source_state is not current_state:
        suffix = f"，针对{'/'.join(labels)}" if labels else ""
        return f"更温和的备选{suffix}"
    if labels:
        return f"针对{'/'.join(labels)}"
    return "当前阶段的常规动作"


def _rank_actions(candidates, current_state: State, body_parts: list[str] | None):
    def key(item):
        action, source_state = item
        same_state = 1 if source_state is current_state else 0
        return (-same_state, -_overlap(action, body_parts), action.duration_minutes, action.id)

    ranked = sorted(candidates, key=key)
    seen: set[str] = set()
    unique = []
    for action, source_state in ranked:
        if action.id in seen:
            continue
        seen.add(action.id)
        unique.append((action, source_state))
    return unique[:3]


async def handle_heartbeat(
    store: Store, settings: Settings, user_id: str, request: HeartbeatRequest
) -> HeartbeatResponse:
    session = await store.get_session(user_id)
    if session is None:
        session = SessionState(state=_default_state(await store.latest_assessment(user_id)))

    threshold = request.threshold_minutes or settings.sitting_threshold_minutes
    await store.add_sitting_event(user_id, event_type="heartbeat", source="manual")

    if request.sitting_minutes < threshold:
        return HeartbeatResponse(
            triggered=False,
            reason="below_threshold",
            state=session.state.value,
            sitting_minutes=request.sitting_minutes,
            threshold_minutes=threshold,
            next_check_minutes=max(1, threshold - request.sitting_minutes),
        )

    if session.is_cooldown_active(settings.push_cooldown_minutes):
        return HeartbeatResponse(
            triggered=False,
            reason="cooldown",
            state=session.state.value,
            sitting_minutes=request.sitting_minutes,
            threshold_minutes=threshold,
            next_check_minutes=settings.push_cooldown_minutes,
        )

    assessment = await store.latest_assessment(user_id)
    body_parts = assessment["body_parts"] if assessment else None

    current_actions = await store.list_actions(session.state.value)
    if not current_actions:
        return HeartbeatResponse(
            triggered=False,
            reason="no_action_available",
            state=session.state.value,
            sitting_minutes=request.sitting_minutes,
            threshold_minutes=threshold,
            next_check_minutes=threshold,
        )

    candidates = [(action, session.state) for action in current_actions]
    if body_parts:
        matched = [action for action in current_actions if _overlap(action, body_parts) > 0]
        if len(matched) < 2:
            lower = LOWER_STATE.get(session.state)
            if lower is not None:
                lower_actions = await store.list_actions(lower.value, body_parts)
                candidates.extend((action, lower) for action in lower_actions[:2])

    ranked = _rank_actions(candidates, session.state, body_parts)
    payloads = [
        _to_payload(action, _match_reason(action, source_state, session.state, body_parts))
        for action, source_state in ranked
    ]
    primary = ranked[0][0]

    updated = session.model_copy(
        update={"pending_action_id": primary.id, "last_push_at": _now(), "sitting_minutes": request.sitting_minutes}
    )
    await store.save_session(user_id, updated)

    return HeartbeatResponse(
        triggered=True,
        reason="triggered",
        state=session.state.value,
        sitting_minutes=request.sitting_minutes,
        threshold_minutes=threshold,
        next_check_minutes=threshold,
        action=payloads[0],
        actions=payloads,
    )


def _default_state(assessment: dict | None):
    from intervention_engine import State

    if assessment and assessment.get("initial_state"):
        return State(assessment["initial_state"])
    return State.S1


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)