"""Brain turns end to end against the fake backend: permission gating and the three reply paths."""
from jarvis.brain import Brain


class Asker:
    """confirm() callback that records what it was asked and answers with a fixed verdict."""

    def __init__(self, verdict: bool):
        self.verdict, self.asked = verdict, []

    def __call__(self, tool, args):
        self.asked.append((tool.name, tool.level))
        return self.verdict


def test_level1_action_reports_the_exact_tool_result(brain, toolbox):
    toolbox.tools["set_volume"].func = lambda percent=None, mute=None: f"Volume à {percent} %."
    ask = Asker(False)
    assert brain.turn("mets le volume à 30", ask) == "Volume à 30 %."
    assert ask.asked == []


def test_level2_refused_does_not_run_the_tool(brain, toolbox, cfg):
    calls = []
    toolbox.tools["lock_screen"].func = lambda: calls.append(1) or "ok"
    ask = Asker(False)
    assert brain.turn("verrouille la session", ask) == Brain.CANCELLED
    assert ask.asked == [("lock_screen", 2)] and calls == []


def test_level2_accepted_runs_the_tool(brain, toolbox):
    toolbox.tools["lock_screen"].func = lambda: "Session verrouillée."
    ask = Asker(True)
    assert brain.turn("verrouille la session", ask) == "Session verrouillée."
    assert ask.asked == [("lock_screen", 2)]


def test_level3_asks_with_level_3_and_cancels(brain, toolbox):
    calls = []
    toolbox.tools["power"].func = lambda action: calls.append(action) or "Extinction."
    ask = Asker(False)
    assert brain.turn("éteins le PC", ask) == Brain.CANCELLED
    assert ask.asked == [("power", 3)] and calls == []
    assert brain.turn("redémarre le PC", Asker(True)) == "Extinction."
    assert calls == ["reboot"]


def test_info_tool_goes_through_the_reword_pass(brain, toolbox):
    toolbox.tools["get_datetime"].func = lambda: "mercredi 14 octobre 2026, 09:05"
    assert brain.turn("quelle heure est-il ?", Asker(False)) == "mercredi 14 octobre 2026, 09:05"


def test_small_talk_skips_the_tool_path(brain):
    assert brain.turn("bonjour", Asker(False)).startswith("Salut")


def test_ambiguous_request_gets_a_question_instead_of_an_action(brain):
    assert brain.turn("monte le volume", Asker(False)) == "À combien tu veux le volume ?"


def test_history_is_trimmed(brain):
    for _ in range(20):
        brain.turn("bonjour", Asker(False))
    assert len(brain.history) == 2 * brain.cfg["history_turns"]


class ScriptedBackend:
    """Model that answers freely (no router match), first calling a tool, then replying."""

    def __init__(self, tool_call):
        self.script = [{"content": "", "tool_calls": [tool_call]}, {"content": "Voilà."}]

    def settings(self):
        return "scripted", {}

    def post(self, payload):
        return self.script.pop(0)


def test_free_tool_loop_also_enforces_permissions(cfg, toolbox):
    calls = []
    toolbox.tools["power"].func = lambda action: calls.append(action) or "Extinction."
    call = {"id": "1", "type": "function", "function": {"name": "power", "arguments": '{"action": "shutdown"}'}}
    brain = Brain(cfg, toolbox, ScriptedBackend(call))
    ask = Asker(False)
    assert brain.turn("on fait le point sur le projet", ask) == "Voilà."  # no router match
    assert ask.asked == [("power", 3)] and calls == []
