import uuid
from datetime import UTC, datetime
from typing import Protocol

from intervention_engine import State, StateCounters
from pydantic import BaseModel, Field

from ..db.seed import load_seed_actions


class UserRecord(BaseModel):
    id: str
    email: str
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ActionRecord(BaseModel):
    id: str
    name: str
    state: State
    body_parts: list[str]
    duration_minutes: int
    intensity: str
    steps: list[str]
    caution: str = ""


class SessionState(BaseModel):
    state: State
    counters: StateCounters = Field(default_factory=StateCounters)
    sitting_minutes: int = 0
    last_push_at: datetime | None = None
    pending_action_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_cooldown_active(self, cooldown_minutes: int) -> bool:
        if self.last_push_at is None:
            return False
        elapsed = datetime.now(UTC) - self.last_push_at
        return elapsed.total_seconds() < cooldown_minutes * 60


class Store(Protocol):
    async def create_user(self, email: str, password_hash: str) -> UserRecord: ...

    async def get_user_by_email(self, email: str) -> UserRecord | None: ...

    async def get_user(self, user_id: str) -> UserRecord | None: ...

    async def add_assessment(self, user_id: str, payload: dict) -> str: ...

    async def latest_assessment(self, user_id: str) -> dict | None: ...

    async def add_transition(
        self, user_id: str, from_state: str, to_state: str, reason: str, transition_type: str
    ) -> None: ...

    async def add_intervention_log(self, user_id: str, payload: dict) -> str: ...

    async def list_actions(
        self, state: str, body_parts: list[str] | None = None, max_minutes: int | None = None
    ) -> list[ActionRecord]: ...

    async def add_sitting_event(self, user_id: str, event_type: str, source: str = "manual") -> None: ...

    async def record_safety_event(
        self, user_id: str | None, source: str, red_flags: list[str], action_taken: str
    ) -> None: ...

    async def add_qa_log(
        self, user_id: str, question: str, answer: str, citations: list[str]
    ) -> None: ...

    async def list_intervention_logs(self, user_id: str, since: datetime) -> list[dict]: ...

    async def list_transitions(self, user_id: str, since: datetime) -> list[dict]: ...

    async def count_safety_events(self, user_id: str, since: datetime) -> int: ...

    async def count_sitting_events(self, user_id: str, since: datetime) -> int: ...

    async def get_session(self, user_id: str) -> SessionState | None: ...

    async def save_session(self, user_id: str, session: SessionState) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}
        self._emails: dict[str, str] = {}
        self._assessments: dict[str, dict] = {}
        self._latest_assessment: dict[str, dict] = {}
        self._transitions: dict[str, list[dict]] = {}
        self._logs: dict[str, list[dict]] = {}
        self._sessions: dict[str, SessionState] = {}
        self._sitting_events: list[dict] = []
        self._safety_events: list[dict] = []
        self._qa_logs: list[dict] = []
        self._actions = [ActionRecord(**item) for item in load_seed_actions()]

    @property
    def transitions(self) -> dict[str, list[dict]]:
        return self._transitions

    @property
    def safety_events(self) -> list[dict]:
        return self._safety_events

    async def create_user(self, email: str, password_hash: str) -> UserRecord:
        record = UserRecord(id=str(uuid.uuid4()), email=email.lower(), password_hash=password_hash)
        self._users[record.id] = record
        self._emails[record.email] = record.id
        return record

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        user_id = self._emails.get(email.lower())
        return self._users.get(user_id) if user_id else None

    async def get_user(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    async def add_assessment(self, user_id: str, payload: dict) -> str:
        record = {"id": str(uuid.uuid4()), "user_id": user_id, **payload}
        self._assessments[record["id"]] = record
        self._latest_assessment[user_id] = record
        return record["id"]

    async def latest_assessment(self, user_id: str) -> dict | None:
        return self._latest_assessment.get(user_id)

    async def add_transition(
        self, user_id: str, from_state: str, to_state: str, reason: str, transition_type: str
    ) -> None:
        self._transitions.setdefault(user_id, []).append(
            {
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "transition_type": transition_type,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def add_intervention_log(self, user_id: str, payload: dict) -> str:
        record = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "occurred_at": datetime.now(UTC),
            **payload,
        }
        self._logs.setdefault(user_id, []).append(record)
        return record["id"]

    async def list_intervention_logs(self, user_id: str, since: datetime) -> list[dict]:
        return [
            item for item in self._logs.get(user_id, []) if item["occurred_at"] >= since
        ]

    async def list_transitions(self, user_id: str, since: datetime) -> list[dict]:
        return [
            item
            for item in self._transitions.get(user_id, [])
            if datetime.fromisoformat(item["timestamp"]) >= since
        ]

    async def count_safety_events(self, user_id: str, since: datetime) -> int:
        return sum(
            1
            for item in self._safety_events
            if item["user_id"] == user_id
            and datetime.fromisoformat(item["timestamp"]) >= since
        )

    async def count_sitting_events(self, user_id: str, since: datetime) -> int:
        return sum(
            1
            for item in self._sitting_events
            if item["user_id"] == user_id
            and datetime.fromisoformat(item["timestamp"]) >= since
        )

    async def add_qa_log(
        self, user_id: str, question: str, answer: str, citations: list[str]
    ) -> None:
        self._qa_logs.append(
            {
                "user_id": user_id,
                "question": question,
                "answer": answer,
                "citations": list(citations),
                "created_at": datetime.now(UTC),
            }
        )

    async def list_actions(
        self, state: str, body_parts: list[str] | None = None, max_minutes: int | None = None
    ) -> list[ActionRecord]:
        candidates = [action for action in self._actions if action.state == state]
        if body_parts:
            candidates = [
                action for action in candidates if set(action.body_parts) & set(body_parts)
            ]
        if max_minutes is not None:
            candidates = [
                action for action in candidates if action.duration_minutes <= max_minutes
            ]
        return sorted(candidates, key=lambda action: action.duration_minutes)

    async def add_sitting_event(self, user_id: str, event_type: str, source: str = "manual") -> None:
        self._sitting_events.append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "source": source,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def record_safety_event(
        self, user_id: str | None, source: str, red_flags: list[str], action_taken: str
    ) -> None:
        self._safety_events.append(
            {
                "user_id": user_id,
                "source": source,
                "red_flags": list(red_flags),
                "action_taken": action_taken,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def get_session(self, user_id: str) -> SessionState | None:
        return self._sessions.get(user_id)

    async def save_session(self, user_id: str, session: SessionState) -> None:
        self._sessions[user_id] = session.model_copy(
            update={"updated_at": datetime.now(UTC)}
        )


def build_store(settings) -> Store:
    if settings.store_backend == "sql":
        from .sql_store import SqlStore

        return SqlStore(settings)
    return MemoryStore()