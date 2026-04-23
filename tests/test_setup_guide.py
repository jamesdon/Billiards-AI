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
    assert "Score Keeper" in r.text
    assert "sk-embed" in r.text
    assert "main-wrap" in r.text
    assert "id=\"content\"" in r.text
    assert "API BACKEND_PORT" in r.text
    assert "api-port-shown" in r.text
    assert "api-health-lamp" in r.text
    assert "edge-port-lamp" in r.text
    assert "MJPEG port: default 8001" in r.text
    assert "Only ports 8001" in r.text
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
    assert data.get("api_default_port") == 8000
    assert data.get("mjpeg_default_port") == 8001
    assert isinstance(data.get("api_port"), int)
    assert 1 <= int(data.get("api_port", 0)) <= 65535
    assert "public_http_base" in data
    assert isinstance(data["public_http_base"], str)
    assert data["public_http_base"].startswith("http://")
    assert "public_http_base_source" in data
    assert data["public_http_base_source"] in ("host_header", "lan_guess", "loopback")
    assert "scorekeeper_url" in data
    sk_url = data["scorekeeper_url"]
    assert isinstance(sk_url, str)
    assert sk_url.endswith("/scorekeeper")
    assert data["public_http_base"] in sk_url

    r_sk = client.get("/scorekeeper", follow_redirects=False)
    assert r_sk.status_code == 200
    assert "Score Keeper" in r_sk.text
    assert "sk-root" in r_sk.text or "sk-teams" in r_sk.text
    assert "billiards-setup-text-size" in r_sk.text

    r = client.get("/api/setup/steps")
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert len(steps) >= 3
    assert any(s["id"] == "phase3" for s in steps)
    p4 = next(s for s in steps if s["id"] == "phase4")
    assert len(p4["checklist"]) == 1
    assert "display" in (p4["checklist"][0].get("item") or "").lower()
    p4v = p4["checklist"][0].get("verify") or ""
    assert "GET /profiles" in p4v
    assert "Score Keeper" in p4v
    assert "curl" in p4v
    assert "Phase A" in p4v and "Phase C" in p4v and "Phase D" in p4v
    assert (p4.get("doc_refs") or []) == []
    va4 = p4["checklist"][0].get("verify_actions") or []
    assert len(va4) == 4
    assert va4[0].get("label") == "Open GET /profiles"
    assert "href_template" in va4[0]
    assert va4[-1].get("action") == "bootstrap_minimal_profiles"
    p4links = p4.get("links") or []
    assert any(
        (isinstance(x, dict) and x.get("label") == "GET /profiles (JSON)") for x in p4links
    )
    assert any(
        (isinstance(x, dict) and "Score Keeper" in (x.get("label") or "")) for x in p4links
    )
    p3 = next(s for s in steps if s["id"] == "phase3")
    assert len(p3["checklist"]) == 1
    v0 = p3["checklist"][0].get("verify") or ""
    assert "edge.main" in v0 and "phase3" not in v0.lower()
    assert "show-track-debug-overlay" in v0
    assert "track" in v0.lower()
    assert p3["checklist"][0].get("verify_actions")
    assert p3["checklist"][0]["verify_actions"][0]["label"] == "Open MJPEG overlay"
    assert p3["checklist"][0]["verify_actions"][1]["label"] == "Open edge /health"
    assert p3.get("links") == []

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
    # If a doc `href` includes `textSize=`, the `&` before it must be `&amp;` in HTML (Safari).
    if 'href="/api/setup/doc?' in r2.text and "textSize=" in r2.text:
        assert "&amp;textSize=" in r2.text
    assert "setup_text_size" in (r2.headers.get("set-cookie") or "").lower()

    r_cookie = client.get(
        "/api/setup/doc",
        params={"path": "README.md"},
        headers={"Cookie": "setup_text_size=large"},
    )
    assert r_cookie.status_code == 200
    assert 'data-text-size="large"' in r_cookie.text

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
    assert eh.get("reason") == "connection_refused"

    r = client.get("/api/setup/profiles-status")
    assert r.status_code == 200
    ps = r.json()
    assert "player_count" in ps and "stick_count" in ps
    assert "nonempty" in ps
    assert "identities_path_resolved" in ps

    r = client.post("/api/setup/bootstrap-minimal-profiles")
    assert r.status_code == 200
    bj = r.json()
    assert "ok" in bj
    if bj.get("ok"):
        assert "setup-smoke-1" in (bj.get("message") or "")
    else:
        assert "already" in (bj.get("detail") or "").lower()

    r = client.put(
        "/api/setup/progress",
        json={
            "completed": {"overview": True},
            "checklist_done": {},
            "notes": {},
            "last_step_id": "overview",
            "mjpeg_port": 8001,
        },
    )
    assert r.status_code == 200
    assert r.json()["completed"].get("overview") is True

    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/setup"
