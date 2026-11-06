from ..core.config import Settings
from ..repositories.store import SessionState, Store
from ..schemas.sitting import ActionPayload, HeartbeatRequest, HeartbeatResponse


def _to_payload(action) -> ActionPayload:
    return ActionPayload(
        id=action.id,
        name=action.name,
        duration_minutes=action.duration_minutes,
        intensity=action.intensity,
        steps=list(action.steps),
        caution=action.caution,
    )


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
    actions = await store.list_actions(session.state.value, body_parts)
    if not actions:
        actions = await store.list_actions(session.state.value)

    if not actions:
        return HeartbeatResponse(
            triggered=False,
            reason="no_action_available",
            state=session.state.value,
            sitting_minutes=request.sitting_minutes,
            threshold_minutes=threshold,
            next_check_minutes=threshold,
        )

    action = actions[0]
    updated = session.model_copy(
        update={"pending_action_id": action.id, "last_push_at": _now(), "sitting_minutes": request.sitting_minutes}
    )
    await store.save_session(user_id, updated)

    return HeartbeatResponse(
        triggered=True,
        reason="triggered",
        state=session.state.value,
        sitting_minutes=request.sitting_minutes,
        threshold_minutes=threshold,
        next_check_minutes=threshold,
        action=_to_payload(action),
    )


def _default_state(assessment: dict | None):
    from intervention_engine import State

    if assessment and assessment.get("initial_state"):
        return State(assessment["initial_state"])
    return State.S1


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)