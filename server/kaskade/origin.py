"""Where content comes from: written for Kaskade by AI ("ai") or authentic German ("real", with a source).

The UI shows a "KI-geschrieben" badge for "ai" and the source for "real" (follow-up #16).
"""
AI = "ai"
REAL = "real"
ORIGINS = {AI, REAL}


def tag(item: dict) -> dict:
    """{origin, source} of a content item. Kaskade's own content is AI-written unless it says otherwise."""
    return {"origin": item.get("origin", AI), "source": item.get("source")}


def of_mined(source: str | None, media_title: str | None, library: dict[str, dict]) -> dict:
    """A mined sentence keeps the origin of where it came from.

    source: what the app stored ("Schauen · <clip>", "Satz-Check · <clip>", "Lesen · <text title>",
    "Eigener Text"); media_title: title of the clip it was cut from (if any); library: text title → item.
    """
    if media_title:
        return {"origin": REAL, "source": media_title}
    kind, _, rest = (source or "").partition(" · ")
    if kind in ("Schauen", "Satz-Check"):
        return {"origin": REAL, "source": rest or kind}
    if kind == "Eigener Text":
        return {"origin": REAL, "source": "Eigener Text"}
    if kind == "Lesen":
        text = library.get(rest)
        return tag(text) if text else {"origin": AI, "source": None}
    return {"origin": None, "source": source}
