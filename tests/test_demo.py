import subprocess
import sys

from jarvis import demo
from jarvis.brain import Brain
from jarvis.demo import DemoToolbox
from jarvis.fake_llm import FakeBackend


def run_session(cfg, lines):
    out = []
    it = iter(lines)
    tb = DemoToolbox(cfg, say=lambda s: None, out=out.append)
    brain = Brain(cfg, tb, FakeBackend())

    def read():
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None
    demo.repl(brain, input_fn=read, out=out.append)
    return "\n".join(out)


def test_session_with_confirmation_flow(cfg):
    text = run_session(cfg, ["verrouille la session", "oui", "éteins le PC", "oui", "quit"])
    assert "Tu confirmes ?" in text
    assert "level 2 -> accepted" in text
    assert "Session verrouillée." in text
    # a plain "oui" is not enough for the level 3 tool
    assert "level 3 -> refused" in text
    assert "D'accord, j'annule." in text
    assert "would run: systemctl" not in text


def test_level3_accepted_with_the_confirm_word(cfg):
    text = run_session(cfg, ["éteins le PC", "oui, je confirme", "quit"])
    assert "would run: systemctl poweroff" in text


def test_negation_cancels(cfg):
    text = run_session(cfg, ["verrouille la session", "non vas-y pas", "quit"])
    assert "-> refused" in text and "would run: loginctl" not in text


def test_eof_ends_the_session(cfg):
    assert "Jarvis:" not in run_session(cfg, [])


def test_text_mode_runs_without_audio_deps(tmp_path):
    """`python -m jarvis --text` must not import numpy/sounddevice/faster-whisper."""
    code = (f"import sys, jarvis.__main__ as m; sys.stdin = open({str(tmp_path / 'in.txt')!r}); m.main(['--text']); "
            "bad = [n for n in ('sounddevice', 'faster_whisper', 'openwakeword', 'piper') if n in sys.modules]; "
            "print('LEAK', bad) if bad else print('CLEAN')")
    (tmp_path / "in.txt").write_text("quelle heure est-il ?\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path,
                       env={"PATH": "/usr/bin", "HOME": str(tmp_path), "JARVIS_NOTES_DIR": str(tmp_path / "n")})
    assert "CLEAN" in r.stdout, r.stdout + r.stderr
