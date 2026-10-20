def test_next_review_known_undo_flow(client):
    nxt = client.get("/api/cards/next").json()
    card = nxt["card"]
    assert card["isNew"] and card["sentence"] and set(nxt["intervals"]) == {"1", "2", "3", "4"}
    assert nxt["counts"]["new"] == 20

    r = client.post(f"/api/cards/{card['id']}/review", json={"rating": 3})
    assert r.status_code == 200 and r.json()["status"] == "learning"

    second = client.get("/api/cards/next").json()["card"]
    assert second["id"] != card["id"]
    assert client.post(f"/api/cards/{second['id']}/known").json()["status"] == "known"
    assert client.post("/api/cards/undo").json() == {"id": second["id"]}

    stats = client.get("/api/cards/stats").json()
    assert stats["learning"] == 1 and stats["known"] == 0 and stats["newPerDay"] == 20


def test_review_errors(client):
    assert client.post("/api/cards/core:9999/review", json={"rating": 3}).status_code == 404
    first = client.get("/api/cards/next").json()["card"]["id"]
    assert client.post(f"/api/cards/{first}/review", json={"rating": 7}).status_code == 422
    client.post(f"/api/cards/{first}/known")
    assert client.post(f"/api/cards/{first}/review", json={"rating": 3}).status_code == 409
    assert client.post("/api/cards/core:9999/known").status_code == 404


def test_undo_with_nothing_is_409(client):
    assert client.post("/api/cards/undo").status_code == 409


def test_settings_change_new_per_day(client):
    assert client.put("/api/cards/settings", json={"newPerDay": 5}).json() == {"newPerDay": 5}
    assert client.get("/api/cards/next").json()["counts"]["new"] == 5
    assert client.put("/api/cards/settings", json={"newPerDay": -1}).status_code == 422
