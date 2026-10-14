"""Strict spoken confirmation (yes / no / unclear).

Negation always wins: "pas d'accord", "non vas-y", "ne l'envoie pas" all mean no.
Anything that is not an explicit yes without negation is treated as a refusal by the caller.
"""
import re
import unicodedata

_NEGATION = re.compile(
    r"\b(non|nan|pas|jamais|annule|annuler|annulez|arrete|arreter|stop|attends|attend|"
    r"laisse tomber|oublie|surtout pas|n'importe)\b|\bn'|\bne\b"
)
_YES = re.compile(
    r"\b(oui|ouais|ouai|ok|okay|d'accord|dac|vas-y|vas y|go|confirme|confirmer|confirmee?|"
    r"exact|exactement|c'est ca|bien sur|parfait|fais-le|fais le|allez|valide|valider|affirmatif)\b"
)


def _normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w' -]", " ", text)


def parse(text: str) -> str:
    """Return 'yes', 'no' or 'unclear'."""
    t = _normalize(text or "")
    if _NEGATION.search(t):
        return "no"
    if _YES.search(t):
        return "yes"
    return "unclear"


def question(level: int, what: str) -> str:
    """What Jarvis says before running a level 2 or 3 tool."""
    return f"Je vais {what}. " + ("Confirme en disant oui, je confirme." if level >= 3 else "Tu confirmes ?")


def accepted(level: int, answer: str) -> bool:
    """Is `answer` enough to run a tool of this permission level?

    Level 2: an explicit yes. Level 3: an explicit yes AND the word "confirme", no negation.
    """
    verdict = parse(answer)
    if level >= 3:
        return verdict == "yes" and "confirm" in answer.lower()
    return verdict == "yes"
