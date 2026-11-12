from kaskade import texts, tts


def test_list_and_detail(client):
    lib = client.get("/api/texts").json()
    assert len(lib) >= 5
    first = lib[0]
    assert {"id", "title", "level", "slot", "words", "coverage"} <= set(first)
    d = client.get(f"/api/texts/{first['id']}").json()
    assert d["text"] and d["glossary"] and d["readAt"] is None


def test_mark_read_and_next_unread(client):
    lib = texts.library()
    inputs = [t["id"] for t in lib if t["slot"] == "input"]
    assert texts.next_unread("input", set())["id"] == inputs[0]
    client.post(f"/api/texts/{inputs[0]}/read")
    assert client.get(f"/api/texts/{inputs[0]}").json()["readAt"]
    assert texts.next_unread("input", {inputs[0]})["id"] == inputs[1]
    # all read → start again with the first
    assert texts.next_unread("input", set(inputs))["id"] == inputs[0]


def test_unknown_text_404(client):
    assert client.get("/api/texts/t99").status_code == 404
    assert client.post("/api/texts/t99/read").status_code == 404
    assert client.get("/api/texts/t99/audio").status_code == 404


def test_text_audio(client, monkeypatch):
    tid = texts.library()[0]["id"]
    assert client.get(f"/api/texts/{tid}/audio").status_code == 404  # no Piper in tests

    def fake(text, synthesize=None):
        p = tts.cache_path(text)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"OggS")
        return p

    monkeypatch.setattr(tts, "audio_for", fake)
    assert client.get(f"/api/texts/{tid}/audio").content == b"OggS"


def test_today_suggests_texts(client):
    t = client.get("/api/today").json()
    assert t["texts"]["input"]["slot"] == "input"
    assert t["texts"]["lesen"]["slot"] == "lesen"


def test_detail_keeps_full_glossary(client):
    d = client.get("/api/texts/t01").json()
    assert isinstance(d["glossary"], list) and d["glossaryCount"] == len(d["glossary"])
