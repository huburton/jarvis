"""Small text helpers shared by the brain, the speech layer and the demo (no heavy dependencies)."""
import datetime as dt
import re

_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"]


def fr_date(now: dt.datetime) -> str:
    """'mercredi 14 octobre 2026' without depending on the system locale."""
    return f"{_DAYS[now.weekday()]} {now.day} {_MONTHS[now.month - 1]} {now.year}"


def fr_datetime(now: dt.datetime) -> str:
    return f"{fr_date(now)}, {now:%H:%M}"


def for_voice(text: str, max_sentences: int = 3) -> str:
    """Spoken reply: drop trailing model notes and markdown, keep at most `max_sentences`."""
    text = re.split(r"\n\s*\*?(Note|Correction)\b", text)[0]
    sentences = re.split(r"(?<=[.!?…])\s+", text.replace("*", "").strip())
    return " ".join(sentences[:max_sentences]).strip()


def split_sentences(text: str) -> list[str]:
    """Split a reply into sentences for sentence-by-sentence synthesis (strips stray markdown)."""
    text = re.sub(r"[*_#`>]", "", text)
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]
