"""端到端冒烟：注册 → 评估 → 久坐心跳 → 当前干预 → 反馈。

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
        raise SystemExit(f"{method} {path} -> {exc.code} {exc.read().decode('utf-8', 'replace')}")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


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
    print("OK")


if __name__ == "__main__":
    main()
