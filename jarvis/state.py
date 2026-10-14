"""State published for UI widgets (a status bar, a panel...): $XDG_RUNTIME_DIR/jarvis/state.json.

States: idle, listening, thinking, speaking, confirm. History: $XDG_STATE_HOME/jarvis/history.jsonl.
"""
import json
import time

from .config import RUNTIME_DIR, STATE_DIR


class State:
    def __init__(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._file = RUNTIME_DIR / "state.json"
        self._data = {"state": "idle", "heard": "", "reply": "", "muted": False}
        self.set("idle")

    def set(self, state: str, **fields):
        self._data.update(fields, state=state, ts=time.time())
        # Write in place (no rename): file watchers such as Quickshell's FileView follow the original inode
        self._file.write_text(json.dumps(self._data, ensure_ascii=False))

    @property
    def current(self) -> str:
        return self._data["state"]

    @property
    def muted(self) -> bool:
        return self._data["muted"]

    def log(self, heard: str, reply: str):
        with (STATE_DIR / "history.jsonl").open("a") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "heard": heard, "reply": reply},
                               ensure_ascii=False) + "\n")
