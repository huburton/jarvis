"""remote_agent plugin: disabled by default; reply, timeout and unreachable cases (local fake server)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from jarvis import config
from jarvis.tools import Toolbox


class FakeAgent(BaseHTTPRequestHandler):
    delay = 0.0

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        time.sleep(self.delay)
        ok = self.headers["Authorization"] == "Bearer secret" and body == {
            "text": "statut", "from": "jarvis", "wait": True}
        out = json.dumps({"reply": "Tout va bien." if ok else "unexpected request"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def toolbox(tmp_path, url, timeout_s=2):
    key = tmp_path / "key"
    key.write_text("secret\n")
    cfg = config.load(path=tmp_path / "none.toml", env={})
    cfg["plugins"]["remote_agent"].update(enabled=True, url=url, key_file=str(key), timeout_s=timeout_s)
    return Toolbox(cfg, say=lambda s: None)


def serve(delay):
    FakeAgent.delay = delay
    srv = HTTPServer(("127.0.0.1", 0), FakeAgent)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def test_disabled_by_default(toolbox):
    assert "ask_remote_agent" not in toolbox.tools


def test_enabled_registers_a_level1_tool_with_triggers(tmp_path):
    tb = toolbox(tmp_path, "http://127.0.0.1:9")
    assert tb.tools["ask_remote_agent"].level == 1
    assert "cherche" in tb.tools["ask_remote_agent"].triggers


def test_reply(tmp_path):
    srv, url = serve(0)
    assert toolbox(tmp_path, url).call("ask_remote_agent", {"request": "statut"}) == "Tout va bien."
    srv.shutdown()


def test_timeout_is_not_an_error(tmp_path):
    srv, url = serve(1.5)
    out = toolbox(tmp_path, url, timeout_s=0.5).call("ask_remote_agent", {"request": "statut"})
    assert "transmis" in out
    srv.shutdown()


def test_unreachable(tmp_path):
    assert "injoignable" in toolbox(tmp_path, "http://127.0.0.1:9").call("ask_remote_agent", {"request": "statut"})
