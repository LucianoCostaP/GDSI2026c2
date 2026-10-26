from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "version" in data


def test_healthz_liveness(client: TestClient) -> None:
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_readiness(client: TestClient) -> None:
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}
