"""The frontend may be opened as localhost or as 127.0.0.1 (different origins for the browser)."""
import pytest


def _preflight(client, origin):
    return client.options(
        "/api/documents",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173", "http://[::1]:5173"],
)
def test_loopback_origins_are_allowed(client, origin):
    resp = _preflight(client, origin)
    assert resp.status_code == 200 and resp.headers["access-control-allow-origin"] == origin
    assert client.get("/api/documents", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost.evil.example:5173", "http://127.0.0.1.evil.example"])
def test_other_origins_are_not(client, origin):
    resp = _preflight(client, origin)
    assert "access-control-allow-origin" not in resp.headers
