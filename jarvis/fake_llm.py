"""Offline stand-in for the LLM server, used by the demo and the tests.

It implements the same `settings()` / `post(payload)` interface as llm.HTTPBackend and answers the
three kinds of request the brain makes, with the same shapes a real server returns:

  * constrained tool choice (payload has `response_format`): a keyword/regex router returns the
    JSON `{"tool": ..., "args": {...}}` document the grammar would force;
  * rewording of a tool result (`tool_choice == "none"`): returns the tool result unchanged;
  * free chat: a handful of canned replies.

It is a router, not a language model: it only understands the phrases listed in RULES.
"""
import json
import re

from .router import strip_accents


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _timer(m: re.Match, text: str):
    value, unit = _num(m.group(1)), m.group(2)
    minutes = value * 60 if unit.startswith("h") else value / 60 if unit.startswith("s") else value
    args: dict = {"minutes": max(minutes, 0.1)}
    label = re.search(r"(?:minutes?|min|heures?|h|secondes?)\s+(?:de |d'|pour |que )(.+)", text, re.I)
    if label:
        args["label"] = label.group(1).strip(" .!?")
    return "set_timer", args


def _weather(m: re.Match, text: str):
    args: dict = {}
    if "demain" in text.lower():
        args["day"] = "tomorrow"
    city = re.search(r"\b(?:à|a|pour|de)\s+([A-ZÉÈ][\w'-]+(?:[ -][A-ZÉÈ][\w'-]+)*)", text)
    if city:
        args["city"] = city.group(1)
    return "get_weather", args


def _volume(m: re.Match, text: str):
    n = strip_accents(text)
    if re.search(r"coupe le son|\bmute\b|silence", n):
        return "set_volume", {"mute": True}
    if re.search(r"retablis|remets le son|reactive|reactiver", n):
        return "set_volume", {"mute": False}
    pct = re.search(r"(\d{1,3})", n)
    if pct:
        return "set_volume", {"percent": min(int(pct.group(1)), 100)}
    return "answer", {"text": "À combien tu veux le volume ?"}


def _media(action: str):
    return lambda m, text: ("media_control", {"action": action})


def _power(m: re.Match, text: str):
    n = strip_accents(text)
    action = "reboot" if "redemarr" in n else "suspend" if "veille" in n else "shutdown"
    return "power", {"action": action}


def _tail(tool: str, key: str, pattern: str):
    def build(m: re.Match, text: str):
        found = re.search(pattern, text, re.I)
        return tool, {key: (found.group(1) if found else text).strip(" .!?")}
    return build


# (pattern on lowercase accent-free text, builder(match, original_text) -> (tool, args)); first match wins.
RULES: list[tuple[str, object]] = [
    (r"eteins|eteindre|redemarr|en veille|mets? .*veille", _power),
    (r"verrouill", lambda m, t: ("lock_screen", {})),
    (r"(?:minuteur|timer|rappel|rappelle).*?(\d+(?:[.,]\d+)?)\s*(h|heure|min|minute|sec|seconde)", _timer),
    (r"quel morceau|quelle chanson|quelle musique|qu.est.ce qui passe|c.est quoi cette", lambda m, t: ("now_playing", {})),
    (r"suivant|prochain|\bnext\b|saute", _media("next")),
    (r"precedent|reviens en arriere", _media("previous")),
    (r"pause|(arrete|stop) la musique", _media("pause")),
    (r"reprend|\bplay\b|joue de la musique|(lance|remets?) la musique", _media("play")),
    (r"volume|le son\b", _volume),
    (r"gpu|cpu|processeur|etat du pc|vram|memoire|carte graphique", lambda m, t: ("system_status", {})),
    (r"quelle heure|heure est|quel jour|la date|on est quel", lambda m, t: ("get_datetime", {})),
    (r"meteo|quel temps|temps qu.il fait|pleu|neig|temperature|degres", _weather),
    (r"(?:workspace|bureau)\s*(\d+)", lambda m, t: ("switch_workspace", {"number": int(m.group(1))})),
    (r"\bnotes?\b|\bnoter\b", _tail("take_note", "text", r"(?:note|noter)(?:[- ]moi)?\s*(?:que|ceci|ça|:)?\s*(.+)")),
    (r"tache|todo", _tail("add_task", "title", r"t[aâ]che\s*(?::|de |d'|pour )?\s*(.+)")),
    (r"cherche|recherche|demande a l.agent|occupe.toi|delegue", lambda m, t: ("ask_remote_agent", {"request": t})),
    (r"(?:ouvre|lance|demarre)\s+", _tail("open_app", "name",
        r"(?:ouvre|lance|démarre|demarre)\s+(?:l'application |l'app |le |la |les |l')?(.+)")),
]

CHAT = [
    (r"bonjour|salut|coucou|\bhello\b", "Salut ! Dis-moi ce que je peux faire pour toi."),
    (r"merci", "Avec plaisir."),
    (r"qui es.tu|tu es qui|ton nom", "Je suis Jarvis, ton assistant vocal local. Ici, je tourne sans vrai modèle, "
     "avec un routeur à mots-clés."),
    (r"blague", "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que sinon ils tombent dans le bateau."),
    (r"\baide\b|sais.tu faire|tu sais faire", "Je donne l'heure et la météo, je pilote la musique et le volume, "
     "j'ouvre des applications, je règle des minuteurs et je prends des notes."),
]
FALLBACK_CHAT = ("Dans cette démo hors ligne, je ne réponds qu'à quelques phrases types. "
                 "Branche un vrai serveur avec JARVIS_LLM_URL pour une vraie conversation.")
NOT_UNDERSTOOD = "Je n'ai pas bien compris, tu peux reformuler ?"


class FakeBackend:
    def settings(self) -> tuple[str, dict]:
        return "fake-router", {}

    def post(self, payload: dict) -> dict:
        if payload.get("response_format"):
            return {"content": self._json(self._pick(payload))}
        if payload.get("tool_choice") == "none":
            results = [m["content"] for m in payload["messages"] if m["role"] == "tool"]
            return {"content": results[-1] if results else ""}
        return {"content": self._chat(self._user_text(payload))}

    @staticmethod
    def _json(action: dict) -> str:
        return json.dumps(action, ensure_ascii=False)

    @staticmethod
    def _user_text(payload: dict) -> str:
        users = [m["content"] for m in payload["messages"] if m["role"] == "user"]
        return users[-1] if users else ""

    def _pick(self, payload: dict) -> dict:
        available = {o["properties"]["tool"]["const"]
                     for o in payload["response_format"]["json_schema"]["schema"]["anyOf"]}
        text = self._user_text(payload)
        norm = strip_accents(text)
        for pattern, build in RULES:
            m = re.search(pattern, norm)
            if m:
                tool, args = build(m, text)
                if tool in available:
                    return {"tool": tool, "args": args}
        return {"tool": "answer", "args": {"text": NOT_UNDERSTOOD}}

    @staticmethod
    def _chat(text: str) -> str:
        norm = strip_accents(text)
        for pattern, reply in CHAT:
            if re.search(pattern, norm):
                return reply
        return FALLBACK_CHAT
