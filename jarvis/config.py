"""Configuration: neutral defaults, overridden by a TOML file and by environment variables.

Precedence (lowest to highest): DEFAULTS < config.toml < environment variables.

Config file: $JARVIS_CONFIG, else ~/.config/jarvis/config.toml. See config.example.toml.
Environment overrides: JARVIS_LLM_URL, JARVIS_LLM_MODEL, JARVIS_LLM_KEY, JARVIS_TTS_VOICE,
JARVIS_NOTES_DIR.
"""
import copy
import os
import tomllib
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("JARVIS_CONFIG") or Path.home() / ".config" / "jarvis" / "config.toml")
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "jarvis"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "jarvis"

DEFAULTS = {
    # openWakeWord ships an English "hey_jarvis" model. A single frame above the threshold
    # fires on TV audio, so we also require `patience` consecutive frames.
    "wake": {"model": "hey_jarvis", "threshold": 0.5, "patience": 2},
    "audio": {
        "device": "",            # PortAudio device name; empty = system default
        "silence_ms": 800,       # end of utterance after this much silence
        "max_utterance_s": 15,
        "start_timeout_s": 6,    # time allowed to start speaking after the wake word
        "followup_s": 6,         # keep listening without a wake word after a reply...
        "followup_only_after_question": True,  # ...but only if Jarvis just asked a question
        "chime": "/usr/share/sounds/freedesktop/stereo/message.oga",  # empty = no chime
    },
    "stt": {
        "model": "large-v3-turbo",
        "device": "cpu",         # keep the GPU free for the LLM
        "compute_type": "int8",
        "threads": 8,
        "prompt": "Jarvis, Hyprland, workspace, Spotify.",  # vocabulary hint for Whisper
    },
    "tts": {
        "voice": "~/.local/share/piper/fr_FR-tom-medium.onnx",
        "length_scale": 1.0,
    },
    "llm": {
        # Any OpenAI-compatible server that supports `response_format: json_schema`
        # (llama.cpp's llama-server does).
        "url": "http://127.0.0.1:8080/v1",
        "model": "local",
        "api_key": "",
        "key_file": "",          # read the key from a file instead (used if api_key is empty)
        # Optional second endpoint, used when one of `busy_models` is loaded on the primary
        # llama.cpp router (so a small voice model does not evict a big one). Empty = disabled.
        "fallback_url": "",
        "fallback_model": "",
        "fallback_key_file": "",
        "busy_models": [],
        "disable_thinking": True,   # voice latency: no reasoning phase (Qwen-style templates)
        "history_turns": 6,
        "history_ttl_s": 180,
    },
    "weather": {"city": "Paris", "lat": 48.85, "lon": 2.35},   # Open-Meteo, no API key
    "desktop": {
        "lock_command": ["loginctl", "lock-session"],
        "workspace_command": ["hyprctl", "dispatch", "workspace"],
    },
    "notes": {"dir": "~/Documents/jarvis-notes"},  # `take_note` and `add_task` write here
    "plugins": {
        # Optional tool that forwards a request to another agent over HTTP. Off by default.
        "remote_agent": {
            "enabled": False,
            "url": "",                      # POST {url}/message
            "key_file": "",
            "key_env": "JARVIS_REMOTE_KEY",
            "timeout_s": 45,
            "description": "Forward the request to a more capable remote assistant: research, "
                           "analysis, long-running tasks, anything the other tools cannot do.",
            "triggers": r"cherche|recherche|demande a l.agent|occupe.toi|delegue",
        },
    },
}

_ENV_OVERRIDES = {
    "JARVIS_LLM_URL": ("llm", "url"),
    "JARVIS_LLM_MODEL": ("llm", "model"),
    "JARVIS_LLM_KEY": ("llm", "api_key"),
    "JARVIS_TTS_VOICE": ("tts", "voice"),
    "JARVIS_NOTES_DIR": ("notes", "dir"),
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: Path | None = None, env: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    path = path or CONFIG_FILE
    if path.is_file():
        with path.open("rb") as f:
            cfg = _merge(cfg, tomllib.load(f))
    env = os.environ if env is None else env
    for var, (section, key) in _ENV_OVERRIDES.items():
        if env.get(var):
            cfg[section][key] = env[var]
    return cfg


def read_secret(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).expanduser().read_text().strip()
    except OSError:
        return ""
