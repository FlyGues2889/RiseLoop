from intervention_engine import State

from app.repositories.store import ActionRecord
from app.services.heartbeat import _rank_actions


def _action(action_id: str, state: State, *, desk: bool, minutes: int, parts=None) -> ActionRecord:
    return ActionRecord(
        id=action_id,
        name=action_id,
        state=state,
        body_parts=parts or ["neck"],
        duration_minutes=minutes,
        intensity="normal",
        desk_friendly=desk,
        steps=["一步"],
        caution="",
    )


def test_rank_prefers_desk_friendly_within_same_state():
    candidates = [
        (_action("standing", State.S1, desk=False, minutes=1), State.S1),
        (_action("seated", State.S1, desk=True, minutes=3), State.S1),
    ]

    ranked = _rank_actions(candidates, State.S1, ["neck"])

    assert [action.id for action, _ in ranked] == ["seated", "standing"]


def test_rank_keeps_current_state_ahead_of_desk_friendly_lower_state():
    candidates = [
        (_action("lower-seated", State.S0, desk=True, minutes=1), State.S0),
        (_action("current-standing", State.S1, desk=False, minutes=1), State.S1),
    ]

    ranked = _rank_actions(candidates, State.S1, ["neck"])

    assert ranked[0][0].id == "current-standing"


def test_rank_caps_same_state_items_when_fallback_present():
    candidates = [
        (_action("s1-a", State.S1, desk=True, minutes=1), State.S1),
        (_action("s1-b", State.S1, desk=True, minutes=2), State.S1),
        (_action("s1-c", State.S1, desk=False, minutes=3), State.S1),
        (_action("s0-fallback", State.S0, desk=True, minutes=1), State.S0),
    ]

    ranked = _rank_actions(candidates, State.S1, None, max_same_state=2)

    ids = [action.id for action, _ in ranked]
    assert ids == ["s1-a", "s1-b", "s0-fallback"]
