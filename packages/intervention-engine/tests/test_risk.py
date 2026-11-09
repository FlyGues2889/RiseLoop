from intervention_engine import (
    BodyPart,
    BrliConfig,
    PostureClass,
    RedFlag,
    RiskInput,
    compute_brli,
    cumulative_load,
    short_term_risk,
)


def baseline_payload(**overrides):
    data = dict(
        posture_class=PostureClass.BASELINE,
        posture_confidence=0.9,
        deviation_deg=2,
        posture_duration_minutes=5,
        continuous_sitting_minutes=5,
        daily_sitting_minutes=30,
        minutes_since_last_break=5,
        micro_activity_minutes=5,
        rest_minutes=5,
        activity_density_2h=15,
    )
    data.update(overrides)
    return RiskInput(**data)


def test_baseline_is_low_risk():
    out = compute_brli(baseline_payload())
    assert out.risk_level == "low"
    assert out.brli < 0.35


def test_prolonged_sitting_and_forward_head_increase_risk():
    low = compute_brli(baseline_payload())
    high = compute_brli(
        baseline_payload(
            posture_class=PostureClass.FORWARD_HEAD,
            deviation_deg=30,
            posture_duration_minutes=30,
            continuous_sitting_minutes=60,
            daily_sitting_minutes=300,
            minutes_since_last_break=60,
            micro_activity_minutes=0,
            rest_minutes=0,
            activity_density_2h=0,
        )
    )
    assert high.brli > low.brli
    assert high.risk_level in {"medium", "high", "very_high"}


def test_recovery_reduces_brli():
    base = baseline_payload(
        posture_class=PostureClass.FORWARD_HEAD,
        deviation_deg=30,
        posture_duration_minutes=30,
        continuous_sitting_minutes=60,
        daily_sitting_minutes=300,
        minutes_since_last_break=60,
        micro_activity_minutes=0,
        rest_minutes=0,
        activity_density_2h=0,
    )
    recovered = base.model_copy(
        update={
            "micro_activity_minutes": 15,
            "rest_minutes": 15,
            "activity_density_2h": 60,
        }
    )
    assert compute_brli(recovered).brli < compute_brli(base).brli


def test_symptoms_increase_brli():
    base = baseline_payload(
        posture_class=PostureClass.LATERAL_TILT,
        deviation_deg=25,
        posture_duration_minutes=20,
        continuous_sitting_minutes=45,
        daily_sitting_minutes=240,
        minutes_since_last_break=45,
    )
    symptomatic = base.model_copy(
        update={
            "pain_score": 8,
            "fatigue_score": 8,
            "body_parts": (BodyPart.NECK, BodyPart.SHOULDER),
        }
    )
    assert compute_brli(symptomatic).brli > compute_brli(base).brli
    assert compute_brli(symptomatic).risk_level in {"high", "very_high"}


def test_red_flags_require_medical_advice():
    out = compute_brli(baseline_payload(red_flags=(RedFlag.RADIATING_PAIN,)))
    assert out.needs_medical_advice is True
    assert out.factors[-1].value == 1.0


def test_undetermined_does_not_penalize():
    forward = baseline_payload(
        posture_class=PostureClass.FORWARD_HEAD,
        deviation_deg=30,
        posture_duration_minutes=30,
    )
    undetermined = forward.model_copy(update={"posture_class": PostureClass.UNDETERMINED})
    assert compute_brli(undetermined).brli < compute_brli(forward).brli


def test_config_weights_are_applied():
    config = BrliConfig(alpha=1.0, beta=0.0, gamma=0.0, delta=0.0)
    out = compute_brli(
        baseline_payload(
            posture_class=PostureClass.LATERAL_TILT,
            deviation_deg=20,
            posture_duration_minutes=15,
        ),
        config,
    )
    assert out.brli == out.factors[0].value


def test_cumulative_and_short_term_risk():
    assert cumulative_load([0.2, 0.4, 0.6], interval_minutes=5) == 6.0
    assert short_term_risk([0.2, 0.4, 0.6], window=2) == 0.5


def test_extreme_values_are_clamped():
    out = compute_brli(
        baseline_payload(
            posture_class=PostureClass.LATERAL_TILT,
            posture_confidence=1.0,
            deviation_deg=90,
            posture_duration_minutes=120,
            continuous_sitting_minutes=600,
            daily_sitting_minutes=1440,
            minutes_since_last_break=600,
            pain_score=10,
            fatigue_score=10,
            body_parts=(BodyPart.NECK, BodyPart.SHOULDER, BodyPart.LOWER_BACK),
        )
    )
    assert 0.0 <= out.brli <= 1.0
    assert out.risk_level == "very_high"
