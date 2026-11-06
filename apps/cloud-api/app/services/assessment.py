from intervention_engine import State

from ..core.safety import MEDICAL_DISCLAIMER
from ..repositories.store import Store
from ..schemas.assessment import AssessmentRequest, AssessmentResponse, TwoWeekPlan

STATE_NAMES = {"S0": "急性缓解", "S1": "激活", "S2": "强化", "S3": "维持"}

DURATION_RANGES = {
    "S0": (2, 2),
    "S1": (3, 5),
    "S2": (5, 8),
    "S3": (2, 5),
}


def decide_initial_state(request: AssessmentRequest) -> tuple[State, str, str]:
    if request.acute_discomfort or request.pain_score >= 7:
        return State.S0, "high", "gentle"
    if request.pain_score >= 4:
        return State.S0, "medium", "gentle"
    return State.S1, "low", "normal"


def build_plan(state: State, available_minutes: int) -> TwoWeekPlan:
    threshold = 45 if available_minutes >= 10 else 30
    weekly = 5 if state is State.S0 else 7
    return TwoWeekPlan(
        week1_goal="建立久坐提醒与最短动作的稳定执行",
        week2_goal="在完成率 ≥60% 的基础上延长单次干预时长",
        push_threshold_minutes=threshold,
        min_completions_per_week=weekly,
    )


async def run_assessment(
    store: Store, user_id: str, request: AssessmentRequest
) -> AssessmentResponse:
    state, risk_level, intensity = decide_initial_state(request)
    plan = build_plan(state, request.available_minutes)
    low, high = DURATION_RANGES[state.value]

    assessment_id = await store.add_assessment(
        user_id,
        {
            "body_parts": list(request.body_parts),
            "sedentary_minutes": request.sedentary_minutes,
            "available_minutes": request.available_minutes,
            "pain_score": request.pain_score,
            "red_flags": [],
            "initial_state": state.value,
            "risk_level": risk_level,
            "plan": plan.model_dump(),
        },
    )

    session = await store.get_session(user_id)
    if session is None:
        from ..repositories.store import SessionState

        await store.save_session(user_id, SessionState(state=state))
    else:
        await store.save_session(user_id, session.model_copy(update={"state": state}))

    return AssessmentResponse(
        assessment_id=assessment_id,
        initial_state=state.value,
        state_name=STATE_NAMES[state.value],
        risk_level=risk_level,
        duration_range=f"{low}-{high} 分钟",
        intensity=intensity,
        plan=plan,
        disclaimer=MEDICAL_DISCLAIMER,
    )