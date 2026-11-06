import json
from functools import lru_cache
from pathlib import Path

from ..cloud.registry import CloudRegistry
from ..core.config import Settings
from ..core.safety import MEDICAL_DISCLAIMER
from ..repositories.store import Store
from ..schemas.qa import QaRequest, QaResponse

KNOWLEDGE_PATH = Path(__file__).resolve().parents[4] / "data" / "knowledge" / "articles.json"
NO_MATCH_ANSWER = (
    "资料中没有直接对应的条目。可以先起身走动 30 秒并观察变化；若症状持续加重请就医。"
)
MAX_ANSWER_CHARS = 150


@lru_cache
def load_articles() -> tuple[dict, ...]:
    if not KNOWLEDGE_PATH.exists():
        return ()
    return tuple(json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8")))


def search_articles(question: str, limit: int = 2) -> list[dict]:
    text = question.lower()
    scored: list[tuple[int, dict]] = []
    for article in load_articles():
        score = sum(2 for tag in article["tags"] if tag.lower() in text)
        if article["title"] in question:
            score += 3
        if score:
            scored.append((score, article))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [article for _, article in scored[:limit]]


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_ANSWER_CHARS else text[: MAX_ANSWER_CHARS - 1] + "…"


def compose_answer(articles: list[dict]) -> str:
    if not articles:
        return NO_MATCH_ANSWER
    primary = articles[0]
    actions = "；".join(primary.get("actions", [])[:2])
    summary = primary.get("summary", "")
    return _clip(f"{actions}。{summary}" if actions else summary)


async def answer_question(
    store: Store,
    cloud: CloudRegistry,
    settings: Settings,
    user_id: str,
    request: QaRequest,
) -> QaResponse:
    articles = search_articles(request.question)
    answer = compose_answer(articles)

    if settings.cloud_provider == "huawei" and cloud.codearts.configured:
        try:
            result = await cloud.codearts.invoke(
                "planning",
                {"question": request.question, "citations": [a["citation"] for a in articles]},
            )
            remote = result.get("output", {}).get("message")
            if isinstance(remote, str) and remote.strip():
                answer = _clip(remote)
        except Exception:
            pass

    session = await store.get_session(user_id)
    state_hint = request.state or (session.state.value if session else None)
    citations = [article["citation"] for article in articles]
    await store.add_qa_log(user_id, request.question, answer, citations)

    return QaResponse(
        answer=answer,
        citations=citations,
        state_hint=state_hint,
        escalated_to_medical=False,
        disclaimer=MEDICAL_DISCLAIMER,
    )