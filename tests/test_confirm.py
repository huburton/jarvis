import pytest

from jarvis.confirm import accepted, parse, question


@pytest.mark.parametrize("text", [
    "oui", "Oui vas-y", "ok", "d'accord", "Ouais, confirme.", "c'est ça", "Bien sûr", "fais-le",
])
def test_yes(text):
    assert parse(text) == "yes"


@pytest.mark.parametrize("text", [
    "non", "pas d'accord", "non, n'envoie pas", "ne le fais pas", "surtout pas", "annule",
    "oui... non attends", "stop", "laisse tomber", "Non merci", "je ne suis pas d'accord",
    "n'éteins pas", "oui mais pas maintenant",
])
def test_no(text):
    assert parse(text) == "no"


@pytest.mark.parametrize("text", ["", "euh", "peut-être", "carrément la météo", "hmm je sais pas trop"])
def test_unclear_or_no(text):
    # jamais « yes » sans oui explicite
    assert parse(text) != "yes"


def test_negation_beats_yes_in_either_order():
    assert parse("oui non") == "no"
    assert parse("non oui") == "no"
    assert parse("oui mais ne le fais pas") == "no"


def test_accented_and_curly_apostrophe_forms():
    assert parse("D’accord") == "yes"
    assert parse("n’envoie pas") == "no"


def test_level2_needs_explicit_yes():
    assert accepted(2, "oui")
    assert accepted(2, "vas-y")
    assert not accepted(2, "euh")
    assert not accepted(2, "non")


def test_level3_needs_yes_and_the_word_confirm():
    assert not accepted(3, "oui")
    assert not accepted(3, "d'accord")
    assert accepted(3, "oui, je confirme")
    assert not accepted(3, "oui je ne confirme pas")
    assert not accepted(3, "non je confirme pas")


def test_question_wording_depends_on_level():
    assert question(2, "verrouiller la session").endswith("Tu confirmes ?")
    assert "je confirme" in question(3, "éteindre le PC")
