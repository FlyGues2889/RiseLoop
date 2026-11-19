"""Small CPU-only MLP, checkpoint helpers and version-B coordinate preprocessing."""

from __future__ import annotations

import math
import os
from typing import Any, Mapping, Sequence

import torch
from torch import nn

from posture_runtime import FEATURE_ORDER, FEATURE_SPEC_VERSION, LABELS

# Model-side response policy, shared by training smoke checks and serving.
MIN_MODEL_CONFIDENCE = 0.5
# Version-B coordinate preprocessing: shoulder midpoint origin, shoulder width scale.
COORD_SCALE_FLOOR = 0.05


class PostureMLP(nn.Module):
    """2-3 hidden layer MLP.  Parameter count stays well below 100k."""

    def __init__(
        self,
        input_dim: int,
        hidden: Sequence[int] = (64, 32),
        num_classes: int = len(LABELS),
        dropout: float = 0.15,
    ) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        previous = input_dim
        for width in hidden:
            layers.append(nn.Linear(previous, int(width)))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(float(dropout)))
            previous = int(width)
        layers.append(nn.Linear(previous, num_classes))
        self.net = nn.Sequential(*layers)
        self.input_dim = int(input_dim)
        self.hidden = tuple(int(w) for w in hidden)
        self.dropout = float(dropout)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.net(inputs)

    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())


def build_model(meta: Mapping[str, Any]) -> PostureMLP:
    return PostureMLP(
        input_dim=int(meta["input_dim"]),
        hidden=tuple(int(w) for w in meta.get("hidden", (64, 32))),
        dropout=float(meta.get("dropout", 0.15)),
    )


def save_checkpoint(path: str, model: PostureMLP, meta: Mapping[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "meta": dict(meta)}, path)


def load_checkpoint(path: str, map_location: str = "cpu") -> tuple[PostureMLP, dict[str, Any]]:
    try:
        payload = torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:  # torch < 2.0 has no weights_only argument
        payload = torch.load(path, map_location=map_location)
    if not isinstance(payload, Mapping) or "state_dict" not in payload:
        raise ValueError("checkpoint does not contain a state_dict")
    meta = dict(payload.get("meta", {}))
    if meta.get("feature_spec_version") != FEATURE_SPEC_VERSION:
        raise ValueError("checkpoint feature_spec_version does not match runtime")
    if meta.get("label_order") != list(LABELS):
        raise ValueError("checkpoint label order does not match runtime")
    if meta.get("feature_names") != list(FEATURE_ORDER):
        raise ValueError("checkpoint feature order does not match runtime")
    model = build_model(meta)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, meta


def coordinates_vector(keypoints: Sequence[Mapping[str, Any]]) -> list[float]:
    """132 version-B coordinates: shoulder-centre origin, shoulder-width scale.

    Kept here (model preprocessing), not in posture_runtime, because it is not a
    cloud contract formula.  The same function is used by training and serving.
    """

    by_name = {str(point["name"]).strip().lower(): point for point in keypoints}
    left = by_name["left_shoulder"]
    right = by_name["right_shoulder"]
    ox = (float(left["x"]) + float(right["x"])) / 2.0
    oy = (float(left["y"]) + float(right["y"])) / 2.0
    oz = (float(left["z"]) + float(right["z"])) / 2.0
    scale = max(
        math.hypot(float(right["x"]) - float(left["x"]), float(right["y"]) - float(left["y"])),
        COORD_SCALE_FLOOR,
    )
    vector: list[float] = []
    for point in keypoints:
        vector.extend(
            (
                (float(point["x"]) - ox) / scale,
                (float(point["y"]) - oy) / scale,
                (float(point["z"]) - oz) / scale,
                float(point["visibility"]),
            )
        )
    return vector


def softmax_probabilities(logits: torch.Tensor) -> list[float]:
    probabilities = torch.softmax(logits, dim=-1).detach().cpu()
    if probabilities.ndim > 1:
        probabilities = probabilities[0]
    return [float(value) for value in probabilities.tolist()]
