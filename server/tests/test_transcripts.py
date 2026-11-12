"""#29: the "gesprochen" track from Whisper words. All sentences here are invented for the tests."""
import json

from kaskade import db, transcripts as tr


def words(text, at, step=0.3, gap=0.05, p=0.9):
    """Whisper-like words: each `step - gap` long, starting `step` apart from `at`."""
    out = []
    for i, w in enumerate(text.split()):
        s = round(at + i * step, 2)
        out.append({"w": w, "s": s, "e": round(s + step - gap, 2), "p": p})
    return out


def seg(text, at, **kw):
    ws = words(text, at, **kw)
    return {"start": ws[0]["s"], "end": ws[-1]["e"], "text": text, "no_speech_prob": 0.01, "avg_logprob": -0.2,
            "words": ws}


def texts(lines):
    return [" ".join(w["w"] for w in ln) for ln in lines]


# ── line builder ──

def test_lines_end_after_a_sentence_and_at_a_pause():
    ws = words("Wo warst du gestern? Ich war im Kino", 0.0) + words("mit meiner Schwester.", 3.2)
    assert texts(tr.build_lines(ws)) == ["Wo warst du gestern?", "Ich war im Kino", "mit meiner Schwester."]


def test_a_dot_after_a_number_or_title_ends_nothing():
    ws = words("Am 3. Oktober kommt Dr. Albers wieder.", 0.0)
    assert texts(tr.build_lines(ws)) == ["Am 3. Oktober kommt Dr. Albers wieder."]


def test_a_long_line_splits_at_its_last_comma():
    ws = words("Wenn du morgen kommst, bring bitte das Buch mit, sonst muss ich es dir am Freitag mit der Post schicken.", 0.0)
    lines = texts(tr.build_lines(ws))
    assert lines == ["Wenn du morgen kommst, bring bitte das Buch mit,", "sonst muss ich es dir am Freitag mit der Post schicken."]


def test_a_long_line_without_comma_splits_at_a_pause():
    ws = words("Wir fahren heute früh mit dem alten Zug", 0.0, step=0.4) + words("nach Hamburg zu meiner Tante Gisela ans Meer.", 3.5, step=0.4)
    # 16 words, the gap at 3.15 → 3.5 is 0.35 s (no 0.7-s pause): a natural place, between two phrases
    assert texts(tr.build_lines(ws)) == ["Wir fahren heute früh mit dem alten Zug", "nach Hamburg zu meiner Tante Gisela ans Meer."]


def test_a_conjunction_beats_a_short_pause():
    """#34: a long line breaks before und/aber/dass … rather than at a 0.25-s pause."""
    ws = words("Wir fahren heute mit dem alten Zug", 0.0, step=0.4) + words("nach Hamburg und dann weiter an die Ostsee zu meiner Tante.", 3.0, step=0.4)
    assert texts(tr.build_lines(ws)) == ["Wir fahren heute mit dem alten Zug nach Hamburg", "und dann weiter an die Ostsee zu meiner Tante."]


def test_a_long_line_never_breaks_inside_a_phrase():
    """#34, the shape of SOKO 3:31: 16 words without a pause used to lose its last 0.6 s ("… stand ein" |
    "Karton mit Akten."). Now: before the conjunction, the article stays with its noun."""
    ws = words("Ich bin leise in den Keller gegangen und auf dem Regal stand ein Karton mit Akten.", 0.0, step=0.28, gap=0.0)
    assert texts(tr.build_lines(ws)) == ["Ich bin leise in den Keller gegangen", "und auf dem Regal stand ein Karton mit Akten."]


def test_no_natural_break_keeps_the_line_whole_up_to_two_rows():
    ws = words("Der alte Herr aus dem Dorf hinter dem Wald kaufte am Morgen drei frische Brote.", 0.0, step=0.3, gap=0.0)
    assert len(ws) == 15 and len(tr.join_words(ws)) <= tr.MAX_CHARS
    assert texts(tr.build_lines(ws)) == ["Der alte Herr aus dem Dorf hinter dem Wald kaufte am Morgen drei frische Brote."]


def test_over_two_rows_it_breaks_between_phrases_never_after_an_opener():
    ws = words("Die Kommission der Gemeinde empfiehlt eine gründliche Untersuchung der Wasserleitungen im Ortsteil Unterberg vor dem Winter.", 0.0, step=0.3, gap=0.0)
    assert len(tr.join_words(ws)) > tr.MAX_CHARS
    assert texts(tr.build_lines(ws)) == ["Die Kommission der Gemeinde empfiehlt", "eine gründliche Untersuchung der Wasserleitungen",
                                         "im Ortsteil Unterberg vor dem Winter."]


def mid_phrase(track):
    """Matt's count: no punctuation at the end, ends on an opener, the next line within 0.5 s."""
    return [(a["text"], b["text"]) for a, b in zip(track, track[1:])
            if a["text"].split()[-1].lower() in tr.OPENERS and b["start"] - a["end"] <= 0.5]


def test_the_spoken_track_has_no_mid_phrase_breaks():
    t = {"segments": [seg("Ich bin leise in den Keller gegangen und auf dem Regal stand ein Karton mit Akten.", 1.0, step=0.28, gap=0.0),
                      seg("Dann habe ich dort drüben im Schatten einen Mann mit einer roten Mütze gesehen.", 6.0, step=0.28, gap=0.0)]}
    track = tr.spoken_cues(t, [])
    assert len(track) >= 3 and mid_phrase(track) == []


def test_whisper_word_pieces_join_without_a_space():
    ws = [{"w": w, "s": 0.0, "e": 0.1} for w in ("Das", "kostet", "2", ",50", "Euro", "in", "der", "ARD", "-Quiz", "-App", "–", "ehrlich.")]
    assert tr.join_words(ws) == "Das kostet 2,50 Euro in der ARD-Quiz-App – ehrlich."


# ── #34: an all-lowercase stretch (Whisper's fast speech) ──

MINI_DICT = {"entries": {"Rechnung": [{"pos": "NOUN"}], "Auto": [{"pos": "NOUN"}], "Konto": [{"pos": "NOUN"}],
                         "Ehe": [{"pos": "NOUN"}], "ehe": [{"pos": "SCONJ"}], "Ich": [{"pos": "NOUN"}],
                         "ich": [{"pos": "PRON"}], "zahlen": [{"pos": "VERB"}]},
             "forms": {"zahlt": "zahlen"}}


def test_a_lowercase_stretch_gets_its_nouns_back_and_never_runs_into_the_next_speaker(monkeypatch):
    from kaskade import analyze
    monkeypatch.setattr(analyze, "dictionary", lambda: MINI_DICT)
    t = {"segments": [seg("seit unserer ehe zahlt er die rechnung für das auto von meinem konto für", 1.0, step=0.25, gap=0.0),
                      seg("Ich nehme zwei Brötchen.", 4.75, step=0.2, gap=0.0)]}
    lines = [c["text"] for c in tr.spoken_cues(t, [])]
    assert lines == ["seit unserer Ehe zahlt er die Rechnung für das Auto von meinem Konto für", "Ich nehme zwei Brötchen."]
    # ARD's capitals come first: a name the dictionary doesn't know
    ard = [{"start": 1.0, "end": 4.0, "text": "Seit unserer Ehe zahlt Gerlinde die Rechnung."}]
    t = {"segments": [seg("seit unserer ehe zahlt gerlinde die rechnung", 1.0, step=0.3)]}
    assert [c["text"] for c in tr.spoken_cues(t, ard)] == ["seit unserer Ehe zahlt Gerlinde die Rechnung"]


def test_a_new_sentence_in_a_new_segment_starts_a_line_but_sie_and_a_phrase_do_not():
    ws = [*({**w, "seg": 0} for w in words("Hast du heute keine Zeit", 0.0)),
          *({**w, "seg": 1} for w in words("Wir können morgen gehen.", 1.5))]
    assert texts(tr.build_lines(ws)) == ["Hast du heute keine Zeit", "Wir können morgen gehen."]
    ws = [*({**w, "seg": 0} for w in words("Ich weiß nicht, ob", 0.0)), *({**w, "seg": 1} for w in words("Sie das verstehen.", 1.2))]
    assert texts(tr.build_lines(ws)) == ["Ich weiß nicht, ob Sie das verstehen."]


def test_after_a_lowercase_stretch_a_noun_stays_with_its_article(monkeypatch):
    from kaskade import analyze
    monkeypatch.setattr(analyze, "dictionary", lambda: MINI_DICT)
    t = {"segments": [seg("und das ist dann wirklich wichtig für die", 1.0, step=0.25, gap=0.0),
                      seg("Kinder im Haus.", 3.0, step=0.25, gap=0.0)]}
    assert [c["text"] for c in tr.spoken_cues(t, [])] == ["und das ist dann wirklich wichtig für die Kinder im Haus."]
    assert not tr.lowercase_segment({"text": "und die dann gegangen sind,"})  # punctuated: Whisper's normal text


def test_no_line_shorter_than_0_6_s_unless_a_whole_sentence():
    ws = words("Und dann", 0.0, step=0.2) + words("ging sie einfach nach Hause.", 1.5) + words("Ich?", 4.0, step=0.3) + words("Ja, du.", 5.0)
    lines = texts(tr.build_lines(ws))
    assert lines[0] == "Und dann ging sie einfach nach Hause."  # 0.35-s fragment joined to what follows
    assert "Ich?" in lines  # 0.25 s, but a sentence on its own


# ── hallucinations ──

def test_vielen_dank_over_music_is_dropped_but_the_same_words_over_speech_stay():
    ard = [{"start": 10.0, "end": 14.0, "text": "♪ Leise Klaviermusik ♪"},
           {"start": 20.0, "end": 22.0, "text": "Vielen Dank."}]
    t = {"segments": [seg("Vielen Dank.", 11.0, p=0.6), seg("Vielen Dank.", 20.2, p=0.6),
                      seg("Das ist schön hier.", 30.0, p=0.5), seg("Untertitel im Auftrag des Senders", 40.0, p=0.9)]}
    track = tr.spoken_cues(t, ard)
    spoken = [c["text"] for c in track if not c["text"].startswith("♪")]
    assert spoken == ["Vielen Dank."] and next(c for c in track if c["text"] == "Vielen Dank.")["start"] == 20.2
    # no ARD speech near 30 s and unsure (p 0.5): dropped; a known phrase goes even when Whisper is sure


def test_sure_speech_without_an_ard_line_stays():
    """ARD leaves whole lines out — that is the point of the track."""
    t = {"segments": [seg("Ich hab das nachgeprüft.", 5.0, p=0.92)]}
    assert [c["text"] for c in tr.spoken_cues(t, [])] == ["Ich hab das nachgeprüft."]


def test_musik_over_the_opening_credits_is_no_line(client):
    """#30: Whisper writes "Musik" over a theme tune — a sound cue, not dialogue (no auto-pause at 0:00)."""
    from kaskade.satzcheck import is_non_speech
    ard = [{"start": 0.0, "end": 3.0, "text": "Untertitel: Testfunk 2026"}, {"start": 6.0, "end": 10.0, "text": "♪ Titelmusik ♪"},
           {"start": 69.0, "end": 70.5, "text": "Hallo, ist da jemand?"}]
    t = {"segments": [seg("Musik", 0.0, step=1.44, gap=0.0), seg("Hallo, ist da jemand?", 68.1)]}
    track = tr.spoken_cues(t, ard)
    assert [c["text"] for c in track] == ["Musik", "♪ Titelmusik ♪", "Hallo, ist da jemand?"]  # the credit line isn't filled in
    assert [c["text"] for c in track if not is_non_speech(c["text"])] == ["Hallo, ist da jemand?"]


def test_sound_cues_stay_interleaved_by_time():
    ard = [{"start": 0.5, "end": 2.0, "text": "Kommst du mit?"}, {"start": 2.5, "end": 4.0, "text": "* Glockenläuten *"},
           {"start": 4.5, "end": 6.0, "text": "Gleich."}]
    t = {"segments": [seg("Kommst du heute mit?", 0.6), seg("Ja, gleich.", 4.6)]}
    track = tr.spoken_cues(t, ard)
    assert [c["text"] for c in track] == ["Kommst du heute mit?", "* Glockenläuten *", "Ja, gleich."]
    assert track[0] == {"start": 0.6, "end": 1.75, "text": "Kommst du heute mit?"}  # word times, not ARD's


# ── import ──

def test_import_builds_the_track_once_and_follows_the_file(client):
    from kaskade import config
    cues = [{"start": 1.0, "end": 3.0, "text": "Wo ist der Schlüssel?"}]
    with db.tx() as conn:
        mid = conn.execute("INSERT INTO media(created_at, kind, title, media_file, cues) VALUES (?, ?, ?, ?, ?)",
                           (db.now_iso(), "upload", "Probe", "upload-7.mp4", json.dumps(cues))).lastrowid
        conn.execute("INSERT INTO media(created_at, kind, title, media_file, cues) VALUES (?, ?, ?, ?, ?)",
                     (db.now_iso(), "upload", "Ohne", "upload-8.mp4", "[]"))
    tr.transcripts_dir().mkdir(parents=True, exist_ok=True)
    f = config.DATA_DIR / "transcripts" / "upload-7.whisper.json"
    f.write_text(json.dumps({"model": "test", "segments": [seg("Wo ist denn der Schlüssel?", 1.1)]}), encoding="utf-8")
    assert tr.import_all() == {"withTranscript": [mid], "changed": [mid], "errors": [], "kept": []}
    assert tr.import_all()["changed"] == []  # idempotent
    assert tr.load(mid)[0]["text"] == "Wo ist denn der Schlüssel?"
    m = client.get(f"/api/media/{mid}").json()
    assert m["spokenCues"][0]["text"] == "Wo ist denn der Schlüssel?" and m["cues"][0]["text"] == "Wo ist der Schlüssel?"
    assert [x["hasSpoken"] for x in client.get("/api/media").json() if x["id"] == mid] == [True]
    f.write_text("{kaputt", encoding="utf-8")
    r = tr.import_all()
    assert r["errors"][0]["mediaId"] == mid and tr.load(mid)  # a broken file keeps the last good track
    f.unlink()
    assert tr.import_all()["changed"] == [mid] and tr.load(mid) is None
    assert client.get(f"/api/media/{mid}").json()["spokenCues"] is None


def test_lines_never_overlap():
    """Words of two segments overlap by 0.2 s: the first line ends where the second begins (#18)."""
    t = {"segments": [seg("Komm sofort her!", 1.0), seg("Ich komme ja schon.", 1.65)]}
    a, b = tr.spoken_cues(t, [])
    assert a["end"] == b["start"] == 1.65 and a["text"] == "Komm sofort her!"


def test_a_short_fragment_never_joins_across_a_long_silence():
    """Schweigen 13:22: 'War ein Unfall?' 7 s after a line ending in a comma stayed a line of its own."""
    ws = words("Ruß in der Lunge, aber wie,", 0.0) + words("War ein Unfall?", 9.0, step=0.18)
    assert texts(tr.build_lines(ws)) == ["Ruß in der Lunge, aber wie,", "War ein Unfall?"]


def test_an_ard_line_where_whisper_heard_nothing_stands_in():
    ard = [{"start": 1.0, "end": 2.5, "text": "Wo ist sie hin?"}, {"start": 5.0, "end": 6.5, "text": "Weiß ich nicht."}]
    t = {"segments": [seg("Wo ist sie denn hin?", 1.1)]}
    assert tr.spoken_cues(t, ard) == [
        {"start": 1.1, "end": 2.55, "text": "Wo ist sie denn hin?"},
        {"start": 5.0, "end": 6.5, "text": "Weiß ich nicht.", "src": "ard"}]


def test_the_prompt_word_glossar_never_shows():
    t = {"segments": [seg("Glossar, aber es wird Ihnen nichts nützen.", 3.0)]}
    assert [c["text"] for c in tr.spoken_cues(t, [{"start": 3.0, "end": 5.0, "text": "Es wird nichts nützen."}])] == [
        "aber es wird Ihnen nichts nützen."]


# ── v2: respelling from ARD, gap fill, re-import on change ──

def line_texts(t, ard):
    return [c["text"] for c in tr.spoken_cues(t, ard)]


def test_a_misheard_name_takes_the_ard_spelling():
    """'Autos' is spelt nothing like 'Otto' (< 0.6) but sounds close, and Otto is a name of this clip
    (≥ 8×, not sentence-initial — also a dictionary word, so it takes that many); 'Geh' doesn't sound like it."""
    ard = [{"start": 1.0, "end": 3.0, "text": "Kennen Sie Pfarrer Otto?"},
           {"start": 9.0, "end": 11.0, "text": "Ja, ich kenne Otto."},
           {"start": 15.0, "end": 17.0, "text": "Wo ist Otto? Hallo, Otto."},
           {"start": 21.0, "end": 23.0, "text": "Komm, Otto."},
           *({"start": 30.0 + 3 * i, "end": 31.0 + 3 * i, "text": "Danke, Otto."} for i in range(4))]
    t = {"segments": [seg("Kennen Sie Pfarrer Autos?", 1.1), seg("Ja, ich kenne ihn, Autos.", 9.1),
                      seg("Komm, geh.", 21.1)]}
    assert [c["text"] for c in tr.spoken_cues(t, ard) if not c.get("src")] == [
        "Kennen Sie Pfarrer Otto?", "Ja, ich kenne ihn, Autos.", "Komm, geh."]
    # second line: ARD has one word less there — an unequal block is left alone


def test_a_near_miss_word_is_respelled_keeping_punctuation_and_times():
    ard = [{"start": 2.0, "end": 4.0, "text": "Jemand hat alles durchwühlt."}]
    t = {"segments": [seg("Jemand hat alles durchwählt.", 2.1)]}
    track = tr.spoken_cues(t, ard)
    assert track == [{"start": 2.1, "end": 3.25, "text": "Jemand hat alles durchwühlt."}]


def test_below_the_threshold_nothing_is_respelled():
    ard = [{"start": 2.0, "end": 4.0, "text": "Da steht eine Katze."},
           {"start": 6.0, "end": 8.0, "text": "Das war der Letzter."}]
    t = {"segments": [seg("Da steht ein Hund.", 2.1), seg("Das war der Bester.", 6.1)]}
    # 'Hund'/'Katze' far apart; 'Bester'/'Letzter' spelt alike (0.77) but they don't sound alike
    assert line_texts(t, ard)[0:2] == ["Da steht ein Hund.", "Das war der Bester."]


def test_inflection_and_elision_stay_as_said():
    """ARD tidies speech up: 'hab' → 'habe', 'deinem' → 'dein'. What Whisper heard was said."""
    ard = [{"start": 1.0, "end": 3.0, "text": "Ich habe es dein Vater gesagt."}]
    t = {"segments": [seg("Ich hab es deinem Vater gesagt.", 1.1)]}
    assert line_texts(t, ard) == ["Ich hab es deinem Vater gesagt."]


def test_kölner_phonetik():
    assert [tr.koelner(w) for w in ("Müller", "Wikipedia", "Christoph", "Tace", "Tatsche")] == ["657", "3412", "47823", "28", "28"]


def test_an_unequal_replace_block_is_left_alone():
    ard = [{"start": 1.0, "end": 3.5, "text": "Er nimmt das Auto mit."}]
    t = {"segments": [seg("Er nimmt den alten Wagen mit.", 1.1)]}
    assert line_texts(t, ard) == ["Er nimmt den alten Wagen mit."]


def test_a_sentence_start_stays_capitalised():
    ard = [{"start": 1.0, "end": 3.0, "text": "Und dann kamen sie."}]
    t = {"segments": [seg("Dan kamen sie.", 1.1)]}  # 'Dan' ↔ 'und dann': unequal, untouched
    assert line_texts(t, ard) == ["Dan kamen sie."]
    ard = [{"start": 1.0, "end": 3.0, "text": "Alles durchwühlt."}]
    t = {"segments": [seg("Alles. Durchwählt.", 1.1)]}
    assert line_texts(t, ard) == ["Alles.", "Durchwühlt."]


def test_gap_fill_only_where_no_whisper_word_is_near():
    ard = [{"start": 1.0, "end": 2.0, "text": "Komm her."},
           {"start": 2.3, "end": 3.2, "text": "Sofort!"},  # Whisper's "her." ends at 2.55: near, no fill
           {"start": 8.0, "end": 9.5, "text": "Generalvikar Billing wird kooperieren."}]
    t = {"segments": [seg("Komm her.", 1.95)]}
    track = tr.spoken_cues(t, ard)
    assert [(c["text"], c.get("src")) for c in track] == [
        ("Komm her.", None), ("Generalvikar Billing wird kooperieren.", "ard")]


def test_reimport_when_the_file_changes(client):
    import os
    cues = [{"start": 1.0, "end": 3.0, "text": "Wo ist der Schlüssel?"}]
    with db.tx() as conn:
        mid = conn.execute("INSERT INTO media(created_at, kind, title, media_file, cues) VALUES (?, ?, ?, ?, ?)",
                           (db.now_iso(), "upload", "Probe", "upload-9.mp4", json.dumps(cues))).lastrowid
    tr.transcripts_dir().mkdir(parents=True, exist_ok=True)
    f = tr.path_for("upload-9.mp4")
    f.write_text(json.dumps({"segments": [seg("Wo ist der Schlüssel denn?", 1.1)]}), encoding="utf-8")
    os.utime(f, ns=(1_000_000_000, 1_000_000_000))
    assert tr.import_all()["changed"] == [mid]
    assert tr.import_all()["changed"] == []  # same file: not even read again
    f.write_text(json.dumps({"version": 2, "segments": [seg("Wo ist nur der Schlüssel?", 1.1)]}), encoding="utf-8")
    os.utime(f, ns=(2_000_000_000, 2_000_000_000))
    # opening the clip picks the new file up
    assert client.get(f"/api/media/{mid}").json()["spokenCues"][0]["text"] == "Wo ist nur der Schlüssel?"
    assert tr.import_all()["changed"] == []
    assert tr.import_all(force=True)["changed"] == []  # rebuilt, same result


# ── #35: what he is in the middle of keeps its lines ──

def test_a_started_clip_keeps_its_track_until_he_is_through(client):
    import os
    cues = [{"start": 1.0, "end": 3.0, "text": "Wo ist der Schlüssel?"}, {"start": 96.0, "end": 100.0, "text": "Ende."}]
    with db.tx() as conn:
        mid = conn.execute("INSERT INTO media(created_at, kind, title, media_file, cues) VALUES (?, ?, ?, ?, ?)",
                           (db.now_iso(), "upload", "Probe", "upload-11.mp4", json.dumps(cues))).lastrowid
    tr.transcripts_dir().mkdir(parents=True, exist_ok=True)
    f = tr.path_for("upload-11.mp4")
    f.write_text(json.dumps({"segments": [seg("Wo ist der Schlüssel denn?", 1.1)]}), encoding="utf-8")
    os.utime(f, ns=(1_000_000_000, 1_000_000_000))
    assert tr.import_all()["changed"] == [mid]
    before = tr.load(mid)

    def watched(position):
        client.put(f"/api/media/{mid}/progress", json={"position": position})

    # half watched: a new builder or a new file changes nothing, also with --force
    watched(40.0)
    assert tr.in_progress(mid)
    f.write_text(json.dumps({"segments": [seg("Wo ist nur der Schlüssel?", 1.1)]}), encoding="utf-8")
    os.utime(f, ns=(2_000_000_000, 2_000_000_000))
    assert tr.import_all() == {"withTranscript": [mid], "changed": [], "errors": [], "kept": [mid]}
    assert tr.import_all(force=True)["kept"] == [mid]
    assert client.get(f"/api/media/{mid}").json()["spokenCues"] == before  # opening it doesn't either
    assert tr.import_all(mid)["kept"] == [mid]
    # the operator names it: rebuilt
    assert tr.import_all(mid, force=True)["changed"] == [mid]
    assert tr.load(mid)[0]["text"] == "Wo ist nur der Schlüssel?"


def test_a_finished_clip_and_an_unstarted_one_get_the_new_lines(client):
    import os
    cues = [{"start": 1.0, "end": 3.0, "text": "Wo ist der Schlüssel?"}, {"start": 96.0, "end": 100.0, "text": "Ende."}]
    ids = []
    for n in (12, 13):
        with db.tx() as conn:
            ids.append(conn.execute("INSERT INTO media(created_at, kind, title, media_file, cues) VALUES (?, ?, ?, ?, ?)",
                                    (db.now_iso(), "upload", "Probe", f"upload-{n}.mp4", json.dumps(cues))).lastrowid)
        tr.transcripts_dir().mkdir(parents=True, exist_ok=True)
        tr.path_for(f"upload-{n}.mp4").write_text(json.dumps({"segments": [seg("Wo ist der Schlüssel denn?", 1.1)]}), encoding="utf-8")
    assert sorted(tr.import_all()["changed"]) == ids
    client.put(f"/api/media/{ids[0]}/progress", json={"position": 92.0})  # within 10 s of the end: finished
    client.put(f"/api/media/{ids[1]}/progress", json={"position": 1.0})   # only opened: not started
    assert not tr.in_progress(ids[0]) and not tr.in_progress(ids[1])
    for n in (12, 13):
        f = tr.path_for(f"upload-{n}.mp4")
        f.write_text(json.dumps({"segments": [seg("Wo ist nur der Schlüssel?", 1.1)]}), encoding="utf-8")
        os.utime(f, ns=(3_000_000_000, 3_000_000_000))
    assert sorted(tr.import_all()["changed"]) == ids


def test_the_end_of_a_planned_clip_is_where_the_plan_stops(client):
    """Tatort: Schweigen's plan ends at 89:21 (before the credits): his 89:19 is finished."""
    cues = [{"start": 1.0, "end": 3.0, "text": "Wo ist der Schlüssel?"}, {"start": 5500.0, "end": 5502.0, "text": "Abspann."}]
    with db.tx() as conn:
        mid = conn.execute("INSERT INTO media(created_at, kind, title, media_file, cues, key) VALUES (?, ?, ?, ?, ?, ?)",
                           (db.now_iso(), "mediathek", "Schweigen", "x.mp4", json.dumps(cues), "tatort-schweigen")).lastrowid
    db.set_setting("phase", "2B")
    assert tr.clip_end(mid) == 5361
    client.put(f"/api/media/{mid}/progress", json={"position": 5359.6})
    assert not tr.in_progress(mid)
    client.put(f"/api/media/{mid}/progress", json={"position": 1314.0})
    assert tr.in_progress(mid)
