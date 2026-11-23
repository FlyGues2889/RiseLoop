"""Capture MediaPipe Pose landmarks from a webcam into keypoints-only JSONL.

The output is a raw capture file, not a training dataset. Feed it to
``collect_frames.py`` to validate, recompute the five features and assign
``frame_id``::

    python scripts/modelarts/collect_frames.py --input raw.jsonl --out frames.jsonl --append

This script never writes images, video, screenshots or pixel arrays. Each line
contains only the 33 normalized landmarks and the segment metadata.

Run with CPython 3.11 (MediaPipe may not publish wheels for newer versions)::

    py -3.11 -m venv .venv-capture
    .venv-capture\\Scripts\\activate
    python -m pip install -r scripts/modelarts/requirements-capture.txt

    python scripts/modelarts/capture_webcam.py \\
        --out data/posture/raw/s01__baseline__laptop-cam__office.jsonl \\
        --subject s01 --device laptop-cam --scene office --label baseline

Use ``--self-test`` to verify the data path without a camera.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from posture_contract import (
    DEFAULT_FRAMING,
    FRAMINGS,
    KEYPOINT_ORDER,
    LABELS,
    ContractError,
    validate_keypoint_ranges,
    validate_keypoints,
)

DEFAULT_MODEL = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "desktop-tauri"
    / "public"
    / "models"
    / "pose_landmarker_lite.task"
)


def _field(point: Any, name: str, default: float = 0.0) -> float:
    if isinstance(point, dict):
        value = point.get(name, default)
    else:
        value = getattr(point, name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalise_landmarks(landmarks: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert MediaPipe landmarks with the same rounding as the end side."""

    if len(landmarks) != len(KEYPOINT_ORDER):
        raise ContractError(
            f"需要 {len(KEYPOINT_ORDER)} 个关键点，实际 {len(landmarks)} 个"
        )

    points: list[dict[str, Any]] = []
    for name, landmark in zip(KEYPOINT_ORDER, landmarks):
        visibility = min(1.0, max(0.0, _field(landmark, "visibility")))
        points.append(
            {
                "name": name,
                "x": round(_field(landmark, "x"), 4),
                "y": round(_field(landmark, "y"), 4),
                "z": round(_field(landmark, "z"), 4),
                "visibility": round(visibility, 3),
            }
        )
    validate_keypoint_ranges(points)
    return points


def make_record(
    points: Sequence[dict[str, Any]],
    *,
    subject: str,
    device: str,
    scene: str,
    label: str,
    framing: str = DEFAULT_FRAMING,
    note: str = "",
    ts: str | None = None,
) -> dict[str, Any]:
    """Build one raw capture row; media fields are deliberately absent."""

    if label not in LABELS:
        raise ContractError(f"未知类别：{label!r}")
    if framing not in FRAMINGS:
        raise ContractError(f"未知取景：{framing!r}")
    if not subject.strip():
        raise ContractError("subject 不能为空")
    validate_keypoint_ranges(points)
    return {
        "ts": ts or datetime.now().astimezone().isoformat(timespec="seconds"),
        "device": device,
        "subject": subject,
        "scene": scene,
        "framing": framing,
        "label": label,
        "label_source": "human",
        "origin": "capture",
        "note": note,
        "keypoints": [
            {
                "name": str(point["name"]),
                "x": float(point["x"]),
                "y": float(point["y"]),
                "z": float(point["z"]),
                "visibility": float(point["visibility"]),
            }
            for point in points
        ],
    }


def write_records(
    path: Path, records: Iterable[dict[str, Any]], *, append: bool = False
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    written = 0
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            written += 1
    return written


def self_test_pose(label: str) -> list[dict[str, Any]]:
    """Generate a deterministic 33-point pose that matches the requested label."""

    base = {
        "nose": (0.50, 0.20, -0.10),
        "left_shoulder": (0.40, 0.40, -0.10),
        "right_shoulder": (0.60, 0.40, -0.10),
        "left_hip": (0.43, 0.70, -0.10),
        "right_hip": (0.57, 0.70, -0.10),
    }
    visibility = 0.99
    if label == "forward_head":
        base["nose"] = (0.50, 0.20, -0.26)
    elif label == "lateral_tilt":
        base["left_shoulder"] = (0.40, 0.35, -0.10)
        base["right_shoulder"] = (0.60, 0.45, -0.10)
    elif label == "undetermined":
        visibility = 0.20

    points = []
    for name in KEYPOINT_ORDER:
        x, y, z = base.get(name, (0.50, 0.50, -0.10))
        points.append(
            {
                "name": name,
                "x": x,
                "y": y,
                "z": z,
                "visibility": visibility,
            }
        )
    validate_keypoints(points)
    return points


def run_self_test(args: argparse.Namespace) -> int:
    points = self_test_pose(args.label)
    records = [
        make_record(
            points,
            subject=args.subject,
            device=args.device,
            scene=args.scene,
            framing=args.framing,
            label=args.label,
            note=args.note,
        )
        for _ in range(args.self_test_frames)
    ]
    written = write_records(args.out, records, append=args.append)
    print(
        json.dumps(
            {
                "mode": "self-test",
                "out": str(args.out),
                "written": written,
                "label": args.label,
                "framing": args.framing,
                "subject": args.subject,
                "media_written": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def ascii_model_path(path: Path) -> Path:
    """MediaPipe's C++ loader cannot open non-ASCII paths on Windows."""

    try:
        str(path).encode("ascii")
        return path
    except UnicodeEncodeError:
        pass

    target = Path(tempfile.gettempdir()) / "riseloop-capture-models" / path.name
    source_size = path.stat().st_size
    if not target.is_file() or target.stat().st_size != source_size:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return target


def _load_landmarker(model_path: Path) -> tuple[Any, Any]:
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as exc:
        raise SystemExit(
            "mediapipe 未安装。请用 CPython 3.11 并执行："
            " python -m pip install -r scripts/modelarts/requirements-capture.txt"
        ) from exc

    if not model_path.is_file():
        raise SystemExit(f"模型文件不存在：{model_path}")

    options = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(ascii_model_path(model_path))),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return mp, vision.PoseLandmarker.create_from_options(options)


def _draw_preview(
    cv2: Any,
    frame: Any,
    points: Sequence[dict[str, Any]] | None,
    *,
    label: str,
    written: int,
    remaining: float,
) -> None:
    height, width = frame.shape[:2]
    if points:
        for point in points:
            x = int(point["x"] * width)
            y = int(point["y"] * height)
            cv2.circle(frame, (x, y), 2, (0, 255, 0), -1)
    status = "no pose" if not points else f"{label}  frames={written}"
    cv2.putText(
        frame,
        status,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0) if points else (0, 0, 255),
        2,
        cv2.LINE_AA,
    )
    if remaining > 0:
        cv2.putText(
            frame,
            f"{remaining:0.1f}s  q/ESC to stop",
            (12, 56),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )


BLACK_FRAME_MEAN = 5.0


def frame_is_black(frame: Any) -> bool:
    return float(frame.mean()) < BLACK_FRAME_MEAN


def prime_camera(camera: Any, cv2: Any, *, timeout: float = 8.0) -> float:
    """Drain black frames that virtual cameras emit until their source attaches."""

    started = time.monotonic()
    if timeout <= 0:
        return 0.0
    deadline = started + timeout
    while time.monotonic() < deadline:
        ok, frame = camera.read()
        if ok and frame is not None and not frame_is_black(frame):
            return time.monotonic() - started
    return time.monotonic() - started


def run_webcam(args: argparse.Namespace) -> int:
    try:
        import cv2
    except ImportError as exc:
        raise SystemExit(
            "opencv-python 未安装。请用 CPython 3.11 并执行："
            " python -m pip install -r scripts/modelarts/requirements-capture.txt"
        ) from exc

    mp, landmarker = _load_landmarker(args.model)
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise SystemExit(
            f"无法打开摄像头 {args.camera}。检查设备占用、Windows 摄像头权限，"
            "或换一个 --camera 序号。"
        )

    if args.width > 0:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    if args.height > 0:
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    prime_camera(camera, cv2, timeout=args.prime)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    output = args.out.open("a" if args.append else "w", encoding="utf-8", newline="\n")
    start = time.monotonic()
    write_from = start + max(0.0, args.warmup)
    stop_at = None if args.duration <= 0 else write_from + args.duration
    next_sample = start
    last_timestamp = -1
    written = 0
    no_pose = 0
    invalid = 0
    latest_points: list[dict[str, Any]] | None = None

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                raise SystemExit("摄像头读帧失败，可能被其他程序占用。")

            now = time.monotonic()
            if stop_at is not None and now >= stop_at:
                break

            if now >= next_sample:
                next_sample = now + max(0.01, args.interval)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp_ms = max(last_timestamp + 1, int((now - start) * 1000))
                last_timestamp = timestamp_ms
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                    timestamp_ms,
                )
                landmarks = (result.pose_landmarks or [])[0] if result.pose_landmarks else []
                if not landmarks:
                    if now >= write_from:
                        no_pose += 1
                    latest_points = None
                else:
                    try:
                        latest_points = normalise_landmarks(landmarks)
                    except ContractError:
                        if now >= write_from:
                            invalid += 1
                        latest_points = None
                    else:
                        if now >= write_from:
                            record = make_record(
                                latest_points,
                                subject=args.subject,
                                device=args.device,
                                scene=args.scene,
                                framing=args.framing,
                                label=args.label,
                                note=args.note,
                            )
                            output.write(
                                json.dumps(
                                    record, ensure_ascii=False, separators=(",", ":")
                                )
                                + "\n"
                            )
                            written += 1

            if args.preview:
                shown = frame.copy()
                remaining = 0.0 if stop_at is None else max(0.0, stop_at - now)
                _draw_preview(
                    cv2,
                    shown,
                    latest_points,
                    label=args.label,
                    written=written,
                    remaining=remaining,
                )
                cv2.imshow("Rise Loop capture - keypoints only", shown)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        output.close()
        camera.release()
        if args.preview:
            cv2.destroyAllWindows()
        landmarker.close()

    print(
        json.dumps(
            {
                "mode": "webcam",
                "out": str(args.out),
                "written": written,
                "no_pose": no_pose,
                "invalid": invalid,
                "label": args.label,
                "framing": args.framing,
                "subject": args.subject,
                "device": args.device,
                "scene": args.scene,
                "interval_s": args.interval,
                "duration_s": args.duration,
                "media_written": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if written else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="raw keypoints .jsonl")
    parser.add_argument("--subject", required=True, help="受试者编号，如 s01")
    parser.add_argument("--label", choices=LABELS, required=True, help="整段姿态标签")
    parser.add_argument("--device", default="unknown")
    parser.add_argument("--scene", default="unknown")
    parser.add_argument(
        "--framing",
        choices=FRAMINGS,
        default=DEFAULT_FRAMING,
        help="取景范围；久坐机位用 upper_body",
    )
    parser.add_argument("--note", default="")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--duration", type=float, default=30.0, help="0 = until q/Ctrl+C")
    parser.add_argument("--interval", type=float, default=0.5, help="seconds between samples")
    parser.add_argument("--warmup", type=float, default=2.0, help="discard seconds before writing")
    parser.add_argument(
        "--prime",
        type=float,
        default=8.0,
        help="seconds to wait for a non-black frame before the timeline starts",
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--self-test", action="store_true", help="write synthetic rows, no camera")
    parser.add_argument("--self-test-frames", type=int, default=3)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.interval <= 0:
        parser.error("--interval 必须大于 0")
    if args.duration < 0:
        parser.error("--duration 不能为负数")
    if args.warmup < 0:
        parser.error("--warmup 不能为负数")
    if args.prime < 0:
        parser.error("--prime 不能为负数")
    if args.self_test_frames < 1:
        parser.error("--self-test-frames 必须大于 0")

    args.preview = not args.no_preview
    if args.self_test:
        return run_self_test(args)
    return run_webcam(args)


if __name__ == "__main__":
    raise SystemExit(main())
