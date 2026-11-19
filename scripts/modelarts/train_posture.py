"""Train and evaluate the v0 posture MLP end to end.

One command reproduces every artefact under ``artifacts/v0``:

    python scripts/modelarts/train_posture.py --data <frames.jsonl>

Input versions
--------------
A: 6 derived features.
B: 132 normalised coordinates (33 x [x, y, z, visibility]) + 6 features = 138.

Both are standardised with train-split statistics only.  The version with the
better *validation* macro-F1 is shipped as ``model.pt``; the test split is
touched once for the final report.  Selecting on test would be leakage.
"""

from __future__ import annotations

import os
import sys

# `python scripts/modelarts/train_posture.py` puts a relative directory in
# sys.path[0].  Some torch 2.x builds then import a module twice while
# resolving `torch._dynamo`, so normalise it to an absolute path before any
# third-party import.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0] or os.getcwd()) == _SCRIPT_DIR:
    sys.path[0] = _SCRIPT_DIR
else:
    sys.path.insert(0, _SCRIPT_DIR)
# torch 2.15 resolves `__main__.__file__` when it lazily imports torch._dynamo.
# A relative __file__ (from `python scripts/...`) makes it resolve modules
# twice, so make the entry-point metadata absolute as well.
__file__ = os.path.abspath(__file__)
if sys.argv and sys.argv[0]:
    sys.argv[0] = os.path.abspath(sys.argv[0])

import argparse
import copy
import hashlib
import json
import random
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


def _ensure_writable_tempdir(preferred: Path | None = None) -> None:
    """Torch's lazy inductor import needs a writable temp directory.

    Some Windows sandboxes leave TEMP pointing at a non-writable location.
    Fall back to the run's output directory first, then to
    ``scripts/modelarts/.tmp`` (git-ignored).
    """

    try:
        handle, probe = tempfile.mkstemp(prefix="posture-", suffix=".tmp")
        os.close(handle)
        os.unlink(probe)
        return
    except OSError:
        pass
    candidates = []
    if preferred is not None:
        candidates.append(preferred)
    candidates.extend(
        (Path(__file__).resolve().parent, Path.cwd())
    )
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        try:
            handle, probe = tempfile.mkstemp(
                prefix=".posture-", suffix=".tmp", dir=str(candidate)
            )
            os.close(handle)
            os.unlink(probe)
        except OSError:
            continue
        os.environ["TEMP"] = str(candidate)
        os.environ["TMP"] = str(candidate)
        tempfile.tempdir = str(candidate)
        return
    raise RuntimeError("no writable temporary directory available")


import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from label_policy import describe as describe_label_policy
from posture_contract import (
    FEATURE_ORDER as FEATURE_NAMES,
    FEATURE_SPEC_VERSION,
    KEYPOINT_ORDER as MEDIAPIPE_33,
    LABELS as LABEL_ORDER,
    MIN_VISIBILITY as VISIBILITY_THRESHOLD,
    ContractError,
    features_from_keypoints as compute_features,
    features_vector,
    validate_keypoints,
)
from metrics_util import compute_metrics
from model import (
    COORD_SCALE_FLOOR,
    MIN_MODEL_CONFIDENCE,
    PostureMLP,
    coordinates_vector,
    save_checkpoint,
    softmax_probabilities,
)

CONTRACT_VERSION = FEATURE_SPEC_VERSION
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


def _validate_features(raw) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ContractError("features must be an object")
    if set(raw.keys()) != set(FEATURE_NAMES):
        raise ContractError("features must contain exactly the six contract fields")
    return {name: float(raw[name]) for name in FEATURE_NAMES}


def _features_close(left, right, tol: float = 1e-9) -> bool:
    return all(abs(float(left[name]) - float(right[name])) <= tol for name in FEATURE_NAMES)


def _label_counts(labels) -> dict[str, int]:
    counts = {label: 0 for label in LABEL_ORDER}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return counts


def build_input_vector(input_version: str, keypoints, features) -> list[float]:
    if input_version == "A":
        return features_vector(features)
    if input_version == "B":
        return coordinates_vector(keypoints) + features_vector(features)
    raise ContractError("input_version must be A or B")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_OUT = SCRIPT_DIR / "artifacts" / "v0"


@dataclass
class Frame:
    frame_id: str
    subject: str
    device: str
    scene: str
    origin: str
    label_source: str
    label: str
    points: list[dict[str, float]]
    features: dict[str, float]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_data_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_file():
        return candidate.resolve()
    candidate = REPO_ROOT / path
    if candidate.is_file():
        return candidate.resolve()
    raise FileNotFoundError(f"data file not found: {path}")


def load_frames(path: Path, warnings: list[str]) -> list[Frame]:
    frames: list[Frame] = []
    seen: set[str] = set()
    skipped = Counter()
    feature_mismatch = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped["invalid_json"] += 1
                continue
            if not isinstance(record, dict):
                skipped["not_an_object"] += 1
                continue

            frame_id = record.get("frame_id")
            subject = record.get("subject")
            label = record.get("label")
            if not isinstance(frame_id, str) or not frame_id:
                skipped["missing_frame_id"] += 1
                continue
            if not isinstance(subject, str) or not subject:
                skipped["missing_subject"] += 1
                continue
            if label not in LABEL_TO_INDEX:
                skipped["missing_or_unknown_label"] += 1
                continue
            if frame_id in seen:
                raise ValueError(f"duplicate frame_id at line {line_number}: {frame_id}")
            seen.add(frame_id)

            try:
                points = _normalise_points(record.get("keypoints"))
            except ContractError:
                skipped["invalid_keypoints"] += 1
                continue
            features = compute_features(points)
            supplied = record.get("features")
            if supplied is not None:
                try:
                    supplied_features = _validate_features(supplied)
                except ContractError:
                    feature_mismatch += 1
                else:
                    if not _features_close(features, supplied_features):
                        feature_mismatch += 1

            frames.append(
                Frame(
                    frame_id=frame_id,
                    subject=subject,
                    device=str(record.get("device") or "unknown"),
                    scene=str(record.get("scene") or "unknown"),
                    origin=str(record.get("origin") or "capture"),
                    label_source=str(record.get("label_source") or "human"),
                    label=label,
                    points=points,
                    features=features,
                )
            )

    if feature_mismatch:
        warnings.append(
            f"features_recomputed_mismatch={feature_mismatch} (recomputed from keypoints; values not logged)"
        )
    if skipped:
        warnings.append("frames_skipped=" + json.dumps(dict(sorted(skipped.items())), sort_keys=True))
    if not frames:
        raise ValueError("no usable frames in data file")
    return frames


def select_origin(
    frames: Sequence[Frame],
    requested: str,
    warnings: list[str],
    *,
    allow_unreviewed: bool = False,
) -> tuple[str, list[Frame]]:
    counts = Counter(frame.origin for frame in frames)
    if requested == "auto":
        if counts.get("capture", 0):
            chosen = "capture"
        elif counts.get("synthetic", 0):
            chosen = "synthetic"
            warnings.append("origin=auto resolved to synthetic because no capture frames exist")
        else:
            raise ValueError("no capture or synthetic frames")
    elif requested in ("capture", "synthetic"):
        chosen = requested
    else:
        raise ValueError("--origin must be auto, capture or synthetic")

    selected = [frame for frame in frames if frame.origin == chosen]
    if not selected:
        raise ValueError(f"no frames with origin={chosen}")
    if chosen == "capture":
        if allow_unreviewed:
            warnings.append(
                "allow_unreviewed_capture=True: prelabelled capture frames used as truth"
            )
        else:
            reviewed = [frame for frame in selected if frame.label_source == "human"]
            if len(reviewed) != len(selected):
                warnings.append(
                    f"capture_prelabel_frames_excluded={len(selected) - len(reviewed)} "
                    "(label_source must be human)"
                )
            selected = reviewed
            if not selected:
                raise ValueError("capture frames exist but none have label_source=human")
    else:
        warnings.append(
            "synthetic_scope: labels are rubric-generated prelabels; metrics are NOT real-capture accuracy"
        )
    return chosen, selected


def split_subjects(subjects: Sequence[str], seed: int) -> dict[str, list[str]]:
    ordered = sorted(subjects)
    if len(ordered) >= 5:
        rng = random.Random(seed)
        rng.shuffle(ordered)
        total = len(ordered)
        n_test = max(1, round(total * 0.15))
        n_val = max(1, round(total * 0.15))
        n_train = total - n_test - n_val
        if n_train < 1:
            n_test, n_val, n_train = 1, 1, total - 2
        return {
            "scheme": "subject_group_70_15_15",
            "train": sorted(ordered[:n_train]),
            "val": sorted(ordered[n_train : n_train + n_val]),
            "test": sorted(ordered[n_train + n_val :]),
        }
    # Leave-one-subject-out is handled by run_loso; this is only a placeholder.
    return {
        "scheme": "loso",
        "train": sorted(ordered),
        "val": [],
        "test": sorted(ordered),
    }


def fit_stats(frames: Sequence[Frame], input_version: str) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(
        [build_input_vector(input_version, frame.points, frame.features) for frame in frames],
        dtype=np.float64,
    )
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std[std < 1e-8] = 1.0
    return mean, std


class FrameDataset(Dataset):
    def __init__(
        self,
        frames: Sequence[Frame],
        input_version: str,
        mean: np.ndarray,
        std: np.ndarray,
    ) -> None:
        raw = np.asarray(
            [build_input_vector(input_version, frame.points, frame.features) for frame in frames],
            dtype=np.float64,
        )
        self.x = torch.tensor((raw - mean) / std, dtype=torch.float32)
        self.y = torch.tensor(
            [LABEL_TO_INDEX[frame.label] for frame in frames], dtype=torch.long
        )
        self.frames = list(frames)

    def __len__(self) -> int:
        return len(self.frames)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.x[index], self.y[index]


def _class_weights(dataset: FrameDataset, num_classes: int = len(LABEL_ORDER)) -> torch.Tensor:
    counts = torch.bincount(dataset.y, minlength=num_classes).float()
    total = float(len(dataset))
    weights = torch.zeros(num_classes, dtype=torch.float32)
    for index in range(num_classes):
        if counts[index] > 0:
            weights[index] = total / (num_classes * float(counts[index]))
    return weights


def _predict_loader(model: nn.Module, loader: DataLoader) -> tuple[list[int], np.ndarray]:
    model.eval()
    labels: list[int] = []
    probabilities: list[np.ndarray] = []
    with torch.inference_mode():
        for inputs, targets in loader:
            logits = model(inputs)
            probabilities.append(torch.softmax(logits, dim=-1).cpu().numpy())
            labels.extend(int(value) for value in targets.tolist())
    return labels, np.concatenate(probabilities, axis=0)


def _predict_frames(
    model: nn.Module,
    frames: Sequence[Frame],
    input_version: str,
    mean: np.ndarray,
    std: np.ndarray,
    batch_size: int = 256,
) -> tuple[list[str], np.ndarray]:
    dataset = FrameDataset(frames, input_version, mean, std)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    true_indices, probabilities = _predict_loader(model, loader)
    predicted = [LABEL_ORDER[int(np.argmax(row))] for row in probabilities]
    return predicted, probabilities


def train_one(
    train_frames: Sequence[Frame],
    val_frames: Sequence[Frame],
    input_version: str,
    mean: np.ndarray,
    std: np.ndarray,
    args: argparse.Namespace,
    seed: int,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    train_dataset = FrameDataset(train_frames, input_version, mean, std)
    val_dataset = FrameDataset(val_frames, input_version, mean, std)
    model = PostureMLP(
        input_dim=len(mean),
        hidden=tuple(args.hidden),
        dropout=args.dropout,
    )
    criterion = nn.CrossEntropyLoss(weight=_class_weights(train_dataset))
    optimizer = torch.optim.Adam(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )

    best_state = copy.deepcopy(model.state_dict())
    best_f1 = -1.0
    best_epoch = 0
    best_val_metrics: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []
    patience = 0
    started = time.perf_counter()

    for epoch in range(1, args.epochs + 1):
        model.train()
        generator = torch.Generator()
        generator.manual_seed(seed + epoch)
        loader = DataLoader(
            train_dataset,
            batch_size=args.batch_size,
            shuffle=True,
            generator=generator,
            num_workers=0,
        )
        total_loss = 0.0
        for inputs, targets in loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(targets)
        train_loss = total_loss / max(1, len(train_dataset))

        val_loader = DataLoader(
            val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0
        )
        true_indices, probabilities = _predict_loader(model, val_loader)
        y_true = [LABEL_ORDER[index] for index in true_indices]
        y_pred = [LABEL_ORDER[int(np.argmax(row))] for row in probabilities]
        val_metrics = compute_metrics(y_true, y_pred)

        # Validation loss for the curve only; selection uses macro-F1.
        model.eval()
        with torch.inference_mode():
            val_logits = model(val_dataset.x)
            val_loss = float(criterion(val_logits, val_dataset.y).item())

        history.append(
            {
                "epoch": epoch,
                "train_loss": round(train_loss, 6),
                "val_loss": round(val_loss, 6),
                "val_macro_f1": round(val_metrics["macro_f1"], 6),
            }
        )

        if val_metrics["macro_f1"] > best_f1 + 1e-9:
            best_f1 = val_metrics["macro_f1"]
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            best_val_metrics = val_metrics
            patience = 0
        else:
            patience += 1
            if patience >= args.patience:
                break

    model.load_state_dict(best_state)
    model.eval()
    elapsed = time.perf_counter() - started

    return {
        "model": model,
        "input_version": input_version,
        "input_dim": len(mean),
        "mean": mean,
        "std": std,
        "params": model.parameter_count(),
        "epochs_run": len(history),
        "best_epoch": best_epoch,
        "best_val_macro_f1": float(best_f1),
        "best_val_metrics": best_val_metrics,
        "history": history,
        "train_seconds": round(elapsed, 3),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(_jsonable(payload), handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def _git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _plot_confusion(metrics: dict[str, Any], path: Path, title: str) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(path.parent / ".mplconfig"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = metrics["confusion_matrix"]["labels"]
    matrix = np.asarray(metrics["confusion_matrix"]["matrix"], dtype=int)
    figure, axis = plt.subplots(figsize=(6.2, 5.4))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_title(title, fontsize=11)
    axis.set_xlabel("predicted")
    axis.set_ylabel("ground truth")
    axis.set_xticks(range(len(labels)))
    axis.set_yticks(range(len(labels)))
    axis.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    axis.set_yticklabels(labels, fontsize=9)
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = int(matrix[row, column])
            color = "white" if value > matrix.max() / 2 else "black"
            axis.text(column, row, str(value), ha="center", va="center", color=color, fontsize=10)
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _rounded_sample(frame: Frame) -> dict[str, Any]:
    return {
        "subject": frame.subject,
        "device": frame.device,
        "scene": frame.scene,
        "keypoints": [
            {
                "name": point["name"],
                "x": round(point["x"], 4),
                "y": round(point["y"], 4),
                "z": round(point["z"], 4),
                "visibility": round(point["visibility"], 4),
            }
            for point in frame.points
        ],
        "features": {
            name: round(float(frame.features[name]), 6) for name in FEATURE_NAMES
        },
    }


def _predict_payload(
    model: nn.Module,
    meta: dict[str, Any],
    sample: dict[str, Any],
) -> tuple[str, float, dict[str, float]]:
    points = _normalise_points(sample["keypoints"])
    features = _validate_features(sample["features"])
    raw = np.asarray(
        build_input_vector(meta["input_version"], points, features), dtype=np.float64
    )
    mean = np.asarray(meta["mean"], dtype=np.float64)
    std = np.asarray(meta["std"], dtype=np.float64)
    tensor = torch.tensor((raw - mean) / std, dtype=torch.float32).unsqueeze(0)
    with torch.inference_mode():
        logits = model(tensor)
        probabilities = softmax_probabilities(logits)
    probabilities_dict = {
        label: round(float(probabilities[index]), 6)
        for index, label in enumerate(LABEL_ORDER)
    }
    best_index = int(np.argmax(probabilities))
    confidence = float(probabilities[best_index])
    posture = LABEL_ORDER[best_index]
    if confidence < MIN_MODEL_CONFIDENCE:
        posture = "undetermined"
    return posture, round(confidence, 6), probabilities_dict


def _feature_spec(mean_a: np.ndarray, std_a: np.ndarray, mean_b: np.ndarray, std_b: np.ndarray,
                  args: argparse.Namespace) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "mediapipe_landmarks": list(MEDIAPIPE_33),
        "feature_order": list(FEATURE_NAMES),
        "label_order": list(LABEL_ORDER),
        "label_index": {label: index for index, label in enumerate(LABEL_ORDER)},
        "label_policy": describe_label_policy(),
        "input_versions": {
            "A": {
                "dimension": len(FEATURE_NAMES),
                "layout": "6 derived features in feature_order",
                "standardization": {
                    "method": "z-score with train-split mean/std",
                    "mean": mean_a.tolist(),
                    "std": std_a.tolist(),
                },
            },
            "B": {
                "dimension": len(mean_b),
                "layout": "132 coordinates (33 landmarks x [x, y, z, visibility]) + 6 features",
                "coordinate_normalization": {
                    "origin": "shoulder midpoint (left_shoulder, right_shoulder), including z",
                    "scale": f"max(2D shoulder width, {COORD_SCALE_FLOOR})",
                    "formula": "[(x - ox) / s, (y - oy) / s, (z - oz) / s, visibility]",
                    "rationale": "removes camera distance and image position; visibility stays 0..1",
                },
                "standardization": {
                    "method": "z-score with train-split mean/std over all 138 dimensions",
                    "mean": mean_b.tolist(),
                    "std": std_b.tolist(),
                },
            },
        },
        "preprocess_constants": {
            "coord_scale_floor": COORD_SCALE_FLOOR,
            "visibility_threshold": VISIBILITY_THRESHOLD,
        },
        "model": {
            "hidden": list(args.hidden),
            "dropout": args.dropout,
            "activation": "ReLU",
            "output": list(LABEL_ORDER),
        },
    }


def _data_summary(
    path: Path,
    frames: Sequence[Frame],
    train_frames: Sequence[Frame],
    val_frames: Sequence[Frame],
    test_frames: Sequence[Frame],
    scope: str,
    all_frames: Sequence[Frame],
) -> dict[str, Any]:
    def distribution(rows: Iterable[Frame]) -> dict[str, int]:
        return _label_counts([frame.label for frame in rows])

    origin_counts = Counter(frame.origin for frame in all_frames)
    source_counts = Counter(frame.label_source for frame in all_frames)
    try:
        relative = str(path.relative_to(REPO_ROOT))
    except ValueError:
        relative = str(path)
    return {
        "path": relative,
        "sha256": _sha256(path),
        "origin": scope,
        "origin_counts": {key: int(value) for key, value in sorted(origin_counts.items())},
        "real_capture_frames": int(origin_counts.get("capture", 0)),
        "synthetic_frames": int(origin_counts.get("synthetic", 0)),
        "label_source_counts": {key: int(value) for key, value in sorted(source_counts.items())},
        "frames_total": len(all_frames),
        "frames_used": len(frames),
        "label_distribution": distribution(frames),
        "subjects": sorted({frame.subject for frame in frames}),
        "subject_count": len({frame.subject for frame in frames}),
        "devices": sorted({frame.device for frame in frames}),
        "device_count": len({frame.device for frame in frames}),
        "scenes": sorted({frame.scene for frame in frames}),
        "scene_count": len({frame.scene for frame in frames}),
        "frames_per_split": {
            "train": len(train_frames),
            "val": len(val_frames),
            "test": len(test_frames),
        },
        "label_distribution_by_split": {
            "train": distribution(train_frames),
            "val": distribution(val_frames),
            "test": distribution(test_frames),
        },
        "metrics_scope": (
            "synthetic_only" if scope == "synthetic" else "real_capture"
        ),
        "metrics_warning": (
            "METRICS ARE FROM SYNTHETIC DATA AND ARE NOT GENERALISATION ACCURACY"
            if scope == "synthetic"
            else None
        ),
    }


def _run_group_split(
    frames: Sequence[Frame],
    split: dict[str, list[str]],
    args: argparse.Namespace,
    warnings: list[str],
) -> dict[str, Any]:
    train_frames = [frame for frame in frames if frame.subject in set(split["train"])]
    val_frames = [frame for frame in frames if frame.subject in set(split["val"])]
    test_frames = [frame for frame in frames if frame.subject in set(split["test"])]
    if not train_frames or not val_frames or not test_frames:
        raise ValueError("subject split produced an empty train/val/test split")

    results: dict[str, Any] = {}
    for version in ("A", "B"):
        mean, std = fit_stats(train_frames, version)
        result = train_one(
            train_frames, val_frames, version, mean, std, args, seed=args.seed
        )
        predicted, probabilities = _predict_frames(
            result["model"], test_frames, version, mean, std
        )
        test_metrics = compute_metrics(
            [frame.label for frame in test_frames], predicted
        )
        results[version] = {
            "version": version,
            "input_dim": result["input_dim"],
            "params": result["params"],
            "epochs_run": result["epochs_run"],
            "best_epoch": result["best_epoch"],
            "best_val_macro_f1": result["best_val_macro_f1"],
            "train_seconds": result["train_seconds"],
            "history": result["history"],
            "val": result["best_val_metrics"],
            "test": test_metrics,
            "mean": mean,
            "std": std,
            "model": result["model"],
            "test_predictions": predicted,
            "test_probabilities": probabilities,
        }

    chosen = max(("A", "B"), key=lambda version: results[version]["best_val_macro_f1"])
    if abs(results["A"]["best_val_macro_f1"] - results["B"]["best_val_macro_f1"]) < 1e-9:
        chosen = "A"  # deterministic tie-break: fewer inputs
    if results[chosen]["test"]["macro_f1"] < results[chosen]["val"]["macro_f1"] - 0.05:
        warnings.append("test_macro_f1_more_than_5_points_below_validation")

    return {
        "results": results,
        "chosen": chosen,
        "train_frames": train_frames,
        "val_frames": val_frames,
        "test_frames": test_frames,
        "test_predictions": results[chosen]["test_predictions"],
    }


def _run_loso(
    frames: Sequence[Frame],
    args: argparse.Namespace,
    warnings: list[str],
) -> dict[str, Any]:
    """Leave-one-subject-out evaluation for fewer than five subjects.

    Out-of-fold predictions produce the reported metrics.  The shipped model is
    retrained on all subjects afterwards; its metrics are the OOF ones above.
    """

    subjects = sorted({frame.subject for frame in frames})
    if len(subjects) < 2:
        raise ValueError("LOSO needs at least two subjects")
    warnings.append(
        f"loso_used: {len(subjects)} subjects (<5); metrics are out-of-fold leave-one-subject-out"
    )
    folds = []
    for index, subject in enumerate(subjects):
        others = [item for item in subjects if item != subject]
        val_subject = others[index % len(others)]
        folds.append(
            {
                "test": subject,
                "val": val_subject,
                "train": [item for item in others if item != val_subject],
            }
        )

    versions: dict[str, Any] = {}
    for version in ("A", "B"):
        oof_true: list[str] = []
        oof_pred: list[str] = []
        oof_frames: list[Frame] = []
        val_scores: list[float] = []
        best_epochs: list[int] = []
        fold_seconds = 0.0
        last_model = None
        last_mean = None
        last_std = None
        last_params = 0
        for fold in folds:
            train_frames = [frame for frame in frames if frame.subject in fold["train"]]
            val_frames = [frame for frame in frames if frame.subject == fold["val"]]
            test_frames = [frame for frame in frames if frame.subject == fold["test"]]
            mean, std = fit_stats(train_frames, version)
            result = train_one(
                train_frames, val_frames, version, mean, std, args, seed=args.seed
            )
            predicted, _ = _predict_frames(
                result["model"], test_frames, version, mean, std
            )
            oof_true.extend(frame.label for frame in test_frames)
            oof_pred.extend(predicted)
            oof_frames.extend(test_frames)
            val_scores.append(result["best_val_macro_f1"])
            best_epochs.append(result["best_epoch"])
            fold_seconds += result["train_seconds"]
            last_model, last_mean, last_std = result["model"], mean, std
            last_params = result["params"]
        metrics = compute_metrics(oof_true, oof_pred)
        versions[version] = {
            "version": version,
            "input_dim": len(last_mean) if last_mean is not None else 0,
            "params": last_params,
            "fold_val_macro_f1": [round(value, 6) for value in val_scores],
            "mean_val_macro_f1": float(statistics.mean(val_scores)),
            "best_val_macro_f1": float(statistics.mean(val_scores)),
            "test": metrics,
            "oof_frames": len(oof_frames),
            "train_seconds": round(fold_seconds, 3),
            "best_epochs": best_epochs,
            "mean": last_mean,
            "std": last_std,
            "model": last_model,
            "history": None,
        }

    chosen = max(("A", "B"), key=lambda version: versions[version]["mean_val_macro_f1"])
    if abs(versions["A"]["mean_val_macro_f1"] - versions["B"]["mean_val_macro_f1"]) < 1e-9:
        chosen = "A"

    # Deployment model: all subjects, fixed epochs (median of fold best epochs).
    fixed_epochs = max(1, int(statistics.median(versions[chosen]["best_epochs"])))
    mean, std = fit_stats(frames, chosen)
    dataset = FrameDataset(frames, chosen, mean, std)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    model = PostureMLP(input_dim=len(mean), hidden=tuple(args.hidden), dropout=args.dropout)
    criterion = nn.CrossEntropyLoss(weight=_class_weights(dataset))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    started = time.perf_counter()
    for epoch in range(fixed_epochs):
        model.train()
        generator = torch.Generator()
        generator.manual_seed(args.seed + epoch)
        loader = DataLoader(
            dataset, batch_size=args.batch_size, shuffle=True, generator=generator, num_workers=0
        )
        for inputs, targets in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), targets)
            loss.backward()
            optimizer.step()
    deploy_seconds = time.perf_counter() - started
    model.eval()

    return {
        "results": versions,
        "chosen": chosen,
        "train_frames": list(frames),
        "val_frames": [],
        "test_frames": list(frames),
        "test_predictions": [],
        "deploy_model": model,
        "deploy_mean": mean,
        "deploy_std": std,
        "fixed_epochs": fixed_epochs,
        "deploy_seconds": round(deploy_seconds, 3),
        "folds": folds,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="frames .jsonl")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--origin", choices=("auto", "capture", "synthetic"), default="auto")
    parser.add_argument("--epochs", type=int, default=160)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--hidden", type=int, nargs="+", default=[64, 32])
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--allow-unreviewed-capture", action="store_true")
    args = parser.parse_args(argv)

    torch.set_num_threads(1)
    try:
        torch.use_deterministic_algorithms(True)
    except Exception:  # older torch builds
        pass

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    warnings: list[str] = []

    data_path = _resolve_data_path(args.data)
    all_frames = load_frames(data_path, warnings)
    scope, frames = select_origin(
        all_frames,
        args.origin,
        warnings,
        allow_unreviewed=args.allow_unreviewed_capture,
    )

    subjects = sorted({frame.subject for frame in frames})
    split = split_subjects(subjects, args.seed)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    _ensure_writable_tempdir(out_dir / ".tmp")

    if split["scheme"] == "loso":
        run = _run_loso(frames, args, warnings)
        train_frames = run["train_frames"]
        val_frames = run["val_frames"]
        test_frames = run["test_frames"]
        chosen = run["chosen"]
        results = run["results"]
        model_a = results["A"].get("model")
        model_b = results["B"].get("model")
        deploy_model = run["deploy_model"]
        mean_a, std_a = results["A"]["mean"], results["A"]["std"]
        mean_b, std_b = results["B"]["mean"], results["B"]["std"]
        # The deployment model is retrained on all subjects; its standardisation
        # is stored separately from the last-fold A/B diagnostics.
        deploy_mean, deploy_std = run["deploy_mean"], run["deploy_std"]
    else:
        run = _run_group_split(frames, split, args, warnings)
        train_frames = run["train_frames"]
        val_frames = run["val_frames"]
        test_frames = run["test_frames"]
        chosen = run["chosen"]
        results = run["results"]
        model_a = results["A"]["model"]
        model_b = results["B"]["model"]
        deploy_model = results[chosen]["model"]
        mean_a, std_a = results["A"]["mean"], results["A"]["std"]
        mean_b, std_b = results["B"]["mean"], results["B"]["std"]
        deploy_mean, deploy_std = results[chosen]["mean"], results[chosen]["std"]

    # ------------------------------------------------------------------
    # Persist weights.
    # ------------------------------------------------------------------
    checkpoint_paths: dict[str, Path] = {}
    for version, model, mean, std in (
        ("A", model_a, mean_a, std_a),
        ("B", model_b, mean_b, std_b),
    ):
        if model is None:
            continue
        meta = {
            "contract_version": CONTRACT_VERSION,
            "feature_spec_version": FEATURE_SPEC_VERSION,
            "input_version": version,
            "input_dim": int(len(mean)),
            "hidden": list(args.hidden),
            "dropout": args.dropout,
            "label_order": list(LABEL_ORDER),
            "feature_names": list(FEATURE_NAMES),
            "mediapipe_landmarks": list(MEDIAPIPE_33),
            "mean": [float(value) for value in mean],
            "std": [float(value) for value in std],
            "coord_scale_floor": COORD_SCALE_FLOOR,
            "seed": args.seed,
            "data_scope": scope,
            "trained_at": started_at,
        }
        path = out_dir / f"model_{version}.pt"
        save_checkpoint(str(path), model, meta)
        checkpoint_paths[version] = path

    deploy_meta = {
        "contract_version": CONTRACT_VERSION,
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "input_version": chosen,
        "input_dim": int(len(mean_a if chosen == "A" else mean_b)),
        "hidden": list(args.hidden),
        "dropout": args.dropout,
        "label_order": list(LABEL_ORDER),
        "feature_names": list(FEATURE_NAMES),
        "mediapipe_landmarks": list(MEDIAPIPE_33),
        "mean": [float(value) for value in (mean_a if chosen == "A" else mean_b)],
        "std": [float(value) for value in (std_a if chosen == "A" else std_b)],
        "coord_scale_floor": COORD_SCALE_FLOOR,
        "seed": args.seed,
        "data_scope": scope,
        "trained_at": started_at,
    }
    deploy_path = out_dir / "model.pt"
    save_checkpoint(str(deploy_path), deploy_model, deploy_meta)

    # ------------------------------------------------------------------
    # Test evaluation for the deployment model (group split only; LOSO uses OOF).
    # ------------------------------------------------------------------
    if split["scheme"] != "loso":
        predicted, probabilities = _predict_frames(
            deploy_model, test_frames, chosen, deploy_meta["mean"], deploy_meta["std"]
        )
        deploy_test_metrics = compute_metrics(
            [frame.label for frame in test_frames], predicted
        )
        predicted_val, _ = _predict_frames(
            deploy_model, val_frames, chosen, deploy_meta["mean"], deploy_meta["std"]
        )
        deploy_val_metrics = compute_metrics(
            [frame.label for frame in val_frames], predicted_val
        )
    else:
        deploy_test_metrics = results[chosen]["test"]
        deploy_val_metrics = None

    # ------------------------------------------------------------------
    # Metrics, spec, split, smoke samples.
    # ------------------------------------------------------------------
    data_summary = _data_summary(
        data_path, frames, train_frames, val_frames, test_frames, scope, all_frames
    )
    spec = _feature_spec(mean_a, std_a, mean_b, std_b, args)
    spec["deployment"] = {
        "input_version": chosen,
        "checkpoint": "model.pt",
        "standardization": {
            "mean": deploy_mean.tolist(),
            "std": deploy_std.tolist(),
        },
    }
    spec["model"]["chosen_input_version"] = chosen
    spec["model"]["parameter_counts"] = {
        version: int(results[version].get("params", 0)) for version in ("A", "B")
    }
    _write_json(out_dir / "feature_spec.json", spec)

    split_payload: dict[str, Any] = {
        "scheme": split["scheme"],
        "seed": args.seed,
        "train_subjects": split["train"],
        "val_subjects": split["val"],
        "test_subjects": split["test"],
        "test_frame_ids": [frame.frame_id for frame in test_frames],
        "val_frame_ids": [frame.frame_id for frame in val_frames],
        "train_frame_count": len(train_frames),
        "val_frame_count": len(val_frames),
        "test_frame_count": len(test_frames),
    }
    if split["scheme"] == "loso":
        split_payload["folds"] = run["folds"]
        split_payload["note"] = (
            "LOSO metrics are out-of-fold; evaluate_posture.py requires retraining "
            "the folds to reproduce them."
        )
    _write_json(out_dir / "split.json", split_payload)

    models_payload: dict[str, Any] = {}
    for version in ("A", "B"):
        entry = results[version]
        models_payload[version] = {
            "input_version": version,
            "input_dim": entry.get("input_dim"),
            "params": entry.get("params"),
            "epochs_run": entry.get("epochs_run"),
            "best_epoch": entry.get("best_epoch"),
            "best_val_macro_f1": entry.get("best_val_macro_f1"),
            "mean_val_macro_f1": entry.get("mean_val_macro_f1"),
            "train_seconds": entry.get("train_seconds"),
            "val": entry.get("val"),
            "test": entry.get("test"),
            "history": entry.get("history"),
            "fold_val_macro_f1": entry.get("fold_val_macro_f1"),
        }

    chosen_entry = results[chosen]
    metrics_payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "label_policy": describe_label_policy(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": _git_head(),
        "seed": args.seed,
        "chosen_input_version": chosen,
        "selection": {
            "criterion": "validation macro-F1",
            "chosen": chosen,
            "A": results["A"].get("best_val_macro_f1"),
            "B": results["B"].get("best_val_macro_f1"),
            "note": "the test split is evaluated once after selection",
        },
        "input_versions": {
            "A": len(FEATURE_NAMES),
            "B": len(MEDIAPIPE_33) * 4 + len(FEATURE_NAMES),
        },
        "model": {
            "architecture": "MLP",
            "hidden": list(args.hidden),
            "dropout": args.dropout,
            "activation": "ReLU",
            "params": chosen_entry.get("params"),
            "label_order": list(LABEL_ORDER),
            "checkpoint": "model.pt",
            "model_sha256": _sha256(deploy_path),
        },
        "models": models_payload,
        "chosen": {
            "input_version": chosen,
            "val": deploy_val_metrics or chosen_entry.get("val"),
            "test": deploy_test_metrics,
            "macro_f1": deploy_test_metrics["macro_f1"],
            "accuracy": deploy_test_metrics["accuracy"],
            "per_class": deploy_test_metrics["per_class"],
            "confusion_matrix": deploy_test_metrics["confusion_matrix"],
        },
        "confusion_matrix": deploy_test_metrics["confusion_matrix"],
        "data": data_summary,
        "split": {
            "scheme": split["scheme"],
            "seed": args.seed,
            "train_subjects": split["train"],
            "val_subjects": split["val"],
            "test_subjects": split["test"],
            "frames": {"train": len(train_frames), "val": len(val_frames), "test": len(test_frames)},
        },
        "training": {
            "device": "cpu",
            "torch_version": torch.__version__,
            "num_threads": torch.get_num_threads(),
            "duration_seconds": round(
                sum(results[version].get("train_seconds", 0.0) for version in ("A", "B")), 3
            ),
            "epochs_requested": args.epochs,
            "patience": args.patience,
            "batch_size": args.batch_size,
            "learning_rate": args.lr,
            "weight_decay": args.weight_decay,
            "class_weight": "inverse-frequency CrossEntropyLoss",
            "started_at": started_at,
        },
        "warnings": warnings,
        "metrics_scope": data_summary["metrics_scope"],
    }
    if split["scheme"] == "loso":
        metrics_payload["training"]["deploy_seconds"] = run["deploy_seconds"]
        metrics_payload["training"]["deploy_epochs"] = run["fixed_epochs"]

    _write_json(out_dir / "metrics.json", metrics_payload)

    # Confusion matrix plot for the shipped model.
    _plot_confusion(
        deploy_test_metrics,
        out_dir / "confusion_matrix.png",
        f"Posture v0 test confusion matrix ({scope})",
    )

    # Smoke samples: one per ground-truth class, fixed by frame_id.
    pools: dict[str, list[tuple[str, Frame]]] = {label: [] for label in LABEL_ORDER}
    for split_name, rows in (
        ("test", test_frames),
        ("val", val_frames),
        ("train", train_frames),
    ):
        for frame in sorted(rows, key=lambda item: item.frame_id):
            pools[frame.label].append((split_name, frame))

    smoke_samples = []
    smoke_warnings = []
    for label in LABEL_ORDER:
        candidates = pools[label]
        if not candidates:
            smoke_warnings.append(f"no sample available for label={label}")
            continue
        split_name, frame = candidates[0]
        sample = _rounded_sample(frame)
        posture, confidence, probabilities = _predict_payload(
            deploy_model, deploy_meta, sample
        )
        smoke_samples.append(
            {
                "frame_id": frame.frame_id,
                "split": split_name,
                "ground_truth": label,
                "expected_posture": posture,
                "expected_confidence": confidence,
                "expected_probabilities": probabilities,
                "sample": sample,
            }
        )
        if posture != label:
            smoke_warnings.append(
                f"smoke_sample_{frame.frame_id}_predicted_{posture}_ground_truth_{label}"
            )

    smoke_payload = {
        "contract_version": CONTRACT_VERSION,
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "input_version": chosen,
        "model_file": "model.pt",
        "model_sha256": _sha256(deploy_path),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "expected_posture is the stored model output for this exact sample; "
            "ground_truth is the label. Use this file to reconcile a deployed endpoint."
        ),
        "samples": smoke_samples,
        "warnings": smoke_warnings,
    }
    _write_json(out_dir / "smoke_test.json", smoke_payload)

    summary = {
        "out": str(out_dir),
        "chosen_input_version": chosen,
        "A_val_macro_f1": results["A"].get("best_val_macro_f1"),
        "B_val_macro_f1": results["B"].get("best_val_macro_f1"),
        "A_test_macro_f1": results["A"]["test"]["macro_f1"],
        "B_test_macro_f1": results["B"]["test"]["macro_f1"],
        "chosen_test_macro_f1": deploy_test_metrics["macro_f1"],
        "test_accuracy": deploy_test_metrics["accuracy"],
        "params": chosen_entry.get("params"),
        "frames": len(frames),
        "subjects": len(subjects),
        "scope": scope,
        "warnings": warnings + smoke_warnings,
    }
    print(json.dumps(_jsonable(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
