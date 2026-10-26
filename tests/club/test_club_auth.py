from fastapi.testclient import TestClient

from tests.conftest import BOCA_HEADERS


def test_missing_auth_header(client: TestClient) -> None:
    res = client.get("/api/v1/socios")
    assert res.status_code == 401
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_invalid_bearer_format(client: TestClient) -> None:
    res = client.get("/api/v1/socios", headers={"Authorization": "Token 12345"})
    assert res.status_code == 401
    body = res.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_invalid_token(client: TestClient) -> None:
    res = client.get(
        "/api/v1/socios", headers={"Authorization": "Bearer invalid_secret_token"}
    )
    assert res.status_code == 401
    body = res.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_valid_token_authenticated(client: TestClient) -> None:
    res = client.get("/api/v1/socios", headers=BOCA_HEADERS)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
