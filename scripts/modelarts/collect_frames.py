"""Convert end-side MediaPipe output into the training jsonl schema.

The collector is deliberately keypoint-only:

* it rejects any record containing image / video / base64 / pixel fields;
* it never writes frames, crops or screenshots;
* it recomputes the contract features with the contract module, using the
  per-subject median of ``label=baseline`` frames as the neutral reference;
* ``--append`` adds to an existing dataset without rewriting it.

Typical use::

    python scripts/modelarts/collect_frames.py \
        --input mediapipe_frames.jsonl \
        --out scripts/modelarts/data/frames.jsonl \
        --subject s01 --device demo-laptop-cam0 --scene office-chair-desk \
        --label forward_head --label-source human --origin capture --append
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, TextIO

from label_policy import prelabel
from posture_contract import (
    BASELINE_DEFAULTS,
    BASELINE_ORDER,
    DEFAULT_FRAMING,
    FEATURE_ORDER,
    FEATURE_SPEC_VERSION,
    FRAMINGS,
    LABELS as LABEL_ORDER,
    ContractError,
    baseline_from_keypoints as compute_baseline,
    features_from_keypoints as compute_features,
    validate_keypoint_ranges,
    validate_keypoints,
)


def _normalise_points(raw) -> list[dict[str, float]]:
    validate_keypoints(raw)
    points = [
        {
            "name": str(point["name"]).strip().lower(),
            "x": float(point["x"]),
            "y": float(point["y"]),
            "z": float(point["z"]),
            "visibility": float(point["visibility"]),
        }
        for point in raw
    ]
    validate_keypoint_ranges(points)
    return points


def _validate_features(raw) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ContractError("features must be an object")
    if set(raw.keys()) != set(FEATURE_ORDER):
        raise ContractError("features must contain exactly the contract fields")
    return {name: float(raw[name]) for name in FEATURE_ORDER}


def _features_close(left, right, tol: float = 1e-9) -> bool:
    return all(abs(float(left[name]) - float(right[name])) <= tol for name in FEATURE_ORDER)


def _record_label(record: dict[str, Any], args: argparse.Namespace) -> str:
    return args.label or record.get("label") or ""


def _record_subject(record: dict[str, Any], args: argparse.Namespace) -> str:
    return str(args.subject or record.get("subject") or "")


def _baselines(
    records: Iterable[tuple[int, str]], args: argparse.Namespace
) -> dict[str, dict[str, float]]:
    """Per-subject median of the labelled neutral segment, in raw 2D units."""

    samples: dict[str, list[dict[str, float]]] = {}
    for _, line in records:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if _record_label(record, args) != "baseline":
            continue
        subject = _record_subject(record, args)
        if not subject:
            continue
        try:
            points = _normalise_points(record.get("keypoints"))
            samples.setdefault(subject, []).append(compute_baseline(points))
        except ContractError:
            continue

    baselines: dict[str, dict[str, float]] = {}
    for subject, values in samples.items():
        baselines[subject] = {
            "shoulder_tilt_deg": round(
                statistics.median(value["shoulder_tilt_deg"] for value in values), 2
            ),
            "neck_ratio": round(
                statistics.median(value["neck_ratio"] for value in values), 4
            ),
            "head_offset_ratio": round(
                statistics.median(value["head_offset_ratio"] for value in values), 4
            ),
        }
    return baselines


def _baseline(record: dict[str, Any], subject: str, baselines: dict[str, dict[str, float]]) -> dict[str, float]:
    supplied = record.get("baseline")
    if isinstance(supplied, dict):
        try:
            return {
                name: float(supplied.get(name, BASELINE_DEFAULTS[name]))
                for name in BASELINE_ORDER
            }
        except (TypeError, ValueError) as exc:
            raise ContractError("baseline 不是数值", code="invalid_baseline") from exc
    return baselines.get(subject, dict(BASELINE_DEFAULTS))

FORBIDDEN_FIELDS = {
    "image",
    "images",
    "frame",
    "frames",
    "pixels",
    "rgb",
    "bgr",
    "base64",
    "image_base64",
    "jpeg",
    "jpg",
    "png",
    "screenshot",
    "video",
    "crop",
}


def _existing_counter(path: Path, subject: str) -> int:
    """Return the next numeric suffix for ``subject`` in an existing file."""

    highest = -1
    if not path.is_file():
        return 0
    prefix = f"{subject}-"
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            frame_id = record.get("frame_id")
            if isinstance(frame_id, str) and frame_id.startswith(prefix):
                suffix = frame_id[len(prefix) :]
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
    return highest + 1


def _reject_media(record: dict[str, Any]) -> str | None:
    for field in FORBIDDEN_FIELDS:
        value = record.get(field)
        if value not in (None, "", [], {}):
            return "media_payload_rejected"
    return None


def _records(stream: TextIO) -> Iterable[tuple[int, Any]]:
    for line_number, line in enumerate(stream, start=1):
        if not line.strip():
            continue
        yield line_number, line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="jsonl file or - for stdin")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--subject", default=None)
    parser.add_argument("--device", default="unknown")
    parser.add_argument("--scene", default="unknown")
    parser.add_argument("--label", choices=LABEL_ORDER, default=None)
    parser.add_argument("--label-source", choices=("human", "prelabel"), default=None)
    parser.add_argument("--origin", choices=("capture", "synthetic"), default=None)
    parser.add_argument("--framing", choices=FRAMINGS, default=None)
    parser.add_argument("--prelabel", action="store_true", help="derive a draft label with the v3 rubric")
    parser.add_argument("--note", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.input == "-":
        lines = list(_records(sys.stdin))
    else:
        with Path(args.input).open("r", encoding="utf-8") as handle:
            lines = list(_records(handle))
    baselines = _baselines(lines, args)

    counters: dict[str, int] = {}
    written = 0
    skipped: dict[str, int] = {}
    feature_mismatch = 0
    seen_ids: set[str] = set()

    if args.append and args.out.is_file():
        with args.out.open("r", encoding="utf-8") as existing:
            for line in existing:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                frame_id = record.get("frame_id") if isinstance(record, dict) else None
                if isinstance(frame_id, str):
                    seen_ids.add(frame_id)

    if args.out.exists() and not args.append and not args.dry_run:
        # Explicit non-append mode truncates; that is the documented default.
        pass

    args.out.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"
    output_handle = None
    if not args.dry_run:
        output_handle = args.out.open(mode, encoding="utf-8", newline="\n")

    try:
        for line_number, line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped["invalid_json"] = skipped.get("invalid_json", 0) + 1
                continue

            if isinstance(record, list):
                record = {"keypoints": record}
            if not isinstance(record, dict):
                skipped["not_an_object"] = skipped.get("not_an_object", 0) + 1
                continue

            media_error = _reject_media(record)
            if media_error:
                skipped[media_error] = skipped.get(media_error, 0) + 1
                continue

            subject = _record_subject(record, args)
            if not subject:
                skipped["missing_subject"] = skipped.get("missing_subject", 0) + 1
                continue

            try:
                points = _normalise_points(record.get("keypoints"))
            except ContractError as exc:
                skipped[exc.code] = skipped.get(exc.code, 0) + 1
                continue
            try:
                neutral = _baseline(record, subject, baselines)
                features = compute_features(points, neutral)
            except ContractError as exc:
                skipped[exc.code] = skipped.get(exc.code, 0) + 1
                continue
            supplied = record.get("features")
            if supplied is not None:
                try:
                    supplied_features = _validate_features(supplied)
                except ContractError:
                    feature_mismatch += 1
                else:
                    if not _features_close(features, supplied_features):
                        feature_mismatch += 1

            label = _record_label(record, args)
            if args.prelabel and not label:
                label = prelabel(features)
            if label not in LABEL_ORDER:
                skipped["missing_label_use_label_or_prelabel"] = (
                    skipped.get("missing_label_use_label_or_prelabel", 0) + 1
                )
                continue

            label_source = args.label_source or record.get("label_source")
            if not label_source and label:
                # A label typed on the CLI is an explicit human annotation; a
                # label merely carried by the input record stays a prelabel
                # until a reviewer promotes it.
                if args.label and args.label_source != "prelabel":
                    label_source = "human"
                else:
                    label_source = "prelabel"

            origin = args.origin or record.get("origin") or "capture"
            if origin not in ("capture", "synthetic"):
                skipped["invalid_origin"] = skipped.get("invalid_origin", 0) + 1
                continue

            framing = record.get("framing") or args.framing or DEFAULT_FRAMING
            if framing not in FRAMINGS:
                skipped["invalid_framing"] = skipped.get("invalid_framing", 0) + 1
                continue

            frame_id = record.get("frame_id")
            if frame_id is None:
                if subject not in counters:
                    counters[subject] = _existing_counter(args.out, subject) if args.append else 0
                frame_id = f"{subject}-{counters[subject]:06d}"
                counters[subject] += 1
            if not isinstance(frame_id, str) or not frame_id:
                skipped["invalid_frame_id"] = skipped.get("invalid_frame_id", 0) + 1
                continue
            if frame_id in seen_ids:
                skipped["duplicate_frame_id"] = skipped.get("duplicate_frame_id", 0) + 1
                continue
            seen_ids.add(frame_id)

            timestamp = record.get("ts")
            if not isinstance(timestamp, str) or not timestamp:
                timestamp = datetime.now().astimezone().isoformat(timespec="seconds")

            note = str(record.get("note") or args.note or "")
            if args.prelabel and not record.get("note"):
                note = (note + ";prelabel:auto_review_required").strip(";")

            frame = {
                "frame_id": frame_id,
                "ts": timestamp,
                "device": str(record.get("device") or args.device),
                "subject": subject,
                "scene": str(record.get("scene") or args.scene),
                "framing": framing,
                "feature_spec_version": FEATURE_SPEC_VERSION,
                "baseline": neutral,
                "keypoints": points,
                "features": {
                    name: round(float(value), 6) for name, value in features.items()
                },
                "label": label,
                "label_source": label_source or "",
                "origin": origin,
                "note": note,
            }

            if output_handle is not None:
                output_handle.write(
                    json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
            written += 1
    finally:
        if output_handle is not None:
            output_handle.close()

    summary = {
        "written": written,
        "skipped": skipped,
        "feature_mismatch_count": feature_mismatch,
        "out": str(args.out),
        "append": bool(args.append),
        "dry_run": bool(args.dry_run),
        "note": "no image, video, screenshot or pixel data is accepted or written",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if written or skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
