"""Text demo: the full brain (router, JSON-grammar tool choice, permissions, confirmation) with no
microphone, no GPU and no LLM server.

By default the LLM is the keyword router in fake_llm.py and the tools are safe stubs: time is real,
weather is mocked, notes go to a temporary directory, and anything that would touch the desktop
(music, volume, apps, lock, power) is printed instead of executed.
"""
import datetime as dt
import sys
import tempfile
from collections.abc import Callable

from . import confirm
from .brain import Brain
from .tools import Toolbox, _norm, match_app

BANNER = """Jarvis text demo (offline: fake LLM router, stub tools). Nothing is executed.
Try: "quelle heure est-il ?", "quel temps demain ?", "mets le volume à 30",
     "note que le dentiste est jeudi", "verrouille la session", "éteins le PC". Type "quit" to leave."""

DEMO_APPS = {"firefox": ["firefox", "navigateur web"], "org.gnome.Terminal": ["terminal", "console"],
             "spotify": ["spotify", "musique"], "org.gnome.Nautilus": ["fichiers", "files"]}
DEMO_APP_LABELS = {"firefox": "Firefox", "org.gnome.Terminal": "Terminal", "spotify": "Spotify",
                   "org.gnome.Nautilus": "Fichiers"}


class DemoToolbox(Toolbox):
    """Same registry, schemas and permission levels as Toolbox; side effects replaced by prints."""

    def __init__(self, cfg: dict, say: Callable[[str], None], out: Callable[[str], None] = print):
        self.out = out
        self.volume, self.muted, self.playing = 40, False, True
        super().__init__(cfg, say)

    def stub(self, text: str):
        self.out(f"  [demo] {text}")

    def call(self, name: str, args: dict) -> str:
        tool = self.tools.get(name)
        if tool:
            kind = {1: "direct", 2: "needs confirmation", 3: "needs strict confirmation"}[tool.level]
            self.out(f"  [tool] {name} {args}  (level {tool.level}, {kind})")
        return super().call(name, args)

    def get_weather(self, city: str = "", day: str = "today") -> str:
        name = city or self.cfg["weather"]["city"]
        self.stub("weather is mocked")
        if day == "tomorrow":
            return f"{name} — Demain : pluie faible, 8 à 13°C, risque de pluie 70%."
        return (f"{name} maintenant : 14°C (ressenti 12°C), partiellement nuageux, vent 11 km/h. "
                "Aujourd hui : partiellement nuageux, 9 à 16°C, risque de pluie 20%.")

    def media_control(self, action: str) -> str:
        self.playing = {"pause": False, "play": True, "play_pause": not self.playing}.get(action, True)
        self.stub(f"would run: playerctl {action.replace('_', '-')}")
        return "Fait."

    def now_playing(self) -> str:
        return f"Daft Punk — Around the World ({'Playing' if self.playing else 'Paused'})"

    def set_volume(self, percent: int | None = None, mute: bool | None = None) -> str:
        if percent is not None:
            self.volume = int(percent)
            self.stub(f"would run: wpctl set-volume @DEFAULT_AUDIO_SINK@ {self.volume}%")
        if mute is not None:
            self.muted = mute
            self.stub(f"would run: wpctl set-mute @DEFAULT_AUDIO_SINK@ {int(mute)}")
        return f"Volume à {self.volume} %" + (", son coupé." if self.muted else ".")

    def open_app(self, name: str) -> str:
        best = match_app(name, {k: [_norm(x) for x in v] for k, v in DEMO_APPS.items()})
        if not best:
            return f"Aucune application ne correspond à « {name} »."
        self.stub(f"would run: gtk-launch {best}")
        return f"Lancé : {DEMO_APP_LABELS[best]}"

    def switch_workspace(self, number: int) -> str:
        self.stub(f"would run: {' '.join(self.cfg['desktop']['workspace_command'])} {int(number)}")
        return f"Workspace {number}."

    def set_timer(self, minutes: float, label: str = "") -> str:
        due = (dt.datetime.now() + dt.timedelta(minutes=minutes)).strftime("%H:%M")
        self.stub(f"would schedule a notification + spoken reminder in {minutes:g} min ({label or 'no label'})")
        return f"Minuteur réglé pour {due}."

    def system_status(self) -> str:
        self.stub("system status is mocked")
        return "Charge CPU 0.8, mémoire 9.1 Go sur 32 Go. GPU 3%, 2.4 Go de VRAM sur 16, 41°C."

    def lock_screen(self) -> str:
        self.stub(f"would run: {' '.join(self.cfg['desktop']['lock_command'])}")
        return "Session verrouillée."

    def power(self, action: str) -> str:
        cmd = {"shutdown": "poweroff", "reboot": "reboot", "suspend": "suspend"}[action]
        self.stub(f"would run: systemctl {cmd} (after 3 s)")
        return {"shutdown": "Extinction dans 3 secondes.", "reboot": "Redémarrage dans 3 secondes.",
                "suspend": "Mise en veille."}[action]


def repl(brain: Brain, input_fn: Callable[[], str] = input, out: Callable[[str], None] = print,
         echo: bool = False) -> None:
    """Read requests until EOF or "quit". `echo` repeats each input line (for piped, non-tty input)."""
    def read() -> str | None:
        print("you> ", end="", flush=True)
        try:
            line = input_fn()
        except EOFError:
            print()
            return None
        if echo:
            print(line)
        return line.strip()

    def ask(tool, args) -> bool:
        what = tool.announce(args) if tool.announce else tool.name
        out(f"Jarvis: {confirm.question(tool.level, what)}")
        answer = read() or ""
        ok = confirm.accepted(tool.level, answer)
        out(f"  [confirm] heard {answer!r} -> {confirm.parse(answer)}; level {tool.level} "
            f"-> {'accepted' if ok else 'refused'}")
        return ok

    while True:
        text = read()
        if text is None or text.lower() in ("quit", "exit", "q"):
            return
        if not text:
            continue
        try:
            out(f"Jarvis: {brain.turn(text, ask)}")
        except Exception as e:  # live server down, etc.
            out(f"Jarvis: Mon cerveau ne répond pas ({e}).")


def run(cfg: dict, backend, real_tools: bool = False) -> None:
    if real_tools:
        toolbox = Toolbox(cfg, say=lambda s: print(f"Jarvis (reminder): {s}"))
    else:
        cfg["notes"]["dir"] = tempfile.mkdtemp(prefix="jarvis-demo-")
        toolbox = DemoToolbox(cfg, say=lambda s: print(f"Jarvis (reminder): {s}"))
    print(BANNER)
    if not real_tools:
        print(f"Notes and tasks are written to {cfg['notes']['dir']}")
    repl(Brain(cfg, toolbox, backend), echo=not sys.stdin.isatty())
