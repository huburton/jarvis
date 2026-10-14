import pytest

from jarvis.router import compile_triggers, needs_tool, strip_accents


@pytest.mark.parametrize("text", [
    "Quelle heure est-il ?", "quel temps fait-il demain", "Mets la musique en pause", "monte le volume",
    "Ouvre Firefox", "rappelle-moi dans 10 minutes", "Éteins le PC", "va sur le bureau 3",
    "note que j'ai rendez-vous", "quel est l'état du PC", "verrouille la session",
])
def test_actions_and_live_info_need_a_tool(text):
    assert needs_tool(text)


@pytest.mark.parametrize("text", [
    "bonjour", "merci beaucoup", "raconte-moi une blague", "qui es-tu", "explique-moi la photosynthèse",
])
def test_small_talk_does_not(text):
    assert not needs_tool(text)


def test_accents_are_ignored():
    assert strip_accents("Météo à Lyon") == "meteo a lyon"
    assert needs_tool("MÉTÉO")


def test_plugins_can_add_triggers():
    assert not needs_tool("cherche des idées de recette")
    assert needs_tool("cherche des idées de recette", compile_triggers((r"cherche",)))
