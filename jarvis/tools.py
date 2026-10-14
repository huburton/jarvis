"""Jarvis tools.

Permission levels: 1 = runs directly, 2 = spoken confirmation ("Tu confirmes ?"),
3 = strict confirmation (the user must say "oui, je confirme").
No tool runs a free-form command: every action goes through a program and arguments fixed here
(apps are limited to installed .desktop entries).
"""
import configparser
import datetime as dt
import difflib
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from .textutil import fr_datetime


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    level: int
    func: Callable
    announce: Callable[[dict], str] | None = None  # sentence spoken before asking for confirmation
    direct: bool = True   # the tool result is spoken as is (actions); False = reworded by the LLM (info)
    triggers: str = ""    # extra router regex (accent-free, lowercase) that should force this tool

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


class Toolbox:
    def __init__(self, cfg: dict, say: Callable[[str], None]):
        self.cfg = cfg
        self.say = say  # used by timers
        self.tools: dict[str, Tool] = {}
        self._register()
        self._register_plugins()

    # ------------------------------------------------------------------ helpers
    def add(self, name, description, properties, required, level, func, announce=None, direct=True, triggers=""):
        self.tools[name] = Tool(name, description, {
            "type": "object", "properties": properties, "required": required}, level, func,
            announce, direct, triggers)

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    @staticmethod
    def _run(*cmd: str, timeout: float = 5) -> str:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr).strip()

    # ------------------------------------------------------------------ registry
    def _register(self):
        add = self.add
        add("get_datetime", "Heure, date, jour de la semaine.", {}, [], 1, self.get_datetime, direct=False)
        add("get_weather", "Météo actuelle, du jour ou de demain (par défaut dans la ville configurée).",
            {"city": {"type": "string", "description": "Ville, facultatif"},
             "day": {"type": "string", "enum": ["today", "tomorrow"]}}, [], 1, self.get_weather, direct=False)
        add("media_control", "Contrôle la musique / vidéo en cours (Spotify, navigateur…).",
            {"action": {"type": "string", "enum": ["play_pause", "play", "pause", "next", "previous"]}},
            ["action"], 1, self.media_control)
        add("now_playing", "Quel morceau / quelle musique passe en ce moment.", {}, [], 1, self.now_playing,
            direct=False)
        add("set_volume", "Règle le volume de sortie en pourcentage, ou coupe / rétablit le son.",
            {"percent": {"type": "integer", "minimum": 0, "maximum": 100},
             "mute": {"type": "boolean"}}, [], 1, self.set_volume)
        add("open_app", "Ouvre une application installée (par son nom).",
            {"name": {"type": "string"}}, ["name"], 1, self.open_app)
        add("switch_workspace", "Va sur le bureau / workspace N (1 à 10).",
            {"number": {"type": "integer", "minimum": 1, "maximum": 10}}, ["number"], 1, self.switch_workspace)
        add("set_timer", "Minuteur ou rappel dans X minutes / heures (« rappelle-moi dans… », "
            "« mets un minuteur »). Prévient à voix haute et par notification.",
            {"minutes": {"type": "number", "minimum": 0.1, "maximum": 1440},
             "label": {"type": "string", "description": "Ce qu'il faut rappeler"}},
            ["minutes"], 1, self.set_timer)
        add("system_status", "État du PC : charge processeur, mémoire, carte graphique (GPU), VRAM, "
            "température.", {}, [], 1, self.system_status, direct=False)
        add("take_note", "Note une idée / information dans le dossier de notes.",
            {"text": {"type": "string"}}, ["text"], 1, self.take_note)
        add("add_task", "Ajoute une tâche à faire (sans heure) à la liste de tâches.",
            {"title": {"type": "string"}}, ["title"], 2, self.add_task,
            lambda a: f"ajouter la tâche « {a.get('title', '')} »")
        add("lock_screen", "Verrouille la session.", {}, [], 2, self.lock_screen, lambda a: "verrouiller la session")
        add("power", "Éteindre, redémarrer ou mettre en veille le PC.",
            {"action": {"type": "string", "enum": ["shutdown", "reboot", "suspend"]}},
            ["action"], 3, self.power,
            lambda a: {"shutdown": "éteindre le PC", "reboot": "redémarrer le PC",
                       "suspend": "mettre le PC en veille"}.get(a.get("action"), "?"))

    def _register_plugins(self):
        from . import plugins
        plugins.register_all(self)

    # ------------------------------------------------------------------ tools
    def get_datetime(self) -> str:
        return fr_datetime(dt.datetime.now().astimezone())

    def get_weather(self, city: str = "", day: str = "today") -> str:
        w = self.cfg["weather"]
        lat, lon, name = w["lat"], w["lon"], w["city"]
        if city and _norm(city) != _norm(name):
            g = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                          params={"name": city, "count": 1, "language": "fr"}, timeout=5).json()
            if not g.get("results"):
                return f"Ville introuvable : {city}"
            r = g["results"][0]
            lat, lon, name = r["latitude"], r["longitude"], r["name"]
        d = httpx.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        }, timeout=5).json()
        c, daily = d["current"], d["daily"]
        i = 1 if day == "tomorrow" else 0
        forecast = (f"{'Demain' if i else 'Aujourd hui'} : {WMO.get(daily['weather_code'][i], 'variable')}, "
                    f"{round(daily['temperature_2m_min'][i])} à {round(daily['temperature_2m_max'][i])}°C, "
                    f"risque de pluie {daily['precipitation_probability_max'][i]}%.")
        if i:
            return f"{name} — {forecast}"
        return (f"{name} maintenant : {round(c['temperature_2m'])}°C (ressenti {round(c['apparent_temperature'])}°C), "
                f"{WMO.get(c['weather_code'], 'temps variable')}, vent {round(c['wind_speed_10m'])} km/h. {forecast}")

    def media_control(self, action: str) -> str:
        cmd = {"play_pause": "play-pause", "play": "play", "pause": "pause",
               "next": "next", "previous": "previous"}[action]
        out = self._run("playerctl", cmd)
        return "Aucun lecteur actif." if "No players" in out else "Fait."

    def now_playing(self) -> str:
        out = self._run("playerctl", "metadata", "--format", "{{artist}} — {{title}} ({{status}})")
        return "Rien en lecture." if not out or "No players" in out else out

    def set_volume(self, percent: int | None = None, mute: bool | None = None) -> str:
        if mute is not None:
            self._run("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if mute else "0")
        if percent is not None:
            self._run("wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{int(percent)}%")
        out = self._run("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")  # "Volume: 0.40 [MUTED]"
        m = re.search(r"([\d.]+)", out)
        level = f"Volume à {round(float(m.group(1)) * 100)} %" if m else "Volume réglé"
        return level + (", son coupé." if "MUTED" in out else ".")

    def open_app(self, name: str) -> str:
        apps = _desktop_apps()
        best = match_app(name, apps)
        if not best:
            return f"Aucune application ne correspond à « {name} »."
        subprocess.Popen(["gtk-launch", best], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return f"Lancé : {apps[best][0]}"

    def switch_workspace(self, number: int) -> str:
        self._run(*self.cfg["desktop"]["workspace_command"], str(int(number)))
        return f"Workspace {number}."

    def set_timer(self, minutes: float, label: str = "") -> str:
        text = label or f"{minutes:g} minutes écoulées"

        def fire():
            subprocess.run(["notify-send", "-a", "Jarvis", "-u", "critical", "Rappel", text])
            self.say(f"Rappel : {text}")
        t = threading.Timer(minutes * 60, fire)
        t.daemon = True
        t.start()
        due = (dt.datetime.now() + dt.timedelta(minutes=minutes)).strftime("%H:%M")
        return f"Minuteur réglé pour {due}."

    def system_status(self) -> str:
        load1 = os.getloadavg()[0]
        mem = dict(re.findall(r"^(\w+):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M))
        used = (int(mem["MemTotal"]) - int(mem["MemAvailable"])) / 1048576
        out = f"Charge CPU {load1:.1f}, mémoire {used:.1f} Go sur {int(mem['MemTotal']) / 1048576:.0f} Go."
        gpu = self._run("nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                        "--format=csv,noheader,nounits")
        if gpu and "," in gpu:
            u, mu, mt, t = [x.strip() for x in gpu.split(",")]
            out += f" GPU {u}%, {int(mu) / 1024:.1f} Go de VRAM sur {int(mt) / 1024:.0f}, {t}°C."
        return out

    def _notes_dir(self) -> Path:
        d = Path(self.cfg["notes"]["dir"]).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def take_note(self, text: str) -> str:
        now = dt.datetime.now()
        path = self._notes_dir() / f"{now:%Y-%m-%d-%H%M%S}-jarvis.md"
        path.write_text(f"---\nsource: jarvis\ncreated: {now:%Y-%m-%dT%H:%M:%S}\n---\n\n{text.strip()}\n")
        return "Noté."

    def add_task(self, title: str) -> str:
        with (self._notes_dir() / "tasks.md").open("a") as f:
            f.write(f"- [ ] {title.strip()}\n")
        return "Tâche ajoutée."

    def lock_screen(self) -> str:
        self._run(*self.cfg["desktop"]["lock_command"])
        return "Session verrouillée."

    def power(self, action: str) -> str:
        cmd = {"shutdown": "poweroff", "reboot": "reboot", "suspend": "suspend"}[action]
        threading.Timer(3, lambda: subprocess.run(["systemctl", cmd])).start()
        return {"shutdown": "Extinction dans 3 secondes.", "reboot": "Redémarrage dans 3 secondes.",
                "suspend": "Mise en veille."}[action]

    # ------------------------------------------------------------------ dispatch
    def call(self, name: str, args: dict) -> str:
        tool = self.tools.get(name)
        if not tool:
            return f"Outil inconnu : {name}"
        try:
            return str(tool.func(**args))
        except TypeError as e:
            return f"Arguments invalides : {e}"
        except Exception as e:  # network, missing command...: Jarvis says so instead of crashing
            return f"Échec : {e}"


# ---------------------------------------------------------------------- utils
def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def match_app(name: str, apps: dict[str, list[str]], threshold: float = 0.6) -> str | None:
    """Best fuzzy match of a spoken app name among {desktop_id: [normalised labels...]}."""
    target = _norm(name)
    best, score = None, 0.0
    for app_id, labels in apps.items():
        for label in labels:
            s = difflib.SequenceMatcher(None, target, label).ratio()
            if target in label.split() or label == target:
                s = max(s, 0.95)
            if s > score:
                best, score = app_id, s
    return best if best and score >= threshold else None


_APPS_CACHE: tuple[float, dict] = (0.0, {})


def _desktop_apps() -> dict[str, list[str]]:
    """{desktop_id: [normalised names...]} for the apps visible in the launcher (cached 5 min)."""
    global _APPS_CACHE
    if time.time() - _APPS_CACHE[0] < 300:
        return _APPS_CACHE[1]
    dirs = [Path.home() / ".local/share/applications", Path("/usr/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications")]
    apps: dict[str, list[str]] = {}
    for d in reversed(dirs):  # user entries override system ones
        for f in d.glob("*.desktop") if d.is_dir() else []:
            p = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                p.read(f, encoding="utf-8")
                e = p["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if e.get("NoDisplay", "false").lower() == "true" or e.get("Type") != "Application":
                apps.pop(f.stem, None)
                continue
            labels = [e.get("Name[fr]") or e.get("Name", ""), e.get("Name", ""), e.get("GenericName[fr]", ""),
                      e.get("GenericName", "")] + e.get("Keywords", "").split(";")
            apps[f.stem] = [n for n in dict.fromkeys(_norm(x) for x in labels) if n]
    _APPS_CACHE = (time.time(), apps)
    return apps


WMO = {0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert", 45: "brouillard",
       48: "brouillard givrant", 51: "bruine légère", 53: "bruine", 55: "bruine forte", 61: "pluie faible",
       63: "pluie", 65: "forte pluie", 66: "pluie verglaçante", 67: "pluie verglaçante forte",
       71: "neige faible", 73: "neige", 75: "forte neige", 77: "grésil", 80: "averses", 81: "averses",
       82: "fortes averses", 85: "averses de neige", 86: "fortes averses de neige", 95: "orage",
       96: "orage avec grêle", 99: "orage violent avec grêle"}

if __name__ == "__main__":  # quick manual check: python -m jarvis.tools
    from jarvis import config
    tb = Toolbox(config.load(), print)
    print(json.dumps([t["function"]["name"] for t in tb.schemas()]))
    print(tb.get_datetime())
    print(tb.system_status())
