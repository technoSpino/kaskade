from kaskade import db


def test_status_without_placement_has_no_phase(client):
    body = client.get("/api/status").json()
    assert body["phase"] is None
    assert body["name"] == "Matt"


def test_status_reports_saved_phase(client):
    db.set_setting("phase", "2A")
    assert client.get("/api/status").json()["phase"] == "2A"


def test_theme_setting(client):
    assert client.get("/api/status").json()["theme"] is None
    assert client.put("/api/settings/theme", json={"theme": "papier"}).json() == {"theme": "papier"}
    assert client.get("/api/status").json()["theme"] == "papier"
    assert client.put("/api/settings/theme", json={"theme": "neon"}).status_code == 422


def test_unknown_api_route_is_404(client):
    assert client.get("/api/nope").status_code == 404
