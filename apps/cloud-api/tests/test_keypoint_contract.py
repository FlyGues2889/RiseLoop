"""端云关键点契约一致性：避免两侧顺序漂移导致静默 422。"""

import re
from pathlib import Path

from app.schemas.posture import MEDIAPIPE_33

ROOT = Path(__file__).resolve().parents[3]
CLIENT_CONTRACT = ROOT / "apps" / "desktop-tauri" / "src" / "data" / "keypoints.js"


def test_client_and_server_keypoint_order_match():
    assert CLIENT_CONTRACT.exists(), f"缺少端侧契约文件：{CLIENT_CONTRACT}"
    text = CLIENT_CONTRACT.read_text(encoding="utf-8")
    block = text.split("MEDIAPIPE_33 = [", 1)[1].split("];", 1)[0]
    names = re.findall(r'"([a-z_]+)"', block)
    assert len(names) == 33
    assert tuple(names) == MEDIAPIPE_33
