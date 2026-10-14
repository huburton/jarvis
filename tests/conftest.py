import pytest

from jarvis import config
from jarvis.brain import Brain
from jarvis.fake_llm import FakeBackend
from jarvis.tools import Toolbox


@pytest.fixture
def cfg(tmp_path):
    c = config.load(path=tmp_path / "missing.toml", env={})
    c["notes"]["dir"] = str(tmp_path / "notes")
    return c


@pytest.fixture
def toolbox(cfg):
    return Toolbox(cfg, say=lambda s: None)


@pytest.fixture
def brain(cfg, toolbox):
    return Brain(cfg, toolbox, FakeBackend())
