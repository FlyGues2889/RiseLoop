import json
import uuid
from datetime import UTC, datetime

from intervention_engine import State, StateCounters
from sqlalchemy import func, select

from ..cloud.dcs import DcsService
from ..db.models import (
    Action,
    Assessment,
    Base,
    InterventionLog,
    QaLog,
    SafetyEvent,
    SittingEvent,
    StateTransition,
    User,
)
from ..db.session import get_sessionmaker, init_sessionmaker
from ..db.seed import load_seed_actions
from .store import ActionRecord, SessionState, UserRecord


def _session_key(user_id: str) -> str:
    return f"session:{user_id}:state"


class SqlStore:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._sessionmaker = init_sessionmaker(settings)
        self._redis = DcsService(settings)
        self._local_sessions: dict[str, SessionState] = {}

    def _session(self):
        if self._sessionmaker is None:
            raise RuntimeError("RDS is not configured")
        return self._sessionmaker()

    async def create_schema(self) -> None:
        if self._sessionmaker is None:
            return
        async with self._sessionmaker() as session:
            connection = await session.connection()
            await connection.run_sync(Base.metadata.create_all)
            await session.commit()
        await self.seed_actions()

    async def seed_actions(self) -> None:
        async with self._session() as session:
            existing = (await session.execute(select(Action.id))).scalars().all()
            known = set(existing)
            for item in load_seed_actions():
                if item["id"] in known:
                    continue
                session.add(Action(**item))
            await session.commit()

    async def create_user(self, email: str, password_hash: str) -> UserRecord:
        async with self._session() as session:
            user = User(id=str(uuid.uuid4()), email=email.lower(), password_hash=password_hash)
            session.add(user)
            await session.commit()
            return UserRecord(id=user.id, email=user.email, password_hash=user.password_hash)

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        async with self._session() as session:
            user = (
                await session.execute(select(User).where(User.email == email.lower()))
            ).scalar_one_or_none()
            if user is None:
                return None
            return UserRecord(id=user.id, email=user.email, password_hash=user.password_hash)

    async def get_user(self, user_id: str) -> UserRecord | None:
        async with self._session() as session:
            user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                return None
            return UserRecord(id=user.id, email=user.email, password_hash=user.password_hash)

    async def add_assessment(self, user_id: str, payload: dict) -> str:
        async with self._session() as session:
            record = Assessment(
                id=str(uuid.uuid4()),
                user_id=user_id,
                body_parts=payload["body_parts"],
                sedentary_minutes=payload["sedentary_minutes"],
                available_minutes=payload["available_minutes"],
                pain_score=payload["pain_score"],
                red_flags=payload.get("red_flags", []),
                initial_state=payload["initial_state"],
                risk_level=payload["risk_level"],
                plan=payload.get("plan", {}),
            )
            session.add(record)
            await session.commit()
            return record.id

    async def latest_assessment(self, user_id: str) -> dict | None:
        async with self._session() as session:
            record = (
                await session.execute(
                    select(Assessment)
                    .where(Assessment.user_id == user_id)
                    .order_by(Assessment.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if record is None:
                return None
            return {
                "id": record.id,
                "body_parts": record.body_parts,
                "sedentary_minutes": record.sedentary_minutes,
                "available_minutes": record.available_minutes,
                "pain_score": record.pain_score,
                "red_flags": record.red_flags,
                "initial_state": record.initial_state,
                "risk_level": record.risk_level,
                "plan": record.plan,
            }

    async def add_transition(
        self, user_id: str, from_state: str, to_state: str, reason: str, transition_type: str
    ) -> None:
        async with self._session() as session:
            session.add(
                StateTransition(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    from_state=from_state,
                    to_state=to_state,
                    reason=reason,
                    transition_type=transition_type,
                )
            )
            await session.commit()

    async def add_intervention_log(self, user_id: str, payload: dict) -> str:
        async with self._session() as session:
            record = InterventionLog(
                id=str(uuid.uuid4()),
                user_id=user_id,
                action_id=payload["action_id"],
                state=payload["state"],
                completion=payload["completion"],
                feeling=payload["feeling"],
                pain_score=payload["pain_score"],
                obstacle=payload.get("obstacle"),
                pushed_at=payload.get("pushed_at"),
            )
            session.add(record)
            await session.commit()
            return record.id

    async def list_actions(
        self, state: str, body_parts: list[str] | None = None, max_minutes: int | None = None
    ) -> list[ActionRecord]:
        async with self._session() as session:
            statement = select(Action).where(Action.state == state, Action.enabled.is_(True))
            if max_minutes is not None:
                statement = statement.where(Action.duration_minutes <= max_minutes)
            rows = (await session.execute(statement)).scalars().all()
        actions = [
            ActionRecord(
                id=row.id,
                name=row.name,
                state=row.state,
                body_parts=row.body_parts,
                duration_minutes=row.duration_minutes,
                intensity=row.intensity,
                steps=row.steps,
                caution=row.caution or "",
            )
            for row in rows
        ]
        if body_parts:
            actions = [action for action in actions if set(action.body_parts) & set(body_parts)]
        return sorted(actions, key=lambda action: action.duration_minutes)

    async def add_sitting_event(self, user_id: str, event_type: str, source: str = "manual") -> None:
        async with self._session() as session:
            session.add(
                SittingEvent(
                    id=str(uuid.uuid4()), user_id=user_id, event_type=event_type, source=source
                )
            )
            await session.commit()

    async def record_safety_event(
        self, user_id: str | None, source: str, red_flags: list[str], action_taken: str
    ) -> None:
        async with self._session() as session:
            session.add(
                SafetyEvent(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    source=source,
                    red_flags=list(red_flags),
                    action_taken=action_taken,
                )
            )
            await session.commit()

    async def add_qa_log(
        self, user_id: str, question: str, answer: str, citations: list[str]
    ) -> None:
        async with self._session() as session:
            session.add(
                QaLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    question=question,
                    answer=answer,
                    citations=list(citations),
                )
            )
            await session.commit()

    async def list_intervention_logs(self, user_id: str, since: datetime) -> list[dict]:
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(InterventionLog)
                    .where(
                        InterventionLog.user_id == user_id,
                        InterventionLog.created_at >= since,
                    )
                    .order_by(InterventionLog.created_at.asc())
                )
            ).scalars().all()
        return [
            {
                "state": row.state,
                "completion": row.completion,
                "feeling": row.feeling,
                "pain_score": row.pain_score,
                "obstacle": row.obstacle,
                "occurred_at": row.created_at,
            }
            for row in rows
        ]

    async def list_transitions(self, user_id: str, since: datetime) -> list[dict]:
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(StateTransition).where(
                        StateTransition.user_id == user_id,
                        StateTransition.created_at >= since,
                    )
                )
            ).scalars().all()
        return [
            {
                "from_state": row.from_state,
                "to_state": row.to_state,
                "transition_type": row.transition_type,
                "timestamp": row.created_at,
            }
            for row in rows
        ]

    async def count_safety_events(self, user_id: str, since: datetime) -> int:
        async with self._session() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(SafetyEvent)
                        .where(
                            SafetyEvent.user_id == user_id,
                            SafetyEvent.created_at >= since,
                        )
                    )
                ).scalar_one()
            )

    async def count_sitting_events(self, user_id: str, since: datetime) -> int:
        async with self._session() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(SittingEvent)
                        .where(
                            SittingEvent.user_id == user_id,
                            SittingEvent.occurred_at >= since,
                        )
                    )
                ).scalar_one()
            )

    async def get_session(self, user_id: str) -> SessionState | None:
        raw = await self._read_raw(user_id)
        if raw is None:
            return None
        payload = json.loads(raw)
        return SessionState(
            state=State(payload["state"]),
            counters=StateCounters(**payload.get("counters", {})),
            sitting_minutes=payload.get("sitting_minutes", 0),
            last_push_at=datetime.fromisoformat(payload["last_push_at"])
            if payload.get("last_push_at")
            else None,
            pending_action_id=payload.get("pending_action_id"),
            updated_at=datetime.fromisoformat(payload["updated_at"])
            if payload.get("updated_at")
            else datetime.now(UTC),
        )

    async def save_session(self, user_id: str, session: SessionState) -> None:
        session = session.model_copy(update={"updated_at": datetime.now(UTC)})
        payload = session.model_dump(mode="json")
        raw = json.dumps(payload, ensure_ascii=False)
        self._local_sessions[user_id] = session
        if self._settings.resolved_redis_url():
            try:
                await self._redis.set(_session_key(user_id), raw, ttl_seconds=60 * 60 * 24)
            except Exception:
                pass

    async def _read_raw(self, user_id: str) -> str | None:
        if self._settings.resolved_redis_url():
            try:
                raw = await self._redis.get(_session_key(user_id))
                if raw:
                    return raw
            except Exception:
                pass
        cached = self._local_sessions.get(user_id)
        return json.dumps(cached.model_dump(mode="json"), ensure_ascii=False) if cached else None

    async def close(self) -> None:
        await self._redis.close()