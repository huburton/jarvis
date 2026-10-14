"""Keyword router: does this request need a tool?

A small model without a reasoning phase tends to answer "from memory" (time, weather, music...).
When the request matches one of these patterns the brain forces a tool-choice step, constrained
by a JSON grammar, instead of letting the model free-wheel. Matching is done on lowercase text
with accents stripped.
"""
import re
import unicodedata

BASE_TRIGGERS = (
    r"meteo|temps qu.il fait|quel temps|pleu|neig|temperature|degres|quelle heure|heure est|quel jour|la date|"
    r"musique|chanson|morceau|pause|reprend|suivant|precedent|volume|le son|monte|baisse|"
    r"ouvre|lance|demarre|workspace|bureau \d|rappel|rappelle|minuteur|timer|dans \d+ (min|h|sec)|"
    r"note|noter|tache|todo|verrouill|eteins|eteindre|redemarr|"
    r"veille|etat du pc|processeur|cpu|gpu|memoire|carte graphique|ecoute|joue"
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def compile_triggers(extra: tuple[str, ...] = ()) -> re.Pattern:
    """Base patterns plus the ones contributed by enabled plugins."""
    return re.compile("|".join(p for p in (BASE_TRIGGERS, *extra) if p))


_DEFAULT = compile_triggers()


def needs_tool(text: str, pattern: re.Pattern = _DEFAULT) -> bool:
    return bool(pattern.search(strip_accents(text)))
