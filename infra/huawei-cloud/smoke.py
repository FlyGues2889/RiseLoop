"""端到端冒烟：注册 → 评估 → 上报久坐时间 → 当前干预 → 反馈 → 基线 → 姿态推理。

用法：python smoke.py http://<host>:8000
只依赖标准库，可在本机、云主机或任何能访问 API 的机器上执行。
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def call(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    return call_allow_error(method, path, body, token)


def call_allow_error(
    method: str, path: str, body: dict | None = None, token: str | None = None
) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", "replace")[:200]}
        return exc.code, payload


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


MEDIAPIPE_33 = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
    "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
    "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
)


def neutral_pose() -> list[dict]:
    anchors = {
        "nose": (0.50, 0.18, 0.0),
        "left_eye": (0.47, 0.22, 0.0),
        "right_eye": (0.53, 0.22, 0.0),
        "left_ear": (0.44, 0.26, 0.0),
        "right_ear": (0.56, 0.26, 0.0),
        "left_shoulder": (0.40, 0.42, 0.0),
        "right_shoulder": (0.60, 0.42, 0.0),
        "left_hip": (0.43, 0.70, 0.0),
        "right_hip": (0.57, 0.70, 0.0),
    }
    return [
        {"name": name, "x": anchors.get(name, (0.5, 0.5, 0.0))[0],
         "y": anchors.get(name, (0.5, 0.5, 0.0))[1],
         "z": anchors.get(name, (0.5, 0.5, 0.0))[2],
         "visibility": 0.95 if name in MEDIAPIPE_33[:13] else 0.2}
        for name in MEDIAPIPE_33
    ]


def main() -> None:
    health_code, health = call("GET", "/health/live")
    check(health_code == 200 and health.get("status") == "ok", f"/health/live -> {health_code}")
    print(f"/health/live          {health_code} {health.get('version')}")

    ready_code, ready = call("GET", "/health/ready")
    print(f"/health/ready         {ready_code} {ready.get('status')}")
    check(ready_code == 200, "/health/ready is not 200; fix dependencies first")

    capabilities = call("GET", "/health/capabilities")[1]
    print(f"/health/capabilities  store_backend={capabilities.get('store_backend')} "
          f"cloud_provider={capabilities.get('cloud_provider')}")

    email = f"smoke-{int(time.time())}@riseloop.app"
    register_code, register = call(
        "POST", "/auth/register", {"email": email, "password": "riseloop-test-1"}
    )
    check(register_code == 201, f"/auth/register -> {register_code}")
    token = register["access_token"]
    print(f"/auth/register        {register_code} {email}")

    assessment_code, assessment = call(
        "POST",
        "/assessment",
        {
            "body_parts": ["neck", "shoulder"],
            "sedentary_minutes": 480,
            "available_minutes": 10,
            "pain_score": 2,
            "acute_discomfort": False,
        },
        token,
    )
    check(assessment_code == 200, f"/assessment -> {assessment_code}")
    print(f"/assessment           {assessment_code} state={assessment['initial_state']} "
          f"risk={assessment['risk_level']}")

    heartbeat_code, heartbeat = call(
        "POST",
        "/sitting/heartbeat",
        {"sitting_minutes": 50, "threshold_minutes": 45, "force": True},
        token,
    )
    check(heartbeat_code == 200, f"/sitting/heartbeat -> {heartbeat_code}")
    check(heartbeat["triggered"] is True, f"heartbeat not triggered: {heartbeat['reason']}")
    action = heartbeat["action"]
    print(f"/sitting/heartbeat    {heartbeat_code} triggered={heartbeat['triggered']} "
          f"action={action['id']} ({action['duration_minutes']} min)")

    current_code, current = call("GET", "/intervention/current", token=token)
    check(current_code == 200 and current["id"] == action["id"], "/intervention/current mismatch")
    print(f"/intervention/current {current_code} {current['id']}")

    feedback_code, feedback = call(
        "POST",
        "/intervention/feedback",
        {
            "action_id": action["id"],
            "completion": "completed",
            "feeling": "better",
            "pain_score": 2,
        },
        token,
    )
    check(feedback_code == 200, f"/intervention/feedback -> {feedback_code}")
    check(feedback["transition_type"] in {"upgrade", "hold", "degrade", "rollback", "short_circuit"},
          f"unexpected transition: {feedback['transition_type']}")
    print(f"/intervention/feedback {feedback_code} {feedback['from_state']} -> {feedback['to_state']} "
          f"{feedback['transition_type']} ({feedback['reason']})")

    pose = neutral_pose()
    baseline_code, baseline = call(
        "POST", "/posture/baseline", {"frames": [pose, pose, pose]}, token
    )
    check(baseline_code == 200, f"/posture/baseline -> {baseline_code} {baseline}")
    fields = baseline.get("baseline", {})
    check({"neck_ratio", "head_scale", "ear_mid_offset"} <= set(fields),
          f"baseline fields incomplete: {sorted(fields)}")
    print(f"/posture/baseline     {baseline_code} frames={baseline.get('frames')} "
          f"head_scale={fields.get('head_scale')}")

    infer_code, infer = call_allow_error(
        "POST",
        "/posture/infer",
        {
            "keypoints": pose,
            "baseline": fields,
            "source": "mediapipe-pose-33",
            "sitting_minutes": 10,
            "daily_sitting_minutes": 30,
            "minutes_since_last_break": 5,
            "pain_score": 0,
            "body_parts": ["neck", "shoulder"],
            "plan": "standard",
        },
        token,
    )
    if infer_code == 200:
        check(infer.get("source") in {"huawei", "mock"},
              f"unexpected posture source: {infer.get('source')}")
        print(f"/posture/infer        {infer_code} posture={infer.get('posture')} "
              f"source={infer.get('source')} confidence={infer.get('confidence')}")
        if infer.get("source") == "mock":
            print("WARN: /posture/infer is still mock; ModelArts endpoint is not active")
    elif infer_code == 503:
        detail = infer.get("detail", {})
        check(detail.get("error") == "modelarts_unavailable",
              f"/posture/infer 503 but unexpected detail: {detail}")
        print("/posture/infer        503 modelarts_unavailable (endpoint not configured/down)")
    else:
        check(False, f"/posture/infer -> {infer_code} {infer}")
    print("OK")


if __name__ == "__main__":
    main()
