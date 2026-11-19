"""Shared metric helpers so training and independent evaluation agree."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

from posture_contract import LABELS as LABEL_ORDER


def compute_metrics(y_true: Sequence[str], y_pred: Sequence[str]) -> dict[str, Any]:
    labels = list(LABEL_ORDER)
    true_array = np.asarray(list(y_true), dtype=object)
    pred_array = np.asarray(list(y_pred), dtype=object)
    if true_array.shape[0] != pred_array.shape[0]:
        raise ValueError("y_true and y_pred length mismatch")

    precision, recall, f1, support = precision_recall_fscore_support(
        true_array,
        pred_array,
        labels=labels,
        zero_division=0,
    )
    per_class = {}
    for index, label in enumerate(labels):
        per_class[label] = {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }

    matrix = confusion_matrix(true_array, pred_array, labels=labels)
    return {
        "accuracy": float(accuracy_score(true_array, pred_array)),
        "macro_f1": float(f1_score(true_array, pred_array, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(true_array, pred_array, labels=labels, average="weighted", zero_division=0)),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": labels,
            "matrix": [[int(value) for value in row] for row in matrix.tolist()],
            "rows": "ground_truth",
            "columns": "predicted",
        },
        "support": int(sum(per_class[label]["support"] for label in labels)),
    }
