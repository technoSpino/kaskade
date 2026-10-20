# Kaskade — Runbook

Everything runs as **user services** of `kaskade` on this box (lingering is on, so they
survive reboots and logouts). Nothing needs sudo. Other services on the box (`cos.service`,
Caddy, Tailscale serve on port 80) belong to another project — don't touch them.

## Services

| Unit | What | Address |
|---|---|---|
| `kaskade-api` | FastAPI + SQLite (`server/`) | 127.0.0.1:8000 (local only) |
| `kaskade-web` | built Vue app via `vite preview`, proxies `/api` | 100.64.43.3:5173 (tailnet only) |
| Tailscale serve (set up by Matt, not by us) | HTTPS in front of `kaskade-web` — **use this address**; the microphone only works over HTTPS | https://cos.tail1b5741.ts.net:8443 (tailnet only) |
| `kaskade-backup.timer` | daily backup at 12:00 UTC | — |
| `kaskade-stock.timer` | daily 04:30 UTC: fetch due plan media (`data/plan/stock.json`), pick the day's tagesschau links, Materialcheck → `~/kaskade-data/materialcheck.json` | — |

```bash
systemctl --user status kaskade-api kaskade-web
systemctl --user restart kaskade-api                      # after backend/content changes
~/kaskade/deploy/web-deploy.sh                            # after frontend changes: keeps old chunks, so open tabs keep working (#20)
journalctl --user -u kaskade-api -n 100 --no-pager        # logs
systemctl --user list-timers | grep kaskade               # next backup
```

Unit files live in `deploy/systemd/`; after editing: copy to `~/.config/systemd/user/`,
then `systemctl --user daemon-reload`.

**Never bind to 0.0.0.0** — the box has a public IP. API on 127.0.0.1, web on the
Tailscale IP 100.64.43.3.

## Data

`~/kaskade-data/` (not in git):

| Path | What | Backed up? |
|---|---|---|
| `kaskade.db` | all progress: cards/FSRS, tests, placement, timers, immersion, settings | yes |
| `media/` | clips: your uploads (`upload-*`, backed up) and plan stock fetched by Kaskade (`stock-*`, `mt-*`: Mediathek/podcast, **not** backed up — `scripts/stock.py` fetches them again) | uploads only |
| `materialcheck.json` | result of the daily Materialcheck (gaps in the next 7 days, link status, missing transcripts, `themes`: library clips with child-abuse hits, #33) | no (regenerated) |
| `recordings/` | Sprechen recordings | yes |
| `snippets/` | audio of lines mined in Schauen & minen | yes |
| `tts/` | Piper voice + generated audio | no (regenerate) |
| `dict/` | Wiktionary glossary | no (regenerate) |
| `freq/` | raw frequency list | no (re-download) |
| `.env` | `ANTHROPIC_API_KEY=…` (optional) | no (secret) |
| `youtube-cookies.txt` | optional YouTube login for yt-dlp (chmod 600, delete in Satz-Check → YouTube) | no (secret) |

### Backup and restore

```bash
cd ~/kaskade/server && .venv/bin/python scripts/backup.py     # manual backup → ~/kaskade-backups/
# restore (stop the API first):
systemctl --user stop kaskade-api
tar -xzf ~/kaskade-backups/kaskade-YYYYMMDD-HHMMSS.tar.gz -C ~      # restores ~/kaskade-data/{kaskade.db,media,recordings,snippets}
systemctl --user start kaskade-api
```

Backups keep the newest 14. For an off-box copy: `scp ~/kaskade-backups/<newest> <elsewhere>`.

### Regenerate what isn't backed up

```bash
cd ~/kaskade/server
# Piper voice (CC0 dataset) → ~/kaskade-data/tts/voices/
for f in de_DE-thorsten-medium.onnx de_DE-thorsten-medium.onnx.json; do
  curl -sSfL -o ~/kaskade-data/tts/voices/$f https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/$f; done
.venv/bin/python scripts/tts_deck.py                         # all card audio (~10 min)
# Wiktionary glossary
curl -sSfL -o ~/kaskade-data/dict/kaikki-German.jsonl.gz https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl.gz
.venv/bin/python scripts/build_dict.py
```

## Updating dependencies

```bash
cd ~/kaskade/server
.venv/bin/pip install -r requirements.txt -r requirements-tools.txt
.venv/bin/python -m spacy download de_core_news_sm
.venv/bin/python -m pytest -q                                 # must stay green
cd ~/kaskade/app && npm ci && npm run test && npm run build
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 npm run test:e2e:kaskade
systemctl --user restart kaskade-api kaskade-web
```

Pinned versions are in `server/requirements*.txt` and `app/package-lock.json`. Update one
thing at a time; the FSRS package (`fsrs`) stores card state as JSON — check its changelog
before major upgrades.

## Content

- Core deck: edit `data/core-deck/raw/*.json`, then `server/.venv/bin/python server/scripts/merge_deck.py`
  (validates and writes `NNNN.json`). Card ids are tied to frequency ranks, so edits keep progress.
- Reading texts: `data/texts/tNN.json`, check with `scripts/check_text.py` (≥ 95 % core words).
- After content changes: `systemctl --user restart kaskade-api` (content is cached in memory).

## Troubleshooting

| Symptom | Check |
|---|---|
| Yellow banner "Server nicht erreichbar" | `systemctl --user status kaskade-api`, logs |
| Page not reachable | Tailscale on? `systemctl --user status kaskade-web`; web binds to 100.64.43.3 and retries until Tailscale is up |
| No audio | `ls ~/kaskade-data/tts/voices/` — without the voice the browser voice is used |
| No glosses in the reader | `ls ~/kaskade-data/dict/de-en.json` |
| YouTube download fails | YouTube blocks datacenter IPs: upload a `cookies.txt` (Satz-Check → Von YouTube holen) or download on the Mac with the one-liner shown there and upload. ARD/ZDF Mediathek works directly |
| Big upload stalls | uploads go up in 8 MB pieces (the web server ends requests after 5 min); unfinished pieces sit in `~/kaskade-data/media/.partial/` and are deleted after 24 h |
| Heute shows "→ zu tun" for a clip | it's missing from the library: `cd ~/kaskade/server && .venv/bin/python scripts/stock.py` (or `--only KEY`); a Mediathek item that is not released yet (e.g. a Tatort before its first broadcast) has `fetchOn` in `stock.json` |
| Recording doesn't start | over http the browser blocks the microphone: open https://cos.tail1b5741.ts.net:8443 |
| Writing not graded | no `ANTHROPIC_API_KEY` in `~/kaskade-data/.env` (optional) |
| Karten: "Autoplay vom Browser blockiert — A drücken" | the browser wants a click first (Safari, Firefox after opening `/karten` directly): one key or click and the next cards play; or untick "Audio automatisch abspielen" |
| Schauen shows ARD subtitles, no "Gesprochen (KI)" toggle | the clip has no transcript yet. cheqs-mac-mini makes them (Whisper large-v3, `"version": 2` format) nightly at 01:30 for new clips, only through `~/bin/transcribe-gate` (`todo` · `audio <id>` · `put <stem>` → `~/kaskade-data/transcripts/<media_file stem>.whisper.json`) — keep that interface (media `id`/`kind`/`media_file`, the file names). Opening the clip, the clip list or the 06:30 Materialcheck imports it; by hand: `cd ~/kaskade/server && .venv/bin/python -m kaskade.transcripts` (`--force` rebuilds all). `materialcheck.json` → `transcripts.missing` lists the planned clips without one. Never commit transcripts |
| Karten and Schauen (#30) E2E in WebKit / Firefox | WebKit: `deploy/webkit-e2e-setup.sh` once (no root), then run as its header says (`--project webkit`). Firefox: `KASKADE_FIREFOX=1 … --project firefox`; the autoplay timing test is skipped there (no audio output on this box) |
| Schauen started a clip at 0:00 / a position went backwards | every saved position is in the API log: `journalctl --user -u kaskade-api | grep 'position media'` (old → new). A jump back of > 60 s that wasn't ← or a chosen line is a `WARNING … jumped back from X to Y`. Matt has "↩ Zurück zu …" on the page, and Starten ignores a saved position before today's part once the day before reached it (#30) |
| The same podcast/radio play comes back the next day | audio heard outside Kaskade (phone) counts once he rates it on Heute (any %) or ticks the block off (#31). Neither happened → it rolls on, as a clip he hasn't seen would. Check `ratings` / `plan_done` for that day and block |
| A spoken line breaks mid-phrase, or the word panel shows the bare verb of a separable verb (#34) | the line builder (`transcripts.py`, `BUILD` 5) breaks a long line at punctuation, before a conjunction or at a pause, never inside a noun/prepositional phrase (spaCy) or after an article/preposition/prefix; a line without such a place stays whole up to 84 characters. After changing it, bump `BUILD` and run `cd ~/kaskade/server && .venv/bin/python -m kaskade.transcripts` outside study time (rebuilds every track, keeps positions, marks and cards). #35: a clip he has started and not finished keeps its track (`kept` in the output and in materialcheck.json) until he is through — also with `--force`; only `--force <id>` rebuilds that one by hand. Separable verbs: `analyze.separable()` joins only a `PTKVZ` + `svp` particle with its verb, and only into a core card or dictionary verb; Schauen posts the whole sentence with `focus` = the line |
| Matt takes a week off (#36) | Fahrplan → "Woche frei nehmen" (this week only if nothing was done in it yet; undo until it starts). Same by hand: `curl -s -X POST 127.0.0.1:8000/api/pauses -H 'Content-Type: application/json' -d '{"monday":"YYYY-MM-DD"}'`, preview with `GET /api/pauses/preview?monday=…`. It writes the setting `pauses` and drops the ranges Heute already fixed for those days; every plan date skips the week, rolling clips go on where he stopped. Cards keep their due dates; new cards wait until fewer than 20 are due once after the week (`cardsCaughtUp`). No restart needed |
| Picking a new crime item or book (#32, #33) | books: no romance — `genre` in stock.json is scifi, fantasy, history, nonfiction or krimi. Crime: read the broadcaster's/publisher's synopsis; nothing where child sexual abuse is the case or a main thread. Once its subtitles or transcript are in, the 06:30 Materialcheck searches them (`kaskade/themes.py`, `ABUSE`) and lists hits under `themes` in `materialcheck.json`; `review` set → decide before it is planned (journal: `grep themeCheck`). Write the result into the item as `"themeCheck": "<date>: Synopsis + UT geprüft, kein Kindesmissbrauch"` (`UT folgt` while it isn't imported). |
