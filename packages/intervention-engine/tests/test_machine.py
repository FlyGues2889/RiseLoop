import pytest

from intervention_engine import (
    Completion,
    EngineInput,
    Feedback,
    Feeling,
    Obstacle,
    RedFlag,
    State,
    StateCounters,
    TransitionType,
    decide,
)


def run(
    state: str,
    completion: str = "completed",
    feeling: str = "same",
    counters: StateCounters | None = None,
    **kwargs,
):
    return decide(
        EngineInput(
            state=State(state),
            feedback=Feedback(
                completion=Completion(completion),
                feeling=Feeling(feeling),
                **kwargs,
            ),
            counters=counters or StateCounters(),
        )
    )


@pytest.mark.parametrize("state", ["S0", "S1", "S2", "S3"])
def test_red_flag_short_circuits_from_any_state(state):
    out = run(state, red_flags=[RedFlag.RADIATING_PAIN])
    assert out.transition_type is TransitionType.SHORT_CIRCUIT
    assert out.from_state is State(state)
    assert out.to_state is State.S0
    assert out.stop_exercise is True
    assert out.medical_advice is True
    assert out.duration_minutes == (0, 1)
    assert out.intensity == "gentle"
    assert out.counters == StateCounters()


def test_red_flag_has_priority_over_worse_feeling():
    out = run(
        "S2",
        feeling="worse",
        red_flags=[RedFlag.NUMBNESS_WORSE],
        counters=StateCounters(worse_streak=1),
    )
    assert out.transition_type is TransitionType.SHORT_CIRCUIT
    assert out.to_state is State.S0


@pytest.mark.parametrize(
    ("state", "target"),
    [("S1", "S0"), ("S2", "S1"), ("S3", "S2"), ("S0", "S0")],
)
def test_two_consecutive_worse_feedback_rolls_back_one_state(state, target):
    out = run(state, feeling="worse", counters=StateCounters(worse_streak=1))
    assert out.transition_type is TransitionType.ROLLBACK
    assert out.to_state is State(target)
    assert out.stop_exercise is False
    assert out.medical_advice is False


def test_single_worse_feedback_holds_without_upgrade():
    out = run("S2", feeling="worse")
    assert out.transition_type is TransitionType.HOLD
    assert out.to_state is State.S2
    assert out.counters.worse_streak == 1


def test_next_day_worse_counts_as_symptom_worsening():
    out = run("S1", next_day_worse=True, counters=StateCounters(worse_streak=1))
    assert out.transition_type is TransitionType.ROLLBACK
    assert out.to_state is State.S0


def test_rollback_to_s0_resets_s0_completion_counter():
    out = run(
        "S1",
        feeling="worse",
        counters=StateCounters(worse_streak=1, s0_completed=3),
    )
    assert out.to_state is State.S0
    assert out.counters.s0_completed == 0


@pytest.mark.parametrize("skipped_streak", [0, 1, 2])
def test_first_two_skips_do_not_upgrade(skipped_streak):
    out = run(
        "S1",
        completion="skipped",
        counters=StateCounters(skipped_streak=skipped_streak),
    )
    if skipped_streak >= 2:
        assert out.transition_type is TransitionType.DEGRADE
    else:
        assert out.transition_type is TransitionType.HOLD
    assert out.to_state is State.S1


def test_third_consecutive_skip_degrades_without_state_change():
    out = run(
        "S2",
        completion="skipped",
        counters=StateCounters(skipped_streak=2),
    )
    assert out.transition_type is TransitionType.DEGRADE
    assert out.from_state is State.S2
    assert out.to_state is State.S2
    assert out.intensity == "gentle"
    assert out.duration_minutes == (3, 5)


def test_degrade_reason_carries_obstacle():
    out = run(
        "S1",
        completion="skipped",
        counters=StateCounters(skipped_streak=2),
        obstacle=Obstacle.BUSY,
    )
    assert "太忙" in out.reason


def test_s0_upgrades_to_s1_after_two_completions_with_low_pain():
    out = run(
        "S0",
        pain_score=2,
        counters=StateCounters(s0_completed=1),
    )
    assert out.transition_type is TransitionType.UPGRADE
    assert out.to_state is State.S1
    assert out.counters.completed_streak == 0
    assert out.counters.s0_completed == 2


def test_s0_holds_when_pain_score_above_threshold():
    out = run(
        "S0",
        pain_score=4,
        counters=StateCounters(s0_completed=1),
    )
    assert out.transition_type is TransitionType.HOLD
    assert out.to_state is State.S0


def test_s0_first_completion_does_not_upgrade():
    out = run("S0", pain_score=1)
    assert out.transition_type is TransitionType.HOLD
    assert out.counters.s0_completed == 1


@pytest.mark.parametrize(("streak", "expected"), [(3, "S1"), (4, "S2"), (5, "S2")])
def test_s1_upgrade_boundary(streak, expected):
    out = run("S1", counters=StateCounters(completed_streak=streak))
    if streak >= 4:
        assert out.transition_type is TransitionType.UPGRADE
        assert out.to_state is State.S2
    else:
        assert out.transition_type is TransitionType.HOLD
        assert out.to_state is State.S1


@pytest.mark.parametrize(("streak", "expected"), [(8, "S2"), (9, "S3"), (10, "S3")])
def test_s2_upgrade_boundary(streak, expected):
    out = run("S2", counters=StateCounters(completed_streak=streak))
    if streak >= 9:
        assert out.transition_type is TransitionType.UPGRADE
        assert out.to_state is State.S3
    else:
        assert out.transition_type is TransitionType.HOLD
        assert out.to_state is State.S2


def test_s3_completion_maintains_state():
    out = run("S3", counters=StateCounters(completed_streak=99))
    assert out.transition_type is TransitionType.HOLD
    assert out.to_state is State.S3


def test_partial_completion_resets_completion_streak():
    out = run(
        "S1",
        completion="partial",
        counters=StateCounters(completed_streak=4, skipped_streak=2),
    )
    assert out.transition_type is TransitionType.HOLD
    assert out.counters.completed_streak == 0
    assert out.counters.skipped_streak == 0


def test_completed_feedback_resets_skip_and_worse_streaks():
    out = run(
        "S1",
        counters=StateCounters(skipped_streak=2, worse_streak=1, completed_streak=1),
    )
    assert out.counters.skipped_streak == 0
    assert out.counters.worse_streak == 0
    assert out.counters.completed_streak == 2


def test_decide_is_pure():
    payload = EngineInput(
        state=State.S1,
        feedback=Feedback(completion=Completion.COMPLETED),
        counters=StateCounters(completed_streak=4),
    )
    assert decide(payload) == decide(payload)