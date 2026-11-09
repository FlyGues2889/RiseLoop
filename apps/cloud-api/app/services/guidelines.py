"""从 data/knowledge/evidence.json 读取权威指南/文献，供风险响应引用。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE_PATH = ROOT / "data" / "knowledge" / "evidence.json"


class GuidelineCitation(BaseModel):
    evidence_id: str
    title: str
    source_type: str
    year: int | None = None
    key_finding: str | None = None
    url: str


@lru_cache(maxsize=1)
def load_evidence() -> dict[str, dict]:
    try:
        records = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {record.get("id"): record for record in records if record.get("id")}


def citations_for(evidence_ids: Iterable[str]) -> list[GuidelineCitation]:
    indexed = load_evidence()
    seen: set[str] = set()
    citations: list[GuidelineCitation] = []
    for evidence_id in evidence_ids:
        if not evidence_id or evidence_id in seen:
            continue
        record = indexed.get(evidence_id)
        if not record:
            continue
        seen.add(evidence_id)
        citations.append(
            GuidelineCitation(
                evidence_id=evidence_id,
                title=record.get("title") or evidence_id,
                source_type=record.get("source_type") or "unknown",
                year=record.get("year"),
                key_finding=record.get("key_finding"),
                url=record.get("url") or "",
            )
        )
    return citations
