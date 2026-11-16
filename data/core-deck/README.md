# Kernwortschatz-Deck (core deck)

Original example sentences for the ~2,000 most frequent German lemmas, written for
Kaskade (A2–B1, everyday adult life). The sentences, glosses and notes are original
work — no textbook, exam or subtitle content. The word *selection and order* come from
`data/freq/lemmas.tsv` (derived from OpenSubtitles 2018 frequencies, CC BY-SA 4.0 — see
`data/freq/README.md`).

## Files

- `raw/rAAAA-BBBB.json` — authoring files, one per 100 raw frequency ranks.
- `NNNN.json` — merged, validated batches of 100 cards (`0001.json` = cards 1–100),
  produced by `server/scripts/merge_deck.py`. The app reads these.

## Card format (raw files)

A JSON array; one object per rank in the file's range, in rank order.

```json
{
  "rank": 99,
  "lemma": "Zeit",
  "pos": "NOUN",
  "display": "die Zeit · die Zeiten",
  "gloss": "time",
  "sentence": "Ich habe heute leider keine Zeit.",
  "target": "Zeit",
  "en": "Unfortunately I don't have time today.",
  "note": "die Zeit, Plural: die Zeiten",
  "case": null
}
```

- `lemma`: dictionary form (nouns capitalised, no article; verbs infinitive).
- `display`: shown big on the back. Nouns: `der/die/das X · die Xe` (or `kein Plural`);
  verbs: `machen · hat gemacht` (add Präteritum for strong/irregular verbs:
  `gehen · ging · ist gegangen`); adjectives: base form (+ irregular comparison);
  everything else: the word.
- `target`: the exact substring of `sentence` to highlight (an inflected form is fine).
- `note`: short, simple German. Prepositions: the case (`mit + Dativ`).
- `origin` (optional): the merge writes `"origin": "ai"` on every card (the sentences are
  written for Kaskade; the app shows "KI-geschrieben"). A card from real input would set
  `"origin": "real"` plus a `source`.
  Optional elsewhere — only when it really helps.
- `case`: `"N" | "A" | "D" | "G" | null` — set for prepositions and when the note is
  about a case; shown as the coloured case badge.

Ranks that are not a learnable German word (names, English, fragments, interjections,
inflected duplicates of another lemma, slurs) are kept as `{"rank": 415, "skip": "Grund"}`.
