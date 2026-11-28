"""训练侧访问云端契约的唯一入口。

33 点顺序、特征公式、类别枚举一律引用 apps/cloud-api，本文件不重复定义。
部署到 ModelArts 的推理包无法 import 本仓库，那份副本在 posture_runtime.py，
由 apps/cloud-api/tests/test_modelarts_contract_parity.py 锁定。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for _path in (
    ROOT / "apps" / "cloud-api",
    ROOT / "packages" / "intervention-engine" / "src",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pydantic import ValidationError  # noqa: E402

from app.schemas.posture import (  # noqa: E402
    KEYPOINT_INDEX,
    MEDIAPIPE_33,
    UPPER_BODY_NAMES,
    Keypoint,
    PostureBaseline,
    PostureFeatures,
)
from app.services.posture_features import (  # noqa: E402
    HEAD_GEOMETRY_ORDER,
    MODEL_FEATURE_ORDER,
    baseline_from_keypoints as _server_baseline,
    extract_features as _server_features,
    model_features_from_keypoints as _server_model_features,
)
from intervention_engine import PostureClass  # noqa: E402

FEATURE_SPEC_VERSION = "v3"
KEYPOINT_ORDER = MEDIAPIPE_33
UPPER_BODY_POINTS = UPPER_BODY_NAMES
FEATURE_ORDER = tuple(PostureFeatures.model_fields)
BASELINE_ORDER = tuple(PostureBaseline.model_fields)
BASELINE_DEFAULTS = PostureBaseline().model_dump()
COORDINATE_ORDER = ("x", "y", "z", "visibility")
LABELS = tuple(label.value for label in PostureClass)
FRAMINGS = ("upper_body", "full_body")
DEFAULT_FRAMING = "upper_body"
MIN_UPPER_BODY_VISIBILITY = 0.5


class ContractError(ValueError):
    """输入不符合端云契约。"""

    def __init__(self, message: str = "", code: str = "contract_error") -> None:
        super().__init__(message)
        self.code = code


def keypoint_names(keypoints: Sequence[dict[str, Any]]) -> list[str]:
    return [str(point.get("name", "")).strip().lower() for point in keypoints]


def validate_keypoints(keypoints: Sequence[dict[str, Any]]) -> None:
    names = keypoint_names(keypoints)
    if len(names) != len(KEYPOINT_ORDER):
        raise ContractError(f"需要 {len(KEYPOINT_ORDER)} 个关键点，实际 {len(names)} 个")
    for index, (actual, expected) in enumerate(zip(names, KEYPOINT_ORDER)):
        if actual != expected:
            raise ContractError(
                f"关键点顺序不符：索引 {index} 应为 {expected}，实际 {actual}"
            )


def _to_keypoint(index: int, raw: dict[str, Any]) -> Keypoint:
    try:
        fields = {name: raw[name] for name in ("name", "x", "y", "z", "visibility")}
    except KeyError as exc:
        raise ContractError(f"关键点 {index} 缺字段 {exc.args[0]}", code="missing_field") from exc
    try:
        return Keypoint(**fields)
    except ValidationError as exc:
        raise ContractError(
            f"关键点 {index} 数值越界", code="keypoint_out_of_range"
        ) from exc


def validate_keypoint_ranges(keypoints: Sequence[dict[str, Any]]) -> None:
    """MediaPipe can emit landmarks outside the frame; the contract cannot."""

    validate_keypoints(keypoints)
    for index, raw in enumerate(keypoints):
        _to_keypoint(index, raw)


def _baseline(raw: Mapping[str, Any] | None) -> PostureBaseline:
    if raw is None:
        return PostureBaseline()
    try:
        return PostureBaseline.model_validate(raw)
    except ValidationError as exc:
        raise ContractError("baseline 数值越界", code="invalid_baseline") from exc


def baseline_from_keypoints(keypoints: Sequence[dict[str, Any]]) -> dict[str, float]:
    validate_keypoints(keypoints)
    points = [_to_keypoint(index, raw) for index, raw in enumerate(keypoints)]
    return _server_baseline(points).model_dump()


def features_from_keypoints(
    keypoints: Sequence[dict[str, Any]],
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    validate_keypoints(keypoints)
    points = [_to_keypoint(index, raw) for index, raw in enumerate(keypoints)]
    return _server_features(points, _baseline(baseline)).model_dump()


def features_vector(features: dict[str, float]) -> list[float]:
    missing = [name for name in FEATURE_ORDER if name not in features]
    if missing:
        raise ContractError(f"特征缺字段：{', '.join(missing)}")
    return [float(features[name]) for name in FEATURE_ORDER]


def model_features_from_keypoints(
    keypoints: Sequence[dict[str, Any]],
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    validate_keypoints(keypoints)
    points = [_to_keypoint(index, raw) for index, raw in enumerate(keypoints)]
    return _server_model_features(points, _baseline(baseline))


def model_features_vector(features: dict[str, float]) -> list[float]:
    missing = [name for name in MODEL_FEATURE_ORDER if name not in features]
    if missing:
        raise ContractError(f"模型特征缺字段：{', '.join(missing)}")
    return [float(features[name]) for name in MODEL_FEATURE_ORDER]


def coordinates_vector(keypoints: Sequence[dict[str, Any]]) -> list[float]:
    validate_keypoints(keypoints)
    values: list[float] = []
    for index, point in enumerate(keypoints):
        for key in COORDINATE_ORDER:
            if key not in point:
                raise ContractError(f"关键点 {index} 缺字段 {key}")
            values.append(float(point[key]))
    return values


def feature_spec() -> dict[str, Any]:
    return {
        "version": FEATURE_SPEC_VERSION,
        "keypoints": list(KEYPOINT_ORDER),
        "upper_body_points": list(UPPER_BODY_POINTS),
        "features": list(FEATURE_ORDER),
        "model_features": list(MODEL_FEATURE_ORDER),
        "baseline_fields": list(BASELINE_ORDER),
        "baseline_defaults": BASELINE_DEFAULTS,
        "labels": list(LABELS),
        "coordinates": list(COORDINATE_ORDER),
        "framings": list(FRAMINGS),
        "min_upper_body_visibility": MIN_UPPER_BODY_VISIBILITY,
    }


def keypoint_index(name: str) -> int:
    return KEYPOINT_INDEX[name]
