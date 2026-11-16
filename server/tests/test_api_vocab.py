def test_get_test_returns_items(client):
    r = client.get("/api/vocab/test")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 100
    assert {"word", "band"} <= set(items[0])


def test_submit_result_and_read_latest(client):
    items = client.get("/api/vocab/test").json()["items"]
    answers = [{**i, "yes": i["band"] in ("b1", "b2")} for i in items]
    r = client.post("/api/vocab/result", json={"answers": answers})
    assert r.status_code == 200
    body = r.json()
    assert body["falseAlarmRate"] == 0
    assert body["estimate"] > 0
    assert body["coreShare"] > 0.5

    latest = client.get("/api/vocab/latest").json()
    assert latest["id"] == body["id"]
    assert latest["estimate"] == body["estimate"]


def test_latest_is_null_without_tests(client):
    assert client.get("/api/vocab/latest").json() is None


def test_submit_rejects_unknown_band(client):
    r = client.post("/api/vocab/result", json={"answers": [{"word": "x", "band": "zz", "yes": True}]})
    assert r.status_code == 422


def test_submit_rejects_empty(client):
    assert client.post("/api/vocab/result", json={"answers": []}).status_code == 422
