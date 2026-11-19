"""校验采集/合成数据：契约、特征一致性、标签与隐私边界。

用法：python scripts/modelarts/dataset_check.py data/posture/frames.jsonl
退出码 0 表示可训练，1 表示存在必须修复的错误。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import posture_contract as contract

DEFAULT_TOLERANCE = 1e-3
REQUIRED_KEYS = {"keypoints", "features", "label", "subject"}
ALLOWED_KEYS = REQUIRED_KEYS | {
    "frame_id",
    "ts",
    "device",
    "scene",
    "label_source",
    "origin",
    "note",
}
FORBIDDEN_KEYS = {
    "image",
    "images",
    "frame",
    "frames",
    "pixel",
    "pixels",
    "base64",
    "jpeg",
    "jpg",
    "png",
    "screenshot",
    "video",
    "photo",
}
VALID_ORIGINS = {"capture", "synthetic"}
VALID_LABEL_SOURCES = {"human", "prelabel"}


@dataclass
class Report:
    frames: int = 0
    labels: Counter = field(default_factory=Counter)
    origins: Counter = field(default_factory=Counter)
    subjects: set = field(default_factory=set)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, line: int, message: str) -> None:
        self.errors.append({"line": line, "error": message})

    def warn(self, line: int, message: str) -> None:
        self.warnings.append({"line": line, "warning": message})

    def summary(self, limit: int = 20) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "frames": self.frames,
            "labels": dict(sorted(self.labels.items())),
            "origins": dict(sorted(self.origins.items())),
            "subjects": len(self.subjects),
            "errors": len(self.errors),
            "error_sample": self.errors[:limit],
            "warnings": len(self.warnings),
            "warning_sample": self.warnings[:limit],
        }


def check_frame(frame: dict[str, Any], line: int, tolerance: float) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    extra = set(frame) & FORBIDDEN_KEYS
    if extra:
        errors.append(f"禁止字段：{', '.join(sorted(extra))}")
    unknown = set(frame) - ALLOWED_KEYS - FORBIDDEN_KEYS
    if unknown:
        warnings.append(f"未识别字段：{', '.join(sorted(unknown))}")
    missing = REQUIRED_KEYS - set(frame)
    if missing:
        errors.append(f"缺字段：{', '.join(sorted(missing))}")
        return errors, warnings

    label = frame.get("label")
    if label not in contract.LABELS:
        errors.append(f"未知类别：{label!r}")

    origin = frame.get("origin")
    if origin is not None and origin not in VALID_ORIGINS:
        errors.append(f"origin 必须是 {sorted(VALID_ORIGINS)}，实际 {origin!r}")
    label_source = frame.get("label_source")
    if label_source is not None and label_source not in VALID_LABEL_SOURCES:
        errors.append(f"label_source 必须是 {sorted(VALID_LABEL_SOURCES)}，实际 {label_source!r}")
    if label_source != "human" and origin == "capture":
        warnings.append("真实采集帧不是人工标签")

    if not str(frame.get("subject", "")).strip():
        errors.append("subject 为空")

    try:
        contract.validate_keypoints(frame["keypoints"])
        computed = contract.features_from_keypoints(frame["keypoints"])
    except contract.ContractError as exc:
        errors.append(str(exc))
        return errors, warnings

    stored = frame["features"]
    if not isinstance(stored, dict):
        errors.append("features 必须是对象")
        return errors, warnings
    for name in contract.FEATURE_ORDER:
        if name not in stored:
            errors.append(f"特征缺字段：{name}")
            continue
        try:
            delta = abs(float(stored[name]) - float(computed[name]))
        except (TypeError, ValueError):
            errors.append(f"特征不是数值：{name}")
            continue
        if delta > tolerance:
            errors.append(f"特征与关键点不一致：{name} 差 {delta:.6f}")

    return errors, warnings


def check_dataset(path: Path, tolerance: float = DEFAULT_TOLERANCE) -> Report:
    report = Report()
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError as exc:
                report.error(line_number, f"JSON 解析失败：{exc.msg}")
                continue
            if not isinstance(frame, dict):
                report.error(line_number, "每行必须是 JSON 对象")
                continue

            report.frames += 1
            report.labels[frame.get("label")] += 1
            report.origins[frame.get("origin", "unknown")] += 1
            report.subjects.add(frame.get("subject"))

            errors, warnings = check_frame(frame, line_number, tolerance)
            for message in errors:
                report.error(line_number, message)
            for message in warnings:
                report.warn(line_number, message)
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验姿态 jsonl 是否符合端云契约")
    parser.add_argument("path", type=Path)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    args = parser.parse_args(argv)

    report = check_dataset(args.path, args.tolerance)
    print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
