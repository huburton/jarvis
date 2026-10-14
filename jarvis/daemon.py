"""Jarvis daemon: wake word (or hotkey) -> listen -> transcribe -> LLM + tools -> speech.

Control over a UNIX socket ($XDG_RUNTIME_DIR/jarvis/ctl.sock), see jarvis-ctl:
  listen | stop | mute | unmute | toggle-mute | say <text> | ask <text>
"""
import logging
import os
import queue
import socket
import threading

from . import audio, config, confirm
from .brain import Brain
from .llm import HTTPBackend
from .speech import STT, TTS
from .state import State
from .tools import Toolbox

log = logging.getLogger("jarvis")


class Jarvis:
    def __init__(self):
        self.cfg = config.load()
        self.state = State()
        a = self.cfg["audio"]
        log.info("loading models...")
        self.mic = audio.Mic(a["device"])
        w = self.cfg["wake"]
        self.wake = audio.WakeWord(w["model"], w["threshold"], w.get("patience", 1))
        self.endpointer = audio.Endpointer(a["silence_ms"], a["max_utterance_s"])
        s = self.cfg["stt"]
        self.stt = STT(s["model"], s["device"], s["compute_type"], s["threads"], s["prompt"])
        self.tts = TTS(self.cfg["tts"]["voice"], self.cfg["tts"]["length_scale"])
        self.toolbox = Toolbox(self.cfg, self.say_async)
        self.brain = Brain(self.cfg, self.toolbox, HTTPBackend(self.cfg))
        self.commands: queue.Queue[tuple[str, str]] = queue.Queue()
        self._abort = threading.Event()
        self._speak_lock = threading.Lock()
        log.info("ready")

    # ------------------------------------------------------------ voix
    def say(self, text: str):
        with self._speak_lock:
            self.state.set("speaking", reply=text)
            self.tts.speak(text)
            self.mic.drain()  # do not listen to our own voice

    def say_async(self, text: str):
        """For timers (runs in its own thread)."""
        self.commands.put(("say", text))

    # ------------------------------------------------------------ interactions
    def listen(self, timeout: float) -> str:
        self.state.set("listening", heard="", reply="")
        audio_data = self.endpointer.record(self.mic, timeout, should_abort=self._abort.is_set)
        if audio_data is None:
            return ""
        self.state.set("thinking")
        return self.stt.transcribe(audio_data)

    def ask_confirmation(self, tool, args) -> bool:
        what = tool.announce(args) if tool.announce else tool.name
        self.say(confirm.question(tool.level, what))
        self.state.set("confirm", reply=f"Confirmer : {what} ?")
        answer = self.listen(self.cfg["audio"]["followup_s"])
        log.info("confirmation %r -> %s", answer, confirm.parse(answer))
        return confirm.accepted(tool.level, answer)

    def conversation(self, first_text: str | None = None):
        """One exchange, then keep listening without a wake word while the user follows up."""
        self._abort.clear()
        text = first_text
        timeout = self.cfg["audio"]["start_timeout_s"]
        while True:
            if text is None:
                text = self.listen(timeout)
            if not text or self._abort.is_set():
                break
            log.info("heard: %s", text)
            self.state.set("thinking", heard=text)
            try:
                reply = self.brain.turn(text, self.ask_confirmation)
            except Exception:
                log.exception("LLM")
                reply = "Mon cerveau ne répond pas, le serveur de modèles est peut-être arrêté."
            self.state.log(text, reply)
            if reply and not self._abort.is_set():
                self.say(reply)
            if self.cfg["audio"].get("followup_only_after_question") and not reply.rstrip().endswith("?"):
                break  # no question asked: do not listen without a wake word (avoids answering the TV)
            text = None
            timeout = self.cfg["audio"]["followup_s"]
        self.state.set("idle")
        self.wake.reset()
        self.mic.drain()

    # ------------------------------------------------------------ boucle
    def run(self):
        threading.Thread(target=self._control_server, daemon=True).start()
        self.mic.start()
        while True:
            try:
                cmd, arg = self.commands.get_nowait()
            except queue.Empty:
                cmd, arg = "", ""
            if cmd == "listen":
                audio.chime(self.cfg["audio"]["chime"])
                self.conversation()
            elif cmd == "ask":
                self.conversation(arg)
            elif cmd == "say":
                self.say(arg)
                self.state.set("idle")
            chunk = self.mic.read(timeout=0.5)
            if chunk is None or self.state.muted:
                continue
            if self.wake.detect(chunk):
                log.info("wake word")
                audio.chime(self.cfg["audio"]["chime"])
                self.wake.reset()
                self.conversation()

    def _control_server(self):
        path = config.RUNTIME_DIR / "ctl.sock"
        path.unlink(missing_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(path))
        os.chmod(path, 0o600)
        srv.listen(4)
        while True:
            conn, _ = srv.accept()
            with conn:
                line = conn.recv(4096).decode().strip()
                cmd, _, arg = line.partition(" ")
                if cmd in ("stop", "listen"):
                    self._abort.set()   # cut the current listening / thinking
                    self.tts.stop()
                    if cmd == "listen" and self.state.current == "idle":
                        self.commands.put(("listen", ""))
                elif cmd in ("mute", "unmute", "toggle-mute"):
                    muted = {"mute": True, "unmute": False}.get(cmd, not self.state.muted)
                    self.state.set(self.state.current, muted=muted)
                elif cmd in ("say", "ask") and arg:
                    self.commands.put((cmd, arg))
                conn.sendall(b"ok\n")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Jarvis().run()
