"""Optional tool plugins. Each one is disabled by default and configured under [plugins.<name>].

remote_agent: forwards a request to another assistant over a tiny HTTP contract.
    POST {url}/message   {"text": "...", "from": "jarvis", "wait": true}   (Bearer token if set)
    200                  {"reply": "one to three sentences to say aloud"}
  A timeout is not an error: the request was handed over and the answer will come another way.
"""
import os

import httpx

from .config import read_secret


def register_all(toolbox):
    if toolbox.cfg["plugins"]["remote_agent"]["enabled"]:
        _register_remote_agent(toolbox)


def _register_remote_agent(toolbox):
    c = toolbox.cfg["plugins"]["remote_agent"]

    def ask_remote_agent(request: str) -> str:
        key = os.environ.get(c["key_env"], "") or read_secret(c["key_file"])
        try:
            r = httpx.post(f"{c['url']}/message", json={"text": request, "from": "jarvis", "wait": True},
                           headers={"Authorization": f"Bearer {key}"} if key else {},
                           timeout=c["timeout_s"])
            r.raise_for_status()
            return r.json()["reply"]
        except httpx.TimeoutException:
            return "C'est transmis. Tu auras la réponse plus tard."
        except httpx.HTTPError:
            return "L'assistant distant est injoignable pour l'instant."

    toolbox.add("ask_remote_agent", c["description"],
                {"request": {"type": "string", "description": "La demande de l'utilisateur, complète et claire"}},
                ["request"], 1, ask_remote_agent, triggers=c["triggers"])
