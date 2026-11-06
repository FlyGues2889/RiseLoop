import json

import pytest

import action_tools
import health_tools


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)


class FakeBackend:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.redis = FakeRedis()
        self.rows = rows or []
        self.executed: list[tuple[str, tuple]] = []

    async def redis_get(self, key: str):
        return await self.redis.get(key)

    async def redis_set(self, key: str, value: str, ttl_seconds: int | None = None):
        await self.redis.set(key, value, ex=ttl_seconds)

    async def redis_delete(self, key: str):
        await self.redis.delete(key)

    async def fetch(self, query: str, *args):
        self.executed.append((query, args))
        return self.rows

    async def fetchrow(self, query: str, *args):
        self.executed.append((query, args))
        return self.rows[0] if self.rows else None

    async def fetchval(self, query: str, *args):
        return 1


@pytest.mark.asyncio
async def test_read_realtime_state_defaults():
    backend = FakeBackend()
    state = await health_tools.read_realtime_state(backend, "u1")
    assert state["user_id"] == "u1"
    assert state["state"] == "S1"
    assert state["sitting_minutes"] == 0
    assert state["pending_intervention"] is None


@pytest.mark.asyncio
async def test_read_realtime_state_merges_redis_keys():
    backend = FakeBackend()
    await backend.redis.set("session:u1:state", json.dumps({"state": "S2", "counters": {"completed_streak": 3}}))
    await backend.redis.set("sitting:u1:timer", "52")
    await backend.redis.set("pending_intervention:u1", json.dumps({"action_id": "a1"}))

    state = await health_tools.read_realtime_state(backend, "u1")
    assert state["state"] == "S2"
    assert state["sitting_minutes"] == 52
    assert state["pending_intervention"]["action_id"] == "a1"


@pytest.mark.asyncio
async def test_write_intervention_result_persists_and_clears_realtime():
    backend = FakeBackend()
    await backend.redis.set("session:u1:state", json.dumps({"state": "S1"}))
    await backend.redis.set("pending_intervention:u1", json.dumps({"action_id": "a1"}))
    await backend.redis.set("sitting:u1:timer", "45")

    result = await health_tools.write_intervention_result(
        backend,
        user_id="u1",
        action_id="a1",
        state="S1",
        completion="completed",
        feeling="better",
        pain_score=2,
        to_state="S2",
        reason="连续完成 5 次",
        transition_type="upgrade",
    )

    assert result["written"] is True
    assert result["state"] == "S2"
    queries = " ".join(query for query, _ in backend.executed)
    assert "intervention_logs" in queries
    assert "state_transitions" in queries
    assert await backend.redis.get("pending_intervention:u1") is None
    assert await backend.redis.get("sitting:u1:timer") == "0"
    assert json.loads(await backend.redis.get("session:u1:state"))["state"] == "S2"


@pytest.mark.asyncio
async def test_get_actions_filters_by_body_part_and_duration():
    rows = [
        {
            "id": "s1-a",
            "name": "颈部",
            "state": "S1",
            "body_parts": ["neck"],
            "duration_minutes": 3,
            "intensity": "normal",
            "steps": ["a"],
            "caution": "",
        },
        {
            "id": "s1-b",
            "name": "腿部",
            "state": "S1",
            "body_parts": json.dumps(["hip"]),
            "duration_minutes": 4,
            "intensity": "normal",
            "steps": json.dumps(["b"]),
            "caution": None,
        },
    ]
    backend = FakeBackend(rows)
    actions = await action_tools.get_actions_by_state(
        backend, state="S1", body_parts=["neck"], max_minutes=5
    )
    assert [action["id"] for action in actions] == ["s1-a"]
    assert actions[0]["steps"] == ["a"]


@pytest.mark.asyncio
async def test_get_actions_respects_limit():
    rows = [
        {
            "id": f"s2-{index}",
            "name": "x",
            "state": "S2",
            "body_parts": ["low_back"],
            "duration_minutes": index,
            "intensity": "normal",
            "steps": [],
            "caution": "",
        }
        for index in range(1, 6)
    ]
    backend = FakeBackend(rows)
    actions = await action_tools.get_actions_by_state(backend, state="S2", limit=2)
    assert len(actions) == 2