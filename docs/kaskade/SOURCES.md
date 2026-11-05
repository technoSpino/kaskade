# Kaskade — third-party sources and licences

| What | Source | Licence | Where |
|---|---|---|---|
| Word frequencies | Hermit Dave, *FrequencyWords* (OpenSubtitles 2018), `de_50k.txt` | CC BY-SA 4.0 | derived list in git: `data/freq/lemmas.tsv` (also CC BY-SA 4.0) |
| Lemmatiser, POS, case morphology | spaCy + `de_core_news_sm` 3.8 | MIT (spaCy), CC BY-SA 4.0 (model, trained on TIGER/WikiNER) | installed in `server/.venv`, not in git |
| German–English glossary (reader) | Wiktionary via kaikki.org (`kaikki.org-dictionary-German.jsonl.gz`, Oct 2026) | CC BY-SA 4.0 / GFDL | `~/kaskade-data/dict/` only, not in git; rebuild with `server/scripts/build_dict.py` |
| Sentence audio | Piper TTS 1.8 (`piper-tts`) | GPL-3.0 (used as a tool) | `server/.venv` |
| Voice | `de_DE-thorsten-medium` (rhasspy/piper-voices); dataset Thorsten-Voice | dataset CC0; model fine-tuned from Piper's "lessac" voice | `~/kaskade-data/tts/voices/`, audio in `~/kaskade-data/tts/audio/` |
| Fonts | Archivo, Archivo Black, Literata, Source Serif 4, Atkinson Hyperlegible, Libre Franklin via `@fontsource/*` | SIL OFL 1.1 | bundled by Vite from `node_modules` |
| SRS | `fsrs` (Python) 6.3 | MIT | `server/.venv` |

Everything else in `data/` (core-deck sentences, reading texts, placement texts, plan
prompts, pseudowords) is original work written for Kaskade.
