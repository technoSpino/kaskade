from kaskade import practice, tts


def key(item):
    return {q["id"]: q["correct"] for q in (item.get("questions") or item.get("situations"))}


def test_overview_lists_modules_and_readiness(client):
    o = client.get("/api/practice").json()
    assert len(o["lesen"]) == 4 and len(o["hoeren"]) == 4 and len(o["schreiben"]) == 8
    assert o["passMark"] == 0.6 and set(o["selfChecks"]) == {"aufgabe", "anrede", "konnektoren", "verbstellung"}
    assert o["readiness"]["lesen"]["attempts"] == 0


def test_item_hides_answers(client):
    it = client.get("/api/practice/lesen/l1").json()
    assert all("correct" not in q for q in it["questions"])
    h = client.get("/api/practice/hoeren/h1").json()
    assert "script" not in h
    assert client.get("/api/practice/lesen/zz").status_code == 404
    assert client.get("/api/practice/schreiben/l1").status_code == 422


def test_submit_scores_stores_and_updates_readiness(client):
    item = practice.get("lesen", "l3")
    r = client.post("/api/practice/lesen/l3/submit", json={"answers": key(item), "seconds": 300, "timed": True}).json()
    assert r["points"] == r["total"] and r["passed"]
    o = client.get("/api/practice").json()
    assert o["readiness"]["lesen"]["latest"] == 1.0
    assert next(i for i in o["lesen"] if i["id"] == "l3")["last"] == 1.0


def test_listening_submit_reveals_transcript(client):
    item = practice.get("hoeren", "h3")
    r = client.post("/api/practice/hoeren/h3/submit", json={"answers": {}}).json()
    assert r["points"] == 0 and r["script"] == item["script"]


def test_listening_audio(client, monkeypatch):
    assert client.get("/api/practice/hoeren/h1/audio").status_code == 404  # no Piper in tests

    def fake(segments, synthesize=None, fmt="ogg"):
        p = tts.cache_path(tts.script_key(segments), fmt)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"OggS")
        return p
    monkeypatch.setattr(tts, "script_audio", fake)
    assert client.get("/api/practice/hoeren/h1/audio").content == b"OggS"


def test_schreiben_selfcheck(client):
    r = client.post("/api/practice/schreiben/s01/selfcheck", json={
        "checks": {"aufgabe": True, "anrede": True, "konnektoren": False, "verbstellung": True},
        "text": "Liebe Lea, …", "seconds": 900, "timed": True}).json()
    assert (r["points"], r["total"], r["passed"]) == (3, 4, True)
    assert client.get("/api/writing?context=practice").json()[0]["promptId"] == "s01"
    assert client.post("/api/practice/schreiben/p01/selfcheck", json={"checks": {}}).status_code == 404


def test_script_key_distinguishes_speakers():
    a = tts.script_key([{"speaker": "A", "text": "Hallo"}])
    b = tts.script_key([{"speaker": "B", "text": "Hallo"}])
    assert a != b
