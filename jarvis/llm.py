"""LLM backends. Both expose the same two methods, so the brain does not care which one it gets:

    settings() -> (model, extra_body)    choose the endpoint for this turn
    post(payload) -> message dict        one /chat/completions call, returns choices[0].message

HTTPBackend talks to any OpenAI-compatible server (llama.cpp's llama-server in the author's setup).
The offline FakeBackend lives in fake_llm.py.
"""
import httpx

from .config import read_secret

THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}


class HTTPBackend:
    def __init__(self, cfg: dict):
        self.cfg = cfg["llm"]
        self._url = self.cfg["url"]
        self._key = ""

    def _primary_key(self) -> str:
        return self.cfg["api_key"] or read_secret(self.cfg["key_file"])

    def settings(self) -> tuple[str, dict]:
        c = self.cfg
        self._url, self._key = c["url"], self._primary_key()
        model = c["model"]
        if c["fallback_url"] and self._use_fallback():
            self._url, self._key = c["fallback_url"], read_secret(c["fallback_key_file"])
            model = c["fallback_model"] or model
        return model, (THINKING_OFF if c["disable_thinking"] else {})

    def _use_fallback(self) -> bool:
        """True if the primary router is unreachable or has one of `busy_models` loaded.

        llama.cpp router mode: GET /models lists each model with its load status.
        """
        c = self.cfg
        try:
            r = httpx.get(c["url"].removesuffix("/v1") + "/models",
                          headers={"Authorization": f"Bearer {self._key}"}, timeout=1.5)
            loaded = {m["id"] for m in r.json()["data"] if m.get("status", {}).get("value") == "loaded"}
            return bool(loaded & set(c["busy_models"]))
        except (httpx.HTTPError, ValueError, KeyError):
            return True

    def post(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        r = httpx.post(f"{self._url}/chat/completions", headers=headers, timeout=120, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]
