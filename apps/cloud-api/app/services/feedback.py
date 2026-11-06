from intervention_engine import EngineInput, Feedback, State, TransitionType, decide

from ..core.safety import MEDICAL_DISCLAIMER
from ..repositories.store import SessionState, Store
from ..schemas.intervention import FeedbackRequest, FeedbackResponse
from .heartbeat import _to_payload


async def handle_feedback(store: Store, user_id: str, request: FeedbackRequest) -> FeedbackResponse:
    session = await store.get_session(user_id)
    if session is None:
        session = SessionState(state=State.S1)

    feedback = Feedback(
        completion=request.completion,
        feeling=request.feeling,
        pain_score=request.pain_score,
        next_day_worse=request.next_day_worse,
        red_flags=tuple(request.red_flags),
        obstacle=request.obstacle,
    )
    output = decide(
        EngineInput(state=session.state, feedback=feedback, counters=session.counters)
    )

    if output.transition_type is not TransitionType.HOLD:
        await store.add_transition(
            user_id,
            from_state=output.from_state.value,
            to_state=output.to_state.value,
            reason=output.reason,
            transition_type=output.transition_type.value,
        )

    await store.add_intervention_log(
        user_id,
        {
            "action_id": request.action_id,
            "state": session.state.value,
            "completion": request.completion.value,
            "feeling": request.feeling.value,
            "pain_score": request.pain_score,
            "obstacle": request.obstacle.value if request.obstacle else None,
            "pushed_at": session.last_push_at,
        },
    )

    if output.stop_exercise:
        await store.record_safety_event(
            user_id,
            source="intervention/feedback",
            red_flags=[flag.value for flag in request.red_flags],
            action_taken="short_circuit",
        )

    await store.save_session(
        user_id,
        session.model_copy(
            update={
                "state": output.to_state,
                "counters": output.counters,
                "pending_action_id": None,
                "last_push_at": None,
                "sitting_minutes": 0,
            }
        ),
    )

    next_action = None
    if not output.stop_exercise:
        actions = await store.list_actions(
            output.to_state.value, max_minutes=output.duration_minutes[1]
        )
        if not actions:
            actions = await store.list_actions(output.to_state.value)
        if actions:
            next_action = _to_payload(actions[0])

    return FeedbackResponse(
        from_state=output.from_state.value,
        to_state=output.to_state.value,
        transition_type=output.transition_type.value,
        reason=output.reason,
        duration_range=f"{output.duration_minutes[0]}-{output.duration_minutes[1]} 分钟",
        intensity=output.intensity,
        stop_exercise=output.stop_exercise,
        medical_advice=output.medical_advice,
        next_action=next_action,
        disclaimer=MEDICAL_DISCLAIMER,
    )