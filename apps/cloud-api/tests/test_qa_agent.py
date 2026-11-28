"""问答的模型通道：有依据才生成，生成失败退回原文，没有依据绝不调用。"""

import pytest

from app.core.config import Settings
from app.services.qa import NO_MATCH_ANSWER, answer_question
from app.schemas.qa import QaRequest


class FakeStore:
    def __init__(self):
        self.logs = []

    async def get_session(self, user_id):
        return None

    async def add_qa_log(self, user_id, question, answer, citations):
        self.logs.append((question, answer, citations))


class FakeMaaS:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    configured = True

    async def answer(self, question, citations, state_hint):
        self.calls.append((question, citations, state_hint))
        if self.error:
            raise self.error
        return self.reply


class FakeCodeArts:
    configured = False


class FakeCloud:
    def __init__(self, maas):
        self.maas = maas
        self.codearts = FakeCodeArts()


def settings():
    return Settings(
        cloud_provider="huawei",
        maas_endpoint="https://maas.example.com/v1",
        maas_api_key="test-key",
    )


@pytest.mark.asyncio
async def test_grounded_answer_uses_model_with_citations():
    maas = FakeMaaS(reply="先坐直收下巴 5 秒，重复 5 次。")
    store = FakeStore()
    response = await answer_question(
        store, FakeCloud(maas), settings(), "u1", QaRequest(question="开会时颈肩紧张怎么办")
    )
    assert response.answer == "先坐直收下巴 5 秒，重复 5 次。"
    assert response.citations
    assert maas.calls and maas.calls[0][1], "应当把检索到的条目作为依据传下去"


@pytest.mark.asyncio
async def test_model_failure_falls_back_to_knowledge_text():
    maas = FakeMaaS(error=RuntimeError("timeout"))
    store = FakeStore()
    response = await answer_question(
        store, FakeCloud(maas), settings(), "u1", QaRequest(question="开会时颈肩紧张怎么办")
    )
    assert response.answer != NO_MATCH_ANSWER
    assert response.citations


@pytest.mark.asyncio
async def test_no_match_never_calls_model():
    maas = FakeMaaS(reply="编造的回答")
    store = FakeStore()
    response = await answer_question(
        store, FakeCloud(maas), settings(), "u1", QaRequest(question="今天基金收益怎么样")
    )
    assert response.answer == NO_MATCH_ANSWER
    assert response.citations == []
    assert maas.calls == []
