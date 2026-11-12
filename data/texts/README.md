# Lesebibliothek (graded reading)

Original short texts written for Kaskade (A2+/B1, everyday adult life in Germany).
No textbook, graded-reader, exam or news content.

**i+1 rule:** at least 95 % of the countable tokens (names and numbers excluded) are
among the first 2,000 core-deck words. Check with

    cd server && .venv/bin/python scripts/check_text.py ../data/texts/t01.json

(spaCy + `de_core_news_sm`, see `server/requirements-tools.txt`). The content tests
enforce the rule and require a glossary entry for every word outside the core.

Format (`tNN.json`): `id, origin ("ai" = written for Kaskade, shown as "KI-geschrieben";
"real" needs a `source`), title, level ("A2+"|"B1"), theme, slot ("input" = 09:30 with
glossary, "lesen" = 10:35 free reading), text (paragraphs separated by a blank line),
glossary [{term, gloss, note?}], questions [{question, options[3], correct}],
names [optional: names the tagger doesn't recognise]`.
