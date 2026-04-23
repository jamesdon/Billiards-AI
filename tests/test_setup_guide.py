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
    assert "Text size" in r.text
    assert 'name="text-size"' in r.text
    assert "sidebar-resize" in r.text

    r = client.get("/api/setup/context")
    assert r.status_code == 200
    data = r.json()
    assert "project_root" in data
    assert isinstance(data["project_root"], str)
    assert "launch_enabled" in data
    assert data["launch_enabled"] is False
    assert isinstance(data.get("markdown_installed"), bool)
    assert data.get("api_default_port") == 8780
    assert isinstance(data.get("api_port"), int)
    assert 1 <= int(data.get("api_port", 0)) <= 65535

    r = client.get("/api/setup/steps")
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert len(steps) >= 3
    assert any(s["id"] == "phase3" for s in steps)
    p3 = next(s for s in steps if s["id"] == "phase3")
    assert p3["checklist"][0].get("verify")
    assert p3["checklist"][1].get("verify_actions")
    assert p3["checklist"][1]["verify_actions"][0]["label"] == "Open MJPEG overlay"

    r = client.get("/api/setup/doc", params={"path": "README.md"})
    assert r.status_code == 200
    assert "Setup wizard" in r.text or "Billiards-AI" in r.text
    assert "md-doc-link" in r.text
    assert "billiards-setup-text-size" in r.text
    assert "URLSearchParams" in r.text
    r2 = client.get("/api/setup/doc", params={"path": "README.md", "textSize": "large"})
    assert r2.status_code == 200
    assert "textSize" in r2.text
    assert 'data-text-size="large"' in r2.text
    assert "28px" in r2.text
    # HTML `href` must use `&amp;` for query `&` or Safari can truncate the URL (dropping `textSize`).
    if "href=" in r2.text and "/api/setup/doc?" in r2.text:
        assert "&amp;textSize=" in r2.text
    assert "setup_text_size" in (r2.headers.get("set-cookie") or "").lower()

    r_cookie = client.get(
        "/api/setup/doc",
        params={"path": "README.md"},
        headers={"Cookie": "setup_text_size=large"},
    )
    assert r_cookie.status_code == 200
    assert 'data-text-size="large"' in r_cookie.text
    assert "textSize=large" in r_cookie.text

    r3 = client.get("/api/setup/steps")
    assert r3.status_code == 200
    steps2 = r3.json()["steps"]
    assert any(
        any((isinstance(it, dict) and bool(it.get("verify"))) for it in (s.get("checklist") or []))
        for s in steps2
    )

    r = client.get("/api/setup/doc", params={"path": "docs/../../../etc/passwd"})
    assert r.status_code == 400

    r = client.get("/api/setup/progress")
    assert r.status_code == 200
    assert "completed" in r.json()

    r = client.get("/api/setup/edge-health", params={"port": 59999})
    assert r.status_code == 200
    eh = r.json()
    assert eh.get("port") == 59999
    assert "ok" in eh
    assert eh.get("ok") is False

    r = client.put(
        "/api/setup/progress",
        json={
            "completed": {"overview": True},
            "checklist_done": {},
            "notes": {},
            "last_step_id": "overview",
            "mjpeg_port": 8080,
        },
    )
    assert r.status_code == 200
    assert r.json()["completed"].get("overview") is True

    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/setup"
