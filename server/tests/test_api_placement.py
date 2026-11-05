from kaskade import ai, placement


def test_content_has_tasks_without_answers(client):
    c = client.get("/api/placement/content").json()
    assert len(c["reading"]) == 2 and c["ai"] is False
    assert "correct" not in c["reading"][0]["questions"][0]
    assert c["writing"]["points"] and len(c["speaking"]) == 3


def test_placement_lifecycle(client):
    assert client.get("/api/placement/current").json() is None
    p = client.post("/api/placement").json()
    assert p["status"] == "in_progress" and p["state"]["step"] == "wortschatz"

    state = {"step": "lesen", "vocab": {"result": {"estimate": 1800, "coreKnown": 1400, "coreShare": 0.7}}}
    assert client.put(f"/api/placement/{p['id']}", json={"state": state}).json() == {"ok": True}
    cur = client.get("/api/placement/current").json()
    assert cur["id"] == p["id"] and cur["state"]["step"] == "lesen"  # resumable

    done = client.post(f"/api/placement/{p['id']}/finish").json()
    assert done["status"] == "done" and done["result"]["words"] == 1800
    assert client.get("/api/status").json()["phase"] == "2A"
    # finished placements can't be edited
    assert client.put(f"/api/placement/{p['id']}", json={"state": {}}).status_code == 409


def test_new_placement_abandons_open_one(client):
    a = client.post("/api/placement").json()
    b = client.post("/api/placement").json()
    assert client.get("/api/placement/current").json()["id"] == b["id"]
    assert a["id"] != b["id"]


def test_unknown_placement_is_404(client):
    assert client.post("/api/placement/99/finish").status_code == 404


def test_score_reading_endpoint(client):
    key = {q["id"]: q["correct"] for t in placement.reading_texts()["texts"] for q in t["questions"]}
    r = client.post("/api/placement/reading/score", json={"answers": key}).json()
    assert r["level"] == "B2" and len(r["review"]) == 10


def test_writing_saved_without_grade_when_no_key(client):
    wid = placement.tasks()["writing"]["id"]
    r = client.post("/api/writing", json={"context": "placement:1", "promptId": wid, "text": "Liebe Jana, ich bin umgezogen."})
    assert r.status_code == 200
    assert r.json()["grade"] is None and r.json()["ai"] is False
    assert client.get("/api/writing?context=placement:1").json()[0]["text"].startswith("Liebe Jana")


def test_writing_graded_when_key_present(client, monkeypatch):
    monkeypatch.setattr(ai, "grade_writing", lambda task, text: {"level": "B1", "summary": "Gut."})
    wid = placement.tasks()["writing"]["id"]
    r = client.post("/api/writing", json={"context": "x", "promptId": wid, "text": "Liebe Jana"}).json()
    assert r["grade"]["level"] == "B1"


def test_writing_errors(client):
    assert client.post("/api/writing", json={"context": "x", "promptId": "nope", "text": "a"}).status_code == 404
    wid = placement.tasks()["writing"]["id"]
    assert client.post("/api/writing", json={"context": "x", "promptId": wid, "text": "  "}).status_code == 422


def test_recording_upload_and_download(client):
    r = client.post("/api/recordings", files={"audio": ("a.webm", b"OggSfake", "audio/webm;codecs=opus")},
                    data={"context": "placement:1:sp1"})
    assert r.status_code == 200
    rid = r.json()["id"]
    f = client.get(f"/api/recordings/{rid}/file")
    assert f.status_code == 200 and f.content == b"OggSfake"


def test_recording_rejects_non_audio(client):
    r = client.post("/api/recordings", files={"audio": ("a.exe", b"MZ", "application/octet-stream")},
                    data={"context": "x"})
    assert r.status_code == 422
    assert client.get("/api/recordings/42/file").status_code == 404


def test_ai_grade_is_none_without_key():
    assert ai.grade_writing({"points": []}, "Hallo") is None


def test_ai_parse_json_tolerates_prose():
    assert ai.parse_json('Hier: {"level": "B1"} fertig')["level"] == "B1"
    assert ai.parse_json("kein json") is None
