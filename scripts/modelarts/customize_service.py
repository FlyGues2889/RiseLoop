"""ModelArts custom inference script for the v1 posture classifier.

Deployment contract
-------------------
ModelArts (PyTorch engine) loads this file as ``customize_service.py`` and
expects a subclass of ``PTServingBaseService``:

    from model_service.pytorch_model_service import PTServingBaseService

Reference (checked 2026-11-19):
https://support.huaweicloud.com/usermanual-standard-modelarts/inference-modelarts-0057.html

Feature extraction and response assembly delegate to ``posture_runtime.py``
(the only deployment copy of the cloud contract).  This file only validates
index order against ``feature_spec.json``, runs torch and logs safe fields.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0] or os.getcwd()) == _SCRIPT_DIR:
    sys.path[0] = _SCRIPT_DIR
elif _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import posture_runtime as runtime  # noqa: E402
from model import coordinates_vector, load_checkpoint  # noqa: E402

FEATURE_SPEC_VERSION = runtime.FEATURE_SPEC_VERSION
features_from_keypoints = runtime.features_from_keypoints

try:  # ModelArts base image provides this package.
    from model_service.pytorch_model_service import PTServingBaseService

    MODELARTS_BASE = True
except ImportError:  # local tests / serve.py
    MODELARTS_BASE = False

    class PTServingBaseService:  # type: ignore[no-redef]
        """Minimal local stand-in; never used on ModelArts."""

        def __init__(self, model_name: str = "posture-v1", model_path: str = "") -> None:
            self.model_name = model_name
            self.model_path = model_path


logger = logging.getLogger("posture_service")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


class InputContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_request_id(value: Any) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if 0 < len(candidate) <= 64 and all(
            character.isalnum() or character in "-_." for character in candidate
        ):
            return candidate
    return uuid.uuid4().hex[:12]


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        raise InputContractError("invalid_field_type", f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InputContractError("invalid_field_type", f"{field} must be a number") from exc
    if not math.isfinite(number):
        raise InputContractError("invalid_field_value", f"{field} must be finite")
    return number


class Model(PTServingBaseService):
    """One resident model; one forward pass per request."""

    def __init__(self, model_name: str, model_path: str) -> None:
        self.model_name = model_name
        self.model_path = model_path
        self.started_at = time.perf_counter()
        self.recompute_count = 0
        self.error_count = 0
        self.request_count = 0

        torch.set_num_threads(1)
        checkpoint = self._resolve_checkpoint(model_path)
        self.model, self.meta = load_checkpoint(str(checkpoint))
        self.model.eval()
        self.input_version = str(self.meta["input_version"])
        self.input_dim = int(self.meta["input_dim"])
        self.mean = np.asarray(self.meta["mean"], dtype=np.float64)
        self.std = np.asarray(self.meta["std"], dtype=np.float64)
        if self.mean.shape != (self.input_dim,) or self.std.shape != (self.input_dim,):
            raise ValueError("checkpoint normalisation shape mismatch")
        if self.meta.get("feature_spec_version") != FEATURE_SPEC_VERSION:
            raise ValueError("checkpoint feature_spec_version mismatch")

        spec = self._load_feature_spec(checkpoint.parent / "feature_spec.json")
        self.keypoint_order = list(spec["mediapipe_landmarks"])
        self.feature_order = list(spec["feature_order"])
        if self.feature_order != list(runtime.FEATURE_ORDER):
            raise ValueError("feature_spec feature_order mismatch")
        checkpoint_order = list(self.meta.get("mediapipe_landmarks", []))
        if checkpoint_order and self.keypoint_order != checkpoint_order:
            raise ValueError("feature_spec/checkpoint keypoint order mismatch")
        if len(self.keypoint_order) != 33:
            raise ValueError("feature_spec must contain 33 landmarks")
        if list(spec["label_order"]) != list(runtime.LABELS):
            raise ValueError("feature_spec label_order mismatch")
        if spec.get("feature_spec_version") != FEATURE_SPEC_VERSION:
            raise ValueError("feature_spec_version mismatch")

        with torch.inference_mode():
            self.model(torch.zeros(1, self.input_dim, dtype=torch.float32))

        logger.info(
            "model_loaded name=%s feature_spec_version=%s input_version=%s input_dim=%s load_ms=%.3f base=%s",
            self.model_name,
            FEATURE_SPEC_VERSION,
            self.input_version,
            self.input_dim,
            (time.perf_counter() - self.started_at) * 1000.0,
            "modelarts" if MODELARTS_BASE else "local",
        )

    @staticmethod
    def _resolve_checkpoint(model_path: str) -> Path:
        candidate = Path(model_path)
        if candidate.is_dir():
            candidate = candidate / "model.pt"
        if not candidate.is_file():
            raise FileNotFoundError(f"model checkpoint not found: {model_path}")
        return candidate

    @staticmethod
    def _load_feature_spec(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"feature_spec.json not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _normalise_points(self, raw: Any) -> list[dict[str, float]]:
        if not isinstance(raw, (list, tuple)):
            raise InputContractError("invalid_keypoints_type", "keypoints must be a list")
        if len(raw) != len(self.keypoint_order):
            raise InputContractError(
                "invalid_keypoints_count",
                f"keypoints must contain exactly {len(self.keypoint_order)} items",
            )
        points: list[dict[str, float]] = []
        for index, (item, expected) in enumerate(zip(raw, self.keypoint_order)):
            if not isinstance(item, Mapping):
                raise InputContractError(
                    "invalid_keypoint_type", f"keypoints[{index}] must be an object"
                )
            name = item.get("name")
            if not isinstance(name, str) or name.strip().lower() != expected:
                raise InputContractError(
                    "invalid_keypoints_order", f"keypoints[{index}] must be {expected!r}"
                )
            x = _number(item.get("x"), f"keypoints[{index}].x")
            y = _number(item.get("y"), f"keypoints[{index}].y")
            z = _number(item.get("z"), f"keypoints[{index}].z")
            visibility = _number(item.get("visibility"), f"keypoints[{index}].visibility")
            if not (-2.0 <= x <= 4.0 and -2.0 <= y <= 4.0):
                raise InputContractError(
                    "invalid_keypoint_range", f"keypoints[{index}].x/y outside range"
                )
            if not (-4.0 <= z <= 4.0):
                raise InputContractError(
                    "invalid_keypoint_range", f"keypoints[{index}].z outside range"
                )
            if not (0.0 <= visibility <= 1.0):
                raise InputContractError(
                    "invalid_keypoint_range", f"keypoints[{index}].visibility outside [0,1]"
                )
            points.append(
                {"name": expected, "x": x, "y": y, "z": z, "visibility": visibility}
            )
        return points

    @staticmethod
    def _validate_features(raw: Any) -> dict[str, float]:
        if not isinstance(raw, Mapping):
            raise InputContractError("invalid_features_type", "features must be an object")
        if set(raw.keys()) != set(runtime.FEATURE_ORDER):
            raise InputContractError(
                "invalid_features_shape",
                "features must contain exactly the contract fields",
            )
        return {
            name: _number(raw[name], f"features.{name}") for name in runtime.FEATURE_ORDER
        }

    @staticmethod
    def _features_close(left: Mapping[str, float], right: Mapping[str, float], tol: float = 1e-2) -> bool:
        return all(
            abs(float(left[name]) - float(right[name])) <= tol
            for name in runtime.FEATURE_ORDER
        )

    def _error(
        self, request_id: str, code: str, message: str, started: float
    ) -> dict[str, Any]:
        self.error_count += 1
        return {
            "ok": False,
            "request_id": request_id,
            "started": started,
            "error": {"code": code, "message": message},
        }

    def _preprocess(self, data: Any) -> dict[str, Any]:
        started = time.perf_counter()
        if not isinstance(data, Mapping):
            return self._error(
                uuid.uuid4().hex[:12],
                "invalid_payload",
                "request body must be a JSON object",
                started,
            )

        request_id = _safe_request_id(data.get("request_id"))
        self.request_count += 1

        keypoints_raw = data.get("keypoints")
        if keypoints_raw is None:
            return self._error(
                request_id, "missing_keypoints", "keypoints is required", started
            )

        try:
            points = self._normalise_points(keypoints_raw)
        except InputContractError as exc:
            return self._error(request_id, exc.code, exc.message, started)

        computed = runtime.features_from_keypoints(points)
        features_raw = data.get("features")
        warnings: list[str] = []
        if features_raw is None:
            features = computed
            warnings.append("features_recomputed_missing")
            self.recompute_count += 1
        else:
            try:
                supplied = self._validate_features(features_raw)
            except InputContractError as exc:
                features = computed
                warnings.append(f"features_recomputed_{exc.code}")
                self.recompute_count += 1
            else:
                if not self._features_close(computed, supplied):
                    warnings.append("features_supplied_mismatch")
                    self.recompute_count += 1
                features = supplied

        try:
            if self.input_version == "A":
                raw = runtime.features_vector(features)
            elif self.input_version == "B":
                raw = coordinates_vector(points) + runtime.features_vector(features)
            else:
                raise InputContractError(
                    "unsupported_input_version", "checkpoint input_version must be A or B"
                )
            vector = np.asarray(raw, dtype=np.float64)
            if vector.shape != (self.input_dim,):
                raise InputContractError(
                    "invalid_input_dimension", "input dimension does not match checkpoint"
                )
            normalised = (vector - self.mean) / self.std
            tensor = torch.tensor(normalised, dtype=torch.float32).unsqueeze(0)
        except InputContractError as exc:
            return self._error(request_id, exc.code, exc.message, started)

        return {
            "ok": True,
            "started": started,
            "request_id": request_id,
            "tensor": tensor,
            "warnings": warnings,
        }

    def _inference(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("ok"):
            return data
        started = time.perf_counter()
        try:
            with torch.inference_mode():
                logits = self.model(data["tensor"])
                probabilities = torch.softmax(logits, dim=-1)[0].cpu().tolist()
        except Exception:  # noqa: BLE001 - never leak a stack trace
            return self._error(
                data.get("request_id", "-"), "inference_failed", "inference failed", started
            )
        return {
            "ok": True,
            "started": data.get("started", started),
            "request_id": data.get("request_id", "-"),
            "probabilities": [float(value) for value in probabilities],
            "inference_ms": (time.perf_counter() - started) * 1000.0,
        }

    def _postprocess(self, data: dict[str, Any]) -> dict[str, Any]:
        started = data.get("started", time.perf_counter())
        request_id = data.get("request_id", "-")
        latency_ms = (time.perf_counter() - started) * 1000.0

        if not data.get("ok"):
            error = data.get("error", {"code": "internal_error", "message": "inference failed"})
            logger.info(
                "posture_inference request_id=%s posture=%s confidence=%.6f latency_ms=%.3f error_code=%s",
                request_id,
                "-",
                0.0,
                latency_ms,
                error.get("code", "internal_error"),
            )
            return {
                "error": {
                    "code": error.get("code", "internal_error"),
                    "message": error.get("message", "inference failed"),
                    "request_id": request_id,
                }
            }

        try:
            probabilities = {
                label: probability
                for label, probability in zip(runtime.LABELS, data["probabilities"])
            }
            response = runtime.build_response(probabilities)
        except Exception:  # noqa: BLE001
            logger.info(
                "posture_inference request_id=%s posture=%s confidence=%.6f latency_ms=%.3f error_code=%s",
                request_id,
                "-",
                0.0,
                latency_ms,
                "invalid_output",
            )
            return {
                "error": {"code": "invalid_output", "message": "model output invalid", "request_id": request_id}
            }

        logger.info(
            "posture_inference request_id=%s posture=%s confidence=%.6f latency_ms=%.3f error_code=%s",
            request_id,
            response["posture"],
            response["confidence"],
            latency_ms,
            "-",
        )
        return response

    def predict(self, payload: Any) -> dict[str, Any]:
        """Run the full ModelArts hook chain for local tests and serve.py."""

        return self._postprocess(self._inference(self._preprocess(payload)))
