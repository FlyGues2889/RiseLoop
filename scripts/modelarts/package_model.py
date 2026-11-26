"""Collect the files ModelArts needs into one upload directory.

    python scripts/modelarts/package_model.py \
        --artifacts data/posture/reports/v3-loso \
        --out data/posture/reports/v3-loso/package

Only code, ``model.pt`` and ``feature_spec.json`` are copied.  Training data,
per-fold checkpoints and logs stay out of the package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import posture_runtime

PACKAGE_FILES = (
    "customize_service.py",
    "posture_runtime.py",
    "model.py",
    "model.pt",
    "feature_spec.json",
)
CODE_DIR = Path(__file__).resolve().parent
CODE_FILES = {"customize_service.py", "posture_runtime.py", "model.py"}


def _source_for(name: str, artifacts: Path) -> Path:
    return (CODE_DIR if name in CODE_FILES else artifacts) / name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("data/posture/reports/v3-loso"),
        help="directory containing model.pt and feature_spec.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="upload directory; defaults to <artifacts>/package",
    )
    args = parser.parse_args(argv)

    source = args.artifacts.resolve()
    output = (args.out or source / "package").resolve()
    missing = [
        name for name in PACKAGE_FILES if not _source_for(name, source).is_file()
    ]
    if missing:
        raise SystemExit(f"missing package files: {', '.join(missing)}")

    spec = json.loads((source / "feature_spec.json").read_text(encoding="utf-8"))
    if spec.get("feature_spec_version") != posture_runtime.FEATURE_SPEC_VERSION:
        raise SystemExit(
            "feature_spec_version mismatch: "
            f"{spec.get('feature_spec_version')} != {posture_runtime.FEATURE_SPEC_VERSION}"
        )
    if list(spec.get("feature_order", [])) != list(posture_runtime.FEATURE_ORDER):
        raise SystemExit("feature_order mismatch between feature_spec and posture_runtime")
    if list(spec.get("baseline_fields", [])) != list(posture_runtime.BASELINE_FIELDS):
        raise SystemExit("baseline_fields mismatch between feature_spec and posture_runtime")

    output.mkdir(parents=True, exist_ok=True)
    files = []
    for name in PACKAGE_FILES:
        target = output / name
        shutil.copy2(_source_for(name, source), target)
        files.append(
            {"name": name, "bytes": target.stat().st_size, "sha256": _sha256(target)}
        )

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "feature_spec_version": spec.get("feature_spec_version"),
        "input_version": spec.get("deployment", {}).get("input_version"),
        "files": files,
    }
    (output / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"out": str(output), **manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
