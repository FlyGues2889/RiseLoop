from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_client(**overrides) -> TestClient:
    settings = Settings(_env_file=None, **overrides)
    return TestClient(create_app(settings))


def test_live_returns_service_metadata():
    with make_client() as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "Rise Loop Cloud API"
        assert data["version"] == "0.1.0"


def test_ready_in_mock_mode_reports_all_dependencies():
    with make_client() as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        names = {item["name"] for item in data["dependencies"]}
        assert names == {"rds", "redis", "codearts", "obs", "kms"}
        assert all(item["provider"] == "mock" for item in data["dependencies"])


def test_ready_with_unconfigured_huawei_services_is_degraded():
    with make_client(cloud_provider="huawei") as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        by_name = {item["name"]: item for item in data["dependencies"]}
        assert by_name["rds"]["configured"] is False
        assert by_name["redis"]["configured"] is False
        assert by_name["codearts"]["configured"] is False


def test_dependency_report_never_leaks_credentials():
    with make_client(
        cloud_provider="huawei",
        rds_password="rds-secret-value",
        redis_password="redis-secret-value",
        codearts_api_key="codearts-secret-value",
        obs_sk="obs-secret-value",
        kms_sk="kms-secret-value",
    ) as client:
        response = client.get("/health/deps")
        body = response.text
        assert "rds-secret-value" not in body
        assert "redis-secret-value" not in body
        assert "codearts-secret-value" not in body
        assert "obs-secret-value" not in body
        assert "kms-secret-value" not in body


def test_huawei_mode_with_rds_dsn_is_configured():
    with make_client(
        cloud_provider="huawei",
        rds_dsn="postgresql+asyncpg://user:pass@127.0.0.1:1/riseloop",
    ) as client:
        response = client.get("/health/deps")
        by_name = {item["name"]: item for item in response.json()["dependencies"]}
        assert by_name["rds"]["configured"] is True
        assert by_name["rds"]["reachable"] is False


def test_root_exposes_runtime_mode():
    with make_client(env="dev", cloud_provider="mock") as client:
        data = client.get("/").json()
        assert data["env"] == "dev"
        assert data["cloud_provider"] == "mock"