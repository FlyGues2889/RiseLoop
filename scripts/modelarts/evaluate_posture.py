"""Independently reproduce ``metrics.json`` from the saved checkpoints.

The evaluator reloads ``model.pt`` / ``model_A.pt`` / ``model_B.pt``, rebuilds
the test split from ``split.json``, recomputes features from keypoints with the
contract module, and compares every headline number with ``metrics.json``.
It writes nothing and touches no training code paths beyond the shared contract.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0] or os.getcwd()) == _SCRIPT_DIR:
    sys.path[0] = _SCRIPT_DIR
else:
    sys.path.insert(0, _SCRIPT_DIR)

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from posture_contract import (
    FEATURE_SPEC_VERSION,
    LABELS as LABEL_ORDER,
    ContractError,
    features_from_keypoints as compute_features,
    model_features_from_keypoints as compute_model_features,
    model_features_vector,
    validate_keypoints,
)
from metrics_util import compute_metrics
from model import coordinates_vector, load_checkpoint
from posture_runtime import decide_posture

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_ARTIFACTS = SCRIPT_DIR / "artifacts" / "v1"
LABEL_TO_INDEX = {label: index for index, label in enumerate(LABEL_ORDER)}


def _normalise_points(raw) -> list[dict[str, float]]:
    validate_keypoints(raw)
    return [
        {
            "name": str(point["name"]).strip().lower(),
            "x": float(point["x"]),
            "y": float(point["y"]),
            "z": float(point["z"]),
            "visibility": float(point["visibility"]),
        }
        for point in raw
    ]


def build_input_vector(input_version: str, keypoints, model_features) -> list[float]:
    if input_version == "A":
        return model_features_vector(model_features)
    if input_version == "B":
        return coordinates_vector(keypoints) + model_features_vector(model_features)
    raise ContractError("input_version must be A or B")


class EvalDataset(Dataset):
    def __init__(self, rows: Sequence[dict[str, Any]], meta: dict[str, Any]) -> None:
        mean = np.asarray(meta["mean"], dtype=np.float64)
        std = np.asarray(meta["std"], dtype=np.float64)
        vectors = []
        labels = []
        for row in rows:
            raw = np.asarray(
                build_input_vector(row["version"], row["points"], row["model_features"]),
                dtype=np.float64,
            )
            vectors.append((raw - mean) / std)
            labels.append(LABEL_TO_INDEX[row["label"]])
        self.x = torch.tensor(np.asarray(vectors), dtype=torch.float32)
        self.y = torch.tensor(labels, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.x[index], self.y[index]


def _resolve_data(artifacts: Path, metrics: dict[str, Any], override: str | None) -> Path:
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate.resolve()
        candidate = REPO_ROOT / override
        if candidate.is_file():
            return candidate.resolve()
        raise FileNotFoundError(f"data file not found: {override}")
    stored = metrics.get("data", {}).get("path")
    if not stored:
        raise FileNotFoundError("metrics.json has no data.path; pass --data")
    candidate = Path(stored)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if not candidate.is_file():
        candidate = Path.cwd() / stored
    if not candidate.is_file():
        raise FileNotFoundError(
            f"data file recorded in metrics.json is unavailable: {stored}; pass --data"
        )
    return candidate.resolve()


def _load_rows(path: Path, frame_ids: set[str], warnings: list[str]) -> list[dict[str, Any]]:
    rows = []
    skipped = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            frame_id = record.get("frame_id")
            if frame_id not in frame_ids:
                continue
            label = record.get("label")
            if label not in LABEL_TO_INDEX:
                skipped += 1
                continue
            try:
                points = _normalise_points(record.get("keypoints"))
            except ContractError:
                skipped += 1
                continue
            raw_baseline = record.get("baseline")
            try:
                features = compute_features(points, raw_baseline)
                model_features = compute_model_features(points, raw_baseline)
            except ContractError:
                skipped += 1
                continue
            rows.append(
                {
                    "frame_id": frame_id,
                    "label": label,
                    "points": points,
                    "features": features,
                    "model_features": model_features,
                }
            )
    if skipped:
        warnings.append(f"eval_frames_skipped={skipped}")
    rows.sort(key=lambda item: item["frame_id"])
    return rows


def _predict(model, meta: dict[str, Any], rows: Sequence[dict[str, Any]]) -> tuple[list[str], list[int]]:
    dataset = EvalDataset(rows, meta)
    loader = DataLoader(dataset, batch_size=256, shuffle=False, num_workers=0)
    predictions: list[str] = []
    true_indices: list[int] = []
    with torch.inference_mode():
        for inputs, targets in loader:
            logits = model(inputs)
            probabilities = torch.softmax(logits, dim=-1).cpu().tolist()
            predictions.extend(decide_posture(row)[0] for row in probabilities)
            true_indices.extend(int(value) for value in targets.tolist())
    return predictions, true_indices


def _close(left: float, right: float, tolerance: float = 1e-6) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def _compare(saved: dict[str, Any], recomputed: dict[str, Any], tolerance: float) -> list[str]:
    problems: list[str] = []
    for field in ("macro_f1", "accuracy", "weighted_f1"):
        if not _close(saved[field], recomputed[field], tolerance):
            problems.append(f"{field}: saved={saved[field]} recomputed={recomputed[field]}")
    for label in LABEL_ORDER:
        for field in ("precision", "recall", "f1"):
            if not _close(saved["per_class"][label][field], recomputed["per_class"][label][field], tolerance):
                problems.append(
                    f"{label}.{field}: saved={saved['per_class'][label][field]} "
                    f"recomputed={recomputed['per_class'][label][field]}"
                )
    if saved["confusion_matrix"]["matrix"] != recomputed["confusion_matrix"]["matrix"]:
        problems.append("confusion_matrix differs")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--data", default=None, help="override frames .jsonl")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    artifacts = args.artifacts.resolve()
    metrics_path = artifacts / "metrics.json"
    split_path = artifacts / "split.json"
    if not metrics_path.is_file() or not split_path.is_file():
        print(f"missing metrics.json/split.json under {artifacts}", file=sys.stderr)
        return 2
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    if metrics.get("feature_spec_version") != FEATURE_SPEC_VERSION:
        print(
            f"metrics feature_spec_version mismatch: {metrics.get('feature_spec_version')!r}",
            file=sys.stderr,
        )
        return 2
    spec_path = artifacts / "feature_spec.json"
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if spec.get("feature_spec_version") != FEATURE_SPEC_VERSION:
            print("feature_spec.json version mismatch", file=sys.stderr)
            return 2
    if split.get("scheme") == "loso":
        print(
            "this artefact used leave-one-subject-out; rerun train_posture.py to "
            "reproduce the out-of-fold metrics",
            file=sys.stderr,
        )
        return 2

    warnings: list[str] = []
    data_path = _resolve_data(artifacts, metrics, args.data)
    rows = _load_rows(data_path, set(split["test_frame_ids"]), warnings)
    if len(rows) != len(split["test_frame_ids"]):
        print(
            f"test frames mismatch: expected {len(split['test_frame_ids'])}, found {len(rows)}",
            file=sys.stderr,
        )
        return 2

    torch.set_num_threads(1)
    report: dict[str, Any] = {
        "artifacts": str(artifacts),
        "data": str(data_path),
        "test_frames": len(rows),
        "input_versions": {},
        "warnings": warnings,
    }
    all_ok = True
    for version in ("A", "B"):
        checkpoint = artifacts / f"model_{version}.pt"
        if not checkpoint.is_file():
            report["input_versions"][version] = {"error": "checkpoint_missing"}
            all_ok = False
            continue
        model, meta = load_checkpoint(str(checkpoint))
        if meta["input_version"] != version:
            report["input_versions"][version] = {"error": "input_version_mismatch"}
            all_ok = False
            continue
        prepared = [
            {"frame_id": row["frame_id"], "label": row["label"], "points": row["points"],
             "features": row["features"], "model_features": row["model_features"],
             "version": version}
            for row in rows
        ]
        predictions, _ = _predict(model, meta, prepared)
        recomputed = compute_metrics([row["label"] for row in rows], predictions)
        saved = metrics["models"][version]["test"]
        problems = _compare(saved, recomputed, tolerance=1e-6)
        all_ok = all_ok and not problems
        history = metrics["models"][version].get("history") or []
        report["input_versions"][version] = {
            "input_dim": meta["input_dim"],
            "params": metrics["models"][version].get("params"),
            "saved_macro_f1": saved["macro_f1"],
            "recomputed_macro_f1": recomputed["macro_f1"],
            "saved_accuracy": saved["accuracy"],
            "recomputed_accuracy": recomputed["accuracy"],
            "epochs_run": metrics["models"][version].get("epochs_run"),
            "best_epoch": metrics["models"][version].get("best_epoch"),
            "best_val_macro_f1": metrics["models"][version].get("best_val_macro_f1"),
            "last_history_entry": history[-1] if history else None,
            "match": not problems,
            "problems": problems,
        }

    chosen = metrics["chosen_input_version"]
    model, meta = load_checkpoint(str(artifacts / "model.pt"))
    prepared = [
        {"frame_id": row["frame_id"], "label": row["label"], "points": row["points"],
         "features": row["features"], "model_features": row["model_features"],
         "version": chosen}
        for row in rows
    ]
    predictions, _ = _predict(model, meta, prepared)
    recomputed = compute_metrics([row["label"] for row in rows], predictions)
    saved = metrics["chosen"]["test"]
    problems = _compare(saved, recomputed, tolerance=1e-6)
    all_ok = all_ok and not problems
    report["chosen"] = {
        "input_version": chosen,
        "saved_macro_f1": saved["macro_f1"],
        "recomputed_macro_f1": recomputed["macro_f1"],
        "saved_accuracy": saved["accuracy"],
        "recomputed_accuracy": recomputed["accuracy"],
        "match": not problems,
        "problems": problems,
        "confusion_matrix": recomputed["confusion_matrix"],
    }

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not all_ok:
        print("evaluation did not match metrics.json", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
