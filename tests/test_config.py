from jarvis import config


def test_defaults_are_neutral_and_plugins_off(tmp_path):
    cfg = config.load(path=tmp_path / "none.toml", env={})
    assert cfg["plugins"]["remote_agent"]["enabled"] is False
    assert cfg["llm"]["fallback_url"] == ""
    assert cfg["llm"]["url"].startswith("http://127.0.0.1")


def test_file_overrides_defaults_deeply(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[llm]\nmodel = "x"\n[plugins.remote_agent]\nenabled = true\n')
    cfg = config.load(path=f, env={})
    assert cfg["llm"]["model"] == "x" and cfg["llm"]["history_turns"] == 6
    assert cfg["plugins"]["remote_agent"]["enabled"] is True
    assert cfg["plugins"]["remote_agent"]["timeout_s"] == 45


def test_env_beats_file(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[llm]\nurl = "http://file/v1"\n')
    cfg = config.load(path=f, env={"JARVIS_LLM_URL": "http://env/v1", "JARVIS_LLM_KEY": "k"})
    assert cfg["llm"]["url"] == "http://env/v1" and cfg["llm"]["api_key"] == "k"
