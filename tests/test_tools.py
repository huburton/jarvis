import datetime as dt
import subprocess

import pytest

from jarvis.demo import DemoToolbox
from jarvis.textutil import for_voice, fr_date, fr_datetime, split_sentences
from jarvis.tools import match_app


def test_permission_levels(toolbox):
    levels = {n: t.level for n, t in toolbox.tools.items()}
    assert levels["power"] == 3
    assert levels["lock_screen"] == 2 and levels["add_task"] == 2
    assert all(lv == 1 for n, lv in levels.items() if n not in ("power", "lock_screen", "add_task"))


def test_confirmed_tools_have_an_announcement(toolbox):
    for tool in toolbox.tools.values():
        if tool.level >= 2:
            assert tool.announce and tool.announce({"action": "reboot", "title": "x"})


def test_info_tools_are_reworded_actions_are_not(toolbox):
    info = {n for n, t in toolbox.tools.items() if not t.direct}
    assert info == {"get_datetime", "get_weather", "now_playing", "system_status"}


def test_call_unknown_tool_and_bad_arguments(toolbox):
    assert "inconnu" in toolbox.call("format_disk", {})
    assert "invalides" in toolbox.call("take_note", {"nope": 1})


def test_notes_and_tasks_go_to_the_configured_directory(toolbox, cfg):
    from pathlib import Path
    assert toolbox.call("take_note", {"text": "acheter du pain"}) == "Noté."
    toolbox.call("add_task", {"title": "payer la facture"})
    toolbox.call("add_task", {"title": "appeler le garage"})
    notes = Path(cfg["notes"]["dir"])
    assert "acheter du pain" in next(notes.glob("*-jarvis.md")).read_text()
    assert (notes / "tasks.md").read_text() == "- [ ] payer la facture\n- [ ] appeler le garage\n"


def test_match_app_fuzzy():
    apps = {"firefox": ["firefox", "navigateur web"], "org.gnome.Terminal": ["terminal"]}
    assert match_app("Firefox", apps) == "firefox"
    assert match_app("navigateur web", apps) == "firefox"
    assert match_app("termnal", apps) == "org.gnome.Terminal"
    assert match_app("photoshop", apps) is None


def test_demo_toolbox_never_touches_the_system(cfg, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("demo tools must not run commands")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    tb = DemoToolbox(cfg, say=lambda s: None, out=lambda s: None)
    for name, args in [("media_control", {"action": "next"}), ("set_volume", {"percent": 20}),
                       ("open_app", {"name": "firefox"}), ("switch_workspace", {"number": 2}),
                       ("set_timer", {"minutes": 5}), ("lock_screen", {}), ("power", {"action": "reboot"}),
                       ("system_status", {}), ("get_weather", {"day": "tomorrow"})]:
        assert not tb.call(name, args).startswith(("Échec", "Arguments"))
    assert tb.volume == 20


def test_french_dates_do_not_depend_on_locale():
    d = dt.datetime(2026, 10, 14, 9, 5)
    assert fr_date(d) == "mercredi 14 octobre 2026"
    assert fr_datetime(d) == "mercredi 14 octobre 2026, 09:05"


def test_for_voice_trims_notes_markdown_and_length():
    text = "Il fait **beau**. Il fait doux. Prends une veste. Et un parapluie.\nNote : ceci est un test."
    assert for_voice(text) == "Il fait beau. Il fait doux. Prends une veste."
    assert for_voice(text, 1) == "Il fait beau."


@pytest.mark.parametrize("text,parts", [
    ("Bonjour. Ça va ? Oui !", ["Bonjour.", "Ça va ?", "Oui !"]),
    ("# Titre\n* un\n* deux", ["Titre", "un", "deux"]),
])
def test_split_sentences(text, parts):
    assert split_sentences(text) == parts
