"""The constrained tool-choice schema, and the fake backend's output validated against it."""
import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

from jarvis.brain import build_action_schema
from jarvis.fake_llm import FakeBackend

UTTERANCES = {
    "quelle heure est-il": "get_datetime",
    "quel temps demain": "get_weather",
    "mets la musique en pause": "media_control",
    "quel morceau passe": "now_playing",
    "mets le volume à 30": "set_volume",
    "ouvre le terminal": "open_app",
    "va sur le bureau 4": "switch_workspace",
    "rappelle-moi dans 10 minutes de sortir le pain": "set_timer",
    "donne-moi l'état du PC": "system_status",
    "note que le dentiste est jeudi": "take_note",
    "ajoute la tâche acheter du café": "add_task",
    "verrouille la session": "lock_screen",
    "éteins le PC": "power",
}


@pytest.fixture
def schema(toolbox):
    return build_action_schema(toolbox.tools.values())


def test_schema_has_one_option_per_tool_plus_answer(toolbox, schema):
    names = [o["properties"]["tool"]["const"] for o in schema["anyOf"]]
    assert names[0] == "answer"
    assert sorted(names[1:]) == sorted(toolbox.tools)


def test_each_option_embeds_the_tool_parameter_schema(toolbox, schema):
    by_name = {o["properties"]["tool"]["const"]: o for o in schema["anyOf"]}
    for name, tool in toolbox.tools.items():
        assert by_name[name]["properties"]["args"] is tool.parameters
        assert by_name[name]["required"] == ["tool", "args"]


def test_schema_accepts_valid_and_rejects_invalid_actions(schema):
    v = Draft202012Validator(schema)
    v.validate({"tool": "set_volume", "args": {"percent": 30}})
    v.validate({"tool": "answer", "args": {"text": "Salut"}})
    for bad in [
        {"tool": "set_volume", "args": {"percent": 300}},      # out of range
        {"tool": "power", "args": {"action": "format_disk"}},  # not in the enum
        {"tool": "rm_rf", "args": {}},                         # unknown tool
        {"tool": "open_app", "args": {}},                      # missing required arg
        {"tool": "answer", "args": {}},
    ]:
        with pytest.raises(ValidationError):
            v.validate(bad)


@pytest.mark.parametrize("text,tool", UTTERANCES.items())
def test_fake_backend_output_conforms_and_picks_the_right_tool(text, tool, toolbox, schema):
    payload = {"messages": [{"role": "user", "content": text}],
               "response_format": {"type": "json_schema", "json_schema": {"name": "action", "schema": schema}}}
    action = json.loads(FakeBackend().post(payload)["content"])
    Draft202012Validator(schema).validate(action)
    assert action["tool"] == tool


def test_fake_backend_answers_when_nothing_matches(schema):
    payload = {"messages": [{"role": "user", "content": "xyzzy"}],
               "response_format": {"type": "json_schema", "json_schema": {"name": "action", "schema": schema}}}
    assert json.loads(FakeBackend().post(payload)["content"])["tool"] == "answer"
