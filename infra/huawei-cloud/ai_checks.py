"""AI 建议链路检查：姿态推理 → BRLI → 推荐动作 → 问答 → 周复盘 → 安全短路。

用法：
    python ai_checks.py http://<host>:8000

只依赖标准库。会注册一个临时账号并写入测试数据；不删除数据，测试环境使用。
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"

MEDIAPIPE_33 = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
    "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
    "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
)


def call(method, path, body=None, token=None, expect=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            payload = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", "replace")[:200]}
    if expect is not None and status != expect:
        raise SystemExit(f"FAIL {method} {path} -> {status}: {json.dumps(payload, ensure_ascii=False)[:400]}")
    return status, payload


def check(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def neutral_pose():
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
        {
            "name": name,
            "x": anchors.get(name, (0.5, 0.5, 0.0))[0],
            "y": anchors.get(name, (0.5, 0.5, 0.0))[1],
            "z": anchors.get(name, (0.5, 0.5, 0.0))[2],
            "visibility": 0.95 if name in MEDIAPIPE_33[:13] else 0.2,
        }
        for name in MEDIAPIPE_33
    ]


def main():
    _, live = call("GET", "/health/live", expect=200)
    check(live.get("status") == "ok", "/health/live not ok")
    _, ready = call("GET", "/health/ready", expect=200)
    check(ready.get("status") == "ready", f"/health/ready degraded: {ready}")
    _, caps = call("GET", "/health/capabilities", expect=200)
    check(caps.get("cloud_provider") == "huawei", f"cloud_provider={caps.get('cloud_provider')}, expected huawei")
    check(caps.get("store_backend") == "sql", f"store_backend={caps.get('store_backend')}, expected sql")
    modelarts = next((d for d in caps.get("dependencies", []) if d.get("name") == "modelarts"), {})
    check(modelarts.get("configured") is True, "modelarts not configured")
    print(f"[1] health              ready, provider={caps['cloud_provider']}, store={caps['store_backend']}")

    email = f"ai-check-{int(time.time())}@riseloop.app"
    _, auth = call(
        "POST", "/auth/register",
        {"email": email, "password": "riseloop-ai-check-1"}, expect=201,
    )
    token = auth["access_token"]
    print(f"[2] auth                {email}")

    _, assessment = call(
        "POST", "/assessment",
        {
            "body_parts": ["neck", "shoulder"],
            "sedentary_minutes": 480,
            "available_minutes": 10,
            "pain_score": 3,
            "acute_discomfort": False,
        },
        token, expect=200,
    )
    print(f"[3] assessment          state={assessment['initial_state']} risk={assessment['risk_level']}")

    _, heartbeat = call(
        "POST", "/sitting/heartbeat",
        {"sitting_minutes": 50, "threshold_minutes": 45, "force": True},
        token, expect=200,
    )
    check(heartbeat.get("triggered") is True, f"heartbeat not triggered: {heartbeat.get('reason')}")
    actions = heartbeat.get("actions") or [heartbeat.get("action")]
    actions = [a for a in actions if a]
    check(actions, "heartbeat returned no action")
    action_id = actions[0]["id"]
    print(f"[4] heartbeat           triggered, actions={len(actions)}, first={action_id} ({actions[0]['duration_minutes']} min)")

    pose = neutral_pose()
    _, baseline = call("POST", "/posture/baseline", {"frames": [pose, pose, pose]}, token, expect=200)
    check(baseline.get("baseline"), "baseline empty")
    fields = baseline["baseline"]
    print(f"[5] baseline            frames={baseline.get('frames')} head_scale={fields.get('head_scale')}")

    status, infer = call(
        "POST", "/posture/infer",
        {
            "keypoints": pose,
            "baseline": fields,
            "source": "mediapipe-pose-33",
            "sitting_minutes": 30,
            "daily_sitting_minutes": 240,
            "minutes_since_last_break": 30,
            "pain_score": 1,
            "body_parts": ["neck", "shoulder"],
            "plan": "standard",
        },
        token,
    )
    if status == 503:
        raise SystemExit("FAIL: /posture/infer 503 (ModelArts 未运行、endpoint 变更或证书校验失败)")
    check(status == 200, f"/posture/infer -> {status}: {infer}")
    check(infer.get("source") == "huawei", f"posture source={infer.get('source')}, expected huawei")
    risk = infer.get("risk") or {}
    check(risk.get("brli") is not None, "infer.risk.brli missing")
    print(
        f"[6] posture infer       posture={infer.get('posture')} conf={infer.get('confidence')} "
        f"source={infer.get('source')} latency={infer.get('latency_ms')}ms brli={risk.get('brli')}"
    )

    _, risk_resp = call(
        "POST", "/posture/risk",
        {
            "posture_class": "forward_head",
            "confidence": 0.9,
            "deviation_deg": 12,
            "posture_duration_minutes": 6,
            "sitting_minutes": 60,
            "daily_sitting_minutes": 480,
            "minutes_since_last_break": 60,
            "pain_score": 5,
            "fatigue_score": 5,
            "body_parts": ["neck", "shoulder"],
            "plan": "standard",
        },
        token, expect=200,
    )
    check(risk_resp.get("brli", 0) >= 0.35, f"brli too low: {risk_resp.get('brli')}")
    check(risk_resp.get("recommended_plan") != "maintain", f"plan={risk_resp.get('recommended_plan')}")
    check(len(risk_resp.get("actions") or []) >= 1, "risk returned no actions")
    check(len(risk_resp.get("factors") or []) == 4, "risk factors != 4")
    check(len(risk_resp.get("citations") or []) >= 1, "risk citations empty")
    print(
        f"[7] risk suggestion     brli={risk_resp['brli']} level={risk_resp['risk_level']} "
        f"plan={risk_resp['recommended_plan']} actions={len(risk_resp['actions'])} "
        f"citations={len(risk_resp['citations'])}"
    )

    _, qa = call(
        "POST", "/qa/ask",
        {"question": "开会太久颈肩紧张怎么办", "state": "S1", "body_parts": ["neck", "shoulder"]},
        token, expect=200,
    )
    check(qa.get("citations"), "qa citations empty for a known question")
    check("资料中没有" not in qa.get("answer", ""), "known question fell back to no-match")
    print(f"[8] qa hit              citations={qa['citations']} answer={qa['answer'][:40]}")

    _, qa_miss = call(
        "POST", "/qa/ask", {"question": "今天天气怎么样", "state": "S1"}, token, expect=200
    )
    check(qa_miss.get("citations") == [], f"unexpected citations: {qa_miss.get('citations')}")
    print(f"[9] qa miss             no citations, answer={qa_miss['answer'][:40]}")

    _, feedback = call(
        "POST", "/intervention/feedback",
        {
            "action_id": action_id,
            "completion": "completed",
            "feeling": "better",
            "pain_score": 2,
        },
        token, expect=200,
    )
    check(feedback.get("transition_type"), "feedback transition_type missing")
    print(
        f"[10] feedback           {feedback['from_state']} -> {feedback['to_state']} "
        f"{feedback['transition_type']}"
    )

    _, weekly = call("GET", "/review/weekly?days=7", token=token, expect=200)
    check(weekly.get("suggestions"), "weekly suggestions empty")
    check(weekly["interventions"]["total"] >= 1, "weekly did not consume intervention log")
    check(weekly["posture"]["samples"] >= 1, "weekly did not consume posture summary")
    print(
        f"[11] weekly review      interventions={weekly['interventions']['total']} "
        f"posture_samples={weekly['posture']['samples']} "
        f"suggestions={len(weekly['suggestions'])} highlights={len(weekly['highlights'])}"
    )

    status, short = call(
        "POST", "/intervention/feedback",
        {
            "action_id": action_id,
            "completion": "completed",
            "feeling": "worse",
            "pain_score": 8,
            "red_flags": ["radiating_pain"],
        },
        token,
    )
    check(status == 403, f"red flag feedback expected 403, got {status}: {short}")
    print("[12] safety short      403, 推荐被拦截")

    print("OK: AI 建议链路全部通过")


if __name__ == "__main__":
    main()
