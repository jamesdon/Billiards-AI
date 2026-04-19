"""Setup wizard API smoke tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import create_app


def test_setup_page_and_api():
    app = create_app()
    client = TestClient(app)

    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 200
    assert "Setup guide" in r.text

    r = client.get("/api/setup/context")
    assert r.status_code == 200
    data = r.json()
    assert "project_root" in data
    assert isinstance(data["project_root"], str)

    r = client.get("/api/setup/steps")
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert len(steps) >= 3
    assert any(s["id"] == "phase3" for s in steps)

    r = client.get("/api/setup/progress")
    assert r.status_code == 200
    assert "completed" in r.json()

    r = client.put(
        "/api/setup/progress",
        json={"completed": {"overview": True}, "checklist_done": {}, "notes": {}, "last_step_id": "overview"},
    )
    assert r.status_code == 200
    assert r.json()["completed"].get("overview") is True

    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/setup"
