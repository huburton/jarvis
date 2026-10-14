"""Conversation loop: LLM (OpenAI-compatible API) with tool calls.

Two paths per turn:
  1. The request matches the keyword router (router.py): the tool choice is forced through a
     JSON-schema-constrained completion, so the model cannot invent an action or loop. Action
     tools report their exact result; information tools get one short rewording pass.
  2. Anything else: a classic tool-calling loop where tools are optional.
Tools of permission level 2 and 3 go through a `confirm(tool, args) -> bool` callback first.
"""
import datetime as dt
import json
import time

from . import router
from .textutil import for_voice, fr_datetime

SYSTEM = """Tu es Jarvis, l'assistant vocal de l'utilisateur sur son PC Linux.
Tu le tutoies et tu lui parles directement. Tu parles français, à l'oral : réponses courtes (1 à 3 phrases), sans markdown, sans liste, sans emoji,
nombres écrits simplement. Ton : direct, un peu d'humour sec, jamais obséquieux.
Maintenant : {now}. L'utilisateur habite à {city}.
Tu n'as AUCUNE information en temps réel (météo, heure, musique, état du PC) sans outil :
pour ces sujets et pour toute action, appelle l'outil correspondant, puis réponds d'après son résultat
exact (ne modifie jamais les chiffres). N'annonce jamais une action comme faite sans le résultat de l'outil.
Si la demande est ambiguë, pose une seule question courte.
Pour une question générale, réponds directement et brièvement. Ne termine pas par une question de relance."""


def build_action_schema(tools) -> dict:
    """JSON schema for the constrained tool choice.

    The model must output {"tool": <name>, "args": {...}} where args match that tool's own
    parameter schema, or {"tool": "answer", "args": {"text": ...}} to reply without a tool.
    """
    options = [{"type": "object", "required": ["tool", "args"], "properties": {
        "tool": {"const": "answer"},
        "args": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}}}]
    for t in tools:
        options.append({"type": "object", "required": ["tool", "args"], "properties": {
            "tool": {"const": t.name}, "args": t.parameters}})
    return {"anyOf": options}


class Brain:
    CANCELLED = "D'accord, j'annule."

    def __init__(self, cfg: dict, toolbox, backend):
        self.cfg = cfg["llm"]
        self.city = cfg["weather"]["city"]
        self.toolbox = toolbox
        self.backend = backend
        self.history: list[dict] = []
        self._last = 0.0
        self._triggers = router.compile_triggers(tuple(t.triggers for t in toolbox.tools.values() if t.triggers))

    def reset_if_stale(self):
        if time.monotonic() - self._last > self.cfg["history_ttl_s"]:
            self.history = []

    def _run_tool(self, name: str, args: dict, confirm) -> str:
        tool = self.toolbox.tools.get(name)
        if tool and tool.level >= 2 and not confirm(tool, args):
            return self.CANCELLED
        return self.toolbox.call(name, args)

    def turn(self, user_text: str, confirm) -> str:
        """One conversation turn. `confirm(tool, args) -> bool` asks permission for level 2/3 tools."""
        self.reset_if_stale()
        self.history.append({"role": "user", "content": user_text})
        model, extra = self.backend.settings()
        now = fr_datetime(dt.datetime.now().astimezone())
        system = {"role": "system", "content": SYSTEM.format(now=now, city=self.city)}
        messages = [system] + self.history
        # presence_penalty: without it, Qwen3.5 without reasoning sometimes loops in its own text
        base = {"model": model, "temperature": 0.3, "presence_penalty": 1.5, **extra}
        tools = self.toolbox.schemas()
        reply = ""

        if router.needs_tool(user_text, self._triggers):
            # 1) Tool choice, guaranteed well-formed by the JSON grammar (short context: last 2 exchanges).
            menu = "\n".join(f"- {t.name} : {t.description}" for t in self.toolbox.tools.values())
            pick = self.backend.post({**base, "temperature": 0, "max_tokens": 300,
                "messages": [system] + self.history[-3:] + [  # the previous exchange is enough for "and tomorrow?"
                {"role": "system", "content": "Choisis l'outil qui réalise la dernière demande de l'utilisateur, avec ses "
                 f"arguments, ou « answer » avec ta réponse si aucun ne convient. Outils :\n{menu}\nJSON uniquement."}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "action", "schema": build_action_schema(self.toolbox.tools.values())}}})
            try:
                action = json.loads(pick.get("content") or "{}")
            except json.JSONDecodeError:
                action = {}
            name, args = action.get("tool"), action.get("args") or {}
            if name == "answer":
                reply = for_voice(args.get("text", ""))
            elif name in self.toolbox.tools:
                result = self._run_tool(name, args, confirm)
                if result == self.CANCELLED or self.toolbox.tools[name].direct:
                    reply = result  # actions: say the exact result, no rewording
            if name in self.toolbox.tools and not reply:
                call = {"id": "call0", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
                messages += [{"role": "assistant", "content": "", "tool_calls": [call]},
                             {"role": "tool", "tool_call_id": "call0", "content": result}]
                # 2) Information tools: spoken rewording, faithful to the result.
                messages.append({"role": "system", "content": "Donne ce résultat à l'utilisateur en une ou deux phrases "
                                 "naturelles, sans rien ajouter ni modifier les chiffres."})
                msg = self.backend.post({**base, "max_tokens": 200, "messages": messages,
                                         "tools": tools, "tool_choice": "none"})
                reply = for_voice(msg.get("content") or result, 2)
        if not reply:
            # General question (or failed tool choice): classic loop, tools optional.
            for _ in range(3):
                msg = self.backend.post({**base, "max_tokens": 1200, "messages": messages,
                                         "tools": tools, "tool_choice": "auto"})
                calls = msg.get("tool_calls") or []
                if not calls:
                    reply = for_voice(msg.get("content") or "")
                    break
                messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
                for call in calls:
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    messages.append({"role": "tool", "tool_call_id": call.get("id", "call"),
                                     "content": self._run_tool(call["function"]["name"], args, confirm)})
            else:
                reply = "Je tourne en rond, je préfère m'arrêter là."
        self.history.append({"role": "assistant", "content": reply})
        self.history = self.history[-2 * self.cfg["history_turns"]:]
        self._last = time.monotonic()
        return reply
