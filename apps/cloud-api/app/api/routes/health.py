from fastapi import APIRouter, Request, Response

from ...schemas.health import (
    CapabilitiesResponse,
    DependencyResponse,
    LiveResponse,
    RateLimitCapability,
    ReadinessResponse,
)

router = APIRouter(prefix="/health", tags=["health"])

REQUIRED_SERVICES = frozenset({"rds", "redis"})


@router.get("/live", response_model=LiveResponse)
async def live(request: Request) -> LiveResponse:
    settings = request.app.state.settings
    return LiveResponse(status="ok", service=settings.app_name, version=settings.version)


@router.get("/deps", response_model=DependencyResponse)
async def dependencies(request: Request) -> DependencyResponse:
    statuses = await request.app.state.cloud.check_all()
    return DependencyResponse(dependencies=statuses)


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(request: Request) -> CapabilitiesResponse:
    settings = request.app.state.settings
    statuses = await request.app.state.cloud.check_all()
    return CapabilitiesResponse(
        env=settings.env,
        version=settings.version,
        store_backend=settings.store_backend,
        cloud_provider=settings.cloud_provider,
        dependencies=statuses,
        rate_limit=RateLimitCapability(
            requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
            auth_requests=settings.rate_limit_auth_requests,
        ),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    statuses = await request.app.state.cloud.check_all()
    is_ready = all(
        status.reachable is True
        for status in statuses
        if status.name in REQUIRED_SERVICES
    )
    if not is_ready:
        response.status_code = 503
    return ReadinessResponse(
        status="ready" if is_ready else "degraded",
        dependencies=statuses,
    )