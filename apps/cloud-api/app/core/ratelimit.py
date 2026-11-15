"""接口限流：内存滑动窗口，按登录态 token 指纹或来源 IP 计数。

不做分布式计数：单实例够用，真要横向扩容时把 _hits 换成 DCS 的 INCR 即可，
本文件对上层只暴露一个中间件，替换实现不影响路由。
"""

import hashlib
import time
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

SKIP_PATHS = frozenset(
    {"/", "/docs", "/redoc", "/openapi.json", "/health/live", "/health/ready", "/health/deps"}
)
AUTH_PATHS = frozenset({"/auth/login", "/auth/register", "/auth/refresh"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        limit: int = 120,
        window: int = 60,
        auth_limit: int = 10,
    ) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = float(window)
        self.auth_limit = auth_limit
        self._hits: dict[str, deque[float]] = {}

    def _bucket(self, request: Request) -> tuple[str, int] | None:
        path = request.url.path
        if path in SKIP_PATHS or request.method == "OPTIONS":
            return None
        is_auth = path in AUTH_PATHS
        authorization = request.headers.get("authorization") or ""
        if authorization:
            fingerprint = hashlib.sha256(authorization.encode()).hexdigest()[:16]
            identity = "token:" + fingerprint
        else:
            host = request.client.host if request.client else "unknown"
            identity = "ip:" + host
        prefix = "auth:" if is_auth else "api:"
        return prefix + identity, (self.auth_limit if is_auth else self.limit)

    async def dispatch(self, request: Request, call_next):
        bucket = self._bucket(request)
        if bucket is None:
            return await call_next(request)
        key, capacity = bucket
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= capacity:
            retry_after = max(1, int(self.window - (now - hits[0])) + 1)
            return JSONResponse(
                status_code=429,
                content={"detail": "rate_limited"},
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        if len(self._hits) > 4096:
            self._hits = {
                k: v for k, v in self._hits.items() if v and now - v[-1] <= self.window
            }
        return await call_next(request)
