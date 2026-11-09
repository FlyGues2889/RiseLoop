"""台账回归：保证 evidence.json 始终通过 G4，并守住 G5 的底线。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "knowledge" / "evidence.json"
TOPICS = [
    "sedentary-threshold",
    "micro-break-workplace",
    "neck-shoulder",
    "low-back",
    "safety-redflag",
    "bct",
]


def load_records() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_evidence_passes_g4_schema() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate_evidence.py", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_topic_and_guideline_coverage() -> None:
    records = load_records()
    counts = Counter()
    for record in records:
        counts.update(set(record.get("topics") or []))

    assert len(records) >= 30
    for topic in TOPICS:
        assert counts[topic] >= 2, f"{topic} 覆盖不足：{counts[topic]}"
    assert sum(1 for record in records if record.get("evidence_level") == "guideline") >= 3


def test_g2_identity_fields() -> None:
    for record in load_records():
        assert record.get("id")
        assert record.get("source_type")
        assert any(record.get(field) for field in ("doi", "pmid", "url")), record["id"]


def test_records_are_verified_and_findings_are_bounded() -> None:
    records = load_records()
    for record in records:
        assert record.get("verified") is True, record["id"]
        finding = record.get("key_finding")
        assert isinstance(finding, str) and 1 <= len(finding) <= 80, record["id"]
        assert record.get("provenance", {}).get("request_url"), record["id"]
        assert record.get("provenance", {}).get("task_id"), record["id"]
