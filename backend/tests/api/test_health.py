"""Smoke test for /api/health."""

from __future__ import annotations


def test_health_returns_ok(api_client):
    resp = api_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
