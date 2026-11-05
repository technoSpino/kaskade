# Frequency data

`lemmas.tsv` — German lemmas ordered by frequency (columns: `rank, lemma, pos, count, forms`).

**Source:** Hermit Dave, *FrequencyWords*, `content/2018/de/de_50k.txt`
(https://github.com/hermitdave/FrequencyWords), built from OpenSubtitles 2018
(http://opus.nlpl.eu/OpenSubtitles2018.php).
**Licence:** CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/).
`lemmas.tsv` is a derived work and is therefore also licensed **CC BY-SA 4.0**
(the MIT licence of the rest of the repository does not apply to this file).

**Changes made:** the 40,000 most frequent word forms were lemmatised with spaCy
`de_core_news_sm` (each form on its own), proper nouns, interjections, numbers, foreign
words and common English were removed, counts of inflected forms were summed per lemma,
and some forms were mapped by hand (`server/scripts/build_freq.py`). The automatic result
is still noisy (some uncapitalised nouns, inflected forms, film-subtitle vocabulary);
the curated layers on top of it are `data/core-deck/` and `data/vocab-test/`.

Rebuild: download `de_50k.txt` to `~/kaskade-data/freq/`, then
`cd server && .venv/bin/python scripts/build_freq.py`.
