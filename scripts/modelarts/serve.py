"""Minimal local HTTP wrapper around the ModelArts service class.

Purpose: exercise exactly the same ``_preprocess`` / ``_inference`` /
``_postprocess`` chain as ModelArts before uploading the package.

    python scripts/modelarts/serve.py --artifacts scripts/modelarts/artifacts/v1

Endpoints:
    GET  /health
    POST /predict   {"keypoints": [...33...], "features": {...}}

This server is for local integration tests only; it is not deployed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0] or os.getcwd()) == _SCRIPT_DIR:
    sys.path[0] = _SCRIPT_DIR
else:
    sys.path.insert(0, _SCRIPT_DIR)

from customize_service import FEATURE_SPEC_VERSION, MODELARTS_BASE, Model

logger = logging.getLogger("posture_serve")
MAX_BODY_BYTES = 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "PostureServe/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Suppress the default request-line log; the service logs the safe fields.
        logger.debug("http %s", format % args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "not_found", "message": "unknown path"}})
            return
        service: Model = self.server.service  # type: ignore[attr-defined]
        self._send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "model": service.model_name,
                "contract_version": service.meta.get("contract_version"),
                "feature_spec_version": FEATURE_SPEC_VERSION,
                "input_version": service.input_version,
                "input_dim": service.input_dim,
                "requests": service.request_count,
                "errors": service.error_count,
                "feature_recompute_count": service.recompute_count,
                "modelarts_base": MODELARTS_BASE,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/predict":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "not_found", "message": "unknown path"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"code": "empty_body", "message": "JSON body required"}})
            return
        if length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": {"code": "body_too_large", "message": "body exceeds 1 MiB"}})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"code": "invalid_json", "message": "body must be valid JSON"}})
            return
        service: Model = self.server.service  # type: ignore[attr-defined]
        response = service.predict(payload)
        status = HTTPStatus.BAD_REQUEST if "error" in response else HTTPStatus.OK
        self._send_json(status, response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "v1",
    )
    parser.add_argument("--model", default=None, help="override model.pt path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log-file", default=None, help="optional local JSONL-safe log file")
    args = parser.parse_args(argv)

    model_path = args.model or str(args.artifacts / "model.pt")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    service = Model("posture-v1", model_path)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.service = service  # type: ignore[attr-defined]
    logger.info(
        "serving host=%s port=%s input_version=%s",
        args.host,
        args.port,
        service.input_version,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
