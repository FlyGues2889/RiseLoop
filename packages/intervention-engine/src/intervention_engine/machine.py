from .models import (
    Completion,
    EngineInput,
    EngineOutput,
    Feeling,
    Obstacle,
    RedFlag,
    State,
    StateCounters,
    TransitionType,
)

DURATION_BY_STATE: dict[State, tuple[int, int]] = {
    State.S0: (0, 2),
    State.S1: (3, 5),
    State.S2: (5, 8),
    State.S3: (2, 5),
}

GENTLE_DURATION_BY_STATE: dict[State, tuple[int, int]] = {
    State.S0: (0, 1),
    State.S1: (2, 3),
    State.S2: (3, 5),
    State.S3: (2, 3),
}

ROLLBACK_TARGET: dict[State, State] = {
    State.S3: State.S2,
    State.S2: State.S1,
    State.S1: State.S0,
    State.S0: State.S0,
}

RED_FLAG_LABELS: dict[RedFlag, str] = {
    RedFlag.RADIATING_PAIN: "放射痛",
    RedFlag.NUMBNESS_WORSE: "麻木加重",
    RedFlag.DIZZINESS: "眩晕",
    RedFlag.LEG_WEAKNESS: "下肢无力",
    RedFlag.COTTON_WOOL_GAIT: "踩棉花感",
    RedFlag.BOWEL_BLADDER: "大小便异常",
    RedFlag.PERINEAL_NUMBNESS: "会阴麻木",
    RedFlag.POST_TRAUMA_SEVERE_PAIN: "外伤后剧痛",
}

OBSTACLE_LABELS: dict[Obstacle, str] = {
    Obstacle.BUSY: "太忙",
    Obstacle.TOO_HARD: "动作太难",
    Obstacle.NO_SPACE: "没地方做",
    Obstacle.FORGOT: "忘了",
}


def decide(payload: EngineInput) -> EngineOutput:
    state = payload.state
    feedback = payload.feedback
    counters = payload.counters

    if feedback.red_flags:
        names = "、".join(RED_FLAG_LABELS[flag] for flag in feedback.red_flags)
        return _build(
            state=state,
            to_state=State.S0,
            transition_type=TransitionType.SHORT_CIRCUIT,
            reason=f"命中安全红线：{names}，停止运动并建议就医",
            duration=GENTLE_DURATION_BY_STATE[State.S0],
            intensity="gentle",
            counters=StateCounters(),
            stop_exercise=True,
            medical_advice=True,
        )

    if feedback.feeling is Feeling.WORSE or feedback.next_day_worse:
        worse_streak = counters.worse_streak + 1
        next_counters = StateCounters(
            completed_streak=0,
            skipped_streak=0,
            worse_streak=worse_streak,
            s0_completed=counters.s0_completed,
        )
        if worse_streak >= 2:
            target = ROLLBACK_TARGET[state]
            if target is State.S0:
                next_counters = StateCounters(
                    completed_streak=0,
                    skipped_streak=0,
                    worse_streak=0,
                    s0_completed=0,
                )
            return _build(
                state=state,
                to_state=target,
                transition_type=TransitionType.ROLLBACK,
                reason=f"连续 {worse_streak} 次症状加重，回退至 {target}",
                duration=DURATION_BY_STATE[target],
                intensity="normal",
                counters=next_counters,
            )
        return _build(
            state=state,
            to_state=state,
            transition_type=TransitionType.HOLD,
            reason="症状加重 1 次，保持当前状态并观察，不升级",
            duration=DURATION_BY_STATE[state],
            intensity="normal",
            counters=next_counters,
        )

    if feedback.completion is Completion.SKIPPED:
        skipped_streak = counters.skipped_streak + 1
        next_counters = StateCounters(
            completed_streak=0,
            skipped_streak=skipped_streak,
            worse_streak=0,
            s0_completed=counters.s0_completed,
        )
        if skipped_streak >= 3:
            reason = f"连续 {skipped_streak} 次跳过，同状态更换更短、更低强度动作"
            if feedback.obstacle is not None:
                reason = f"{reason}（障碍：{OBSTACLE_LABELS[feedback.obstacle]}）"
            return _build(
                state=state,
                to_state=state,
                transition_type=TransitionType.DEGRADE,
                reason=reason,
                duration=GENTLE_DURATION_BY_STATE[state],
                intensity="gentle",
                counters=next_counters,
            )
        return _build(
            state=state,
            to_state=state,
            transition_type=TransitionType.HOLD,
            reason=f"连续 {skipped_streak} 次跳过，不升级",
            duration=DURATION_BY_STATE[state],
            intensity="normal",
            counters=next_counters,
        )

    if feedback.completion is Completion.PARTIAL:
        return _build(
            state=state,
            to_state=state,
            transition_type=TransitionType.HOLD,
            reason="部分完成不计入连续完成，维持当前状态",
            duration=DURATION_BY_STATE[state],
            intensity="normal",
            counters=StateCounters(
                completed_streak=0,
                skipped_streak=0,
                worse_streak=0,
                s0_completed=counters.s0_completed,
            ),
        )

    completed_streak = counters.completed_streak + 1

    if state is State.S0:
        s0_completed = counters.s0_completed + 1
        next_counters = StateCounters(
            completed_streak=completed_streak,
            skipped_streak=0,
            worse_streak=0,
            s0_completed=s0_completed,
        )
        if s0_completed >= 2 and feedback.pain_score <= 3 and not feedback.next_day_worse:
            return _build(
                state=State.S0,
                to_state=State.S1,
                transition_type=TransitionType.UPGRADE,
                reason="S0 已完成 2 次、评分 ≤3 且次日无加重，升级至 S1",
                duration=DURATION_BY_STATE[State.S1],
                intensity="normal",
                counters=StateCounters(
                    completed_streak=0,
                    skipped_streak=0,
                    worse_streak=0,
                    s0_completed=s0_completed,
                ),
            )
        return _build(
            state=State.S0,
            to_state=State.S0,
            transition_type=TransitionType.HOLD,
            reason="S0 升级条件未满足（需完成 ≥2 次、评分 ≤3、次日无加重）",
            duration=DURATION_BY_STATE[State.S0],
            intensity="normal",
            counters=next_counters,
        )

    if state is State.S1 and completed_streak >= 5:
        return _build(
            state=State.S1,
            to_state=State.S2,
            transition_type=TransitionType.UPGRADE,
            reason="S1 连续完成 5 次，升级至 S2",
            duration=DURATION_BY_STATE[State.S2],
            intensity="normal",
            counters=StateCounters(
                completed_streak=0,
                skipped_streak=0,
                worse_streak=0,
                s0_completed=counters.s0_completed,
            ),
        )

    if state is State.S2 and completed_streak >= 10:
        return _build(
            state=State.S2,
            to_state=State.S3,
            transition_type=TransitionType.UPGRADE,
            reason="S2 连续完成 10 次，升级至 S3",
            duration=DURATION_BY_STATE[State.S3],
            intensity="normal",
            counters=StateCounters(
                completed_streak=0,
                skipped_streak=0,
                worse_streak=0,
                s0_completed=counters.s0_completed,
            ),
        )

    return _build(
        state=state,
        to_state=state,
        transition_type=TransitionType.HOLD,
        reason="连续完成次数未达升级阈值，维持当前状态",
        duration=DURATION_BY_STATE[state],
        intensity="normal",
        counters=StateCounters(
            completed_streak=completed_streak,
            skipped_streak=0,
            worse_streak=0,
            s0_completed=counters.s0_completed,
        ),
    )


def _build(
    state: State,
    to_state: State,
    transition_type: TransitionType,
    reason: str,
    duration: tuple[int, int],
    intensity: str,
    counters: StateCounters,
    stop_exercise: bool = False,
    medical_advice: bool = False,
) -> EngineOutput:
    return EngineOutput(
        from_state=state,
        to_state=to_state,
        transition_type=transition_type,
        reason=reason,
        duration_minutes=duration,
        intensity=intensity,
        stop_exercise=stop_exercise,
        medical_advice=medical_advice,
        counters=counters,
    )