"""Entry point.

  python -m jarvis --text      text demo (fake LLM, stub tools; no audio dependencies)
  python -m jarvis             the voice daemon (needs the `voice` extra)
"""
import argparse
import os
import sys

from . import config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis", description="Local French voice assistant.")
    ap.add_argument("--text", action="store_true",
                    help="text REPL instead of the microphone; fake LLM and stub tools by default")
    ap.add_argument("--llm-url", help="use a real OpenAI-compatible server in --text mode "
                    "(same as JARVIS_LLM_URL), e.g. http://127.0.0.1:8080/v1")
    ap.add_argument("--real-tools", action="store_true",
                    help="in --text mode, run the real tools (playerctl, wpctl, ...) instead of stubs")
    args = ap.parse_args(argv)

    if args.text:
        from . import demo
        from .fake_llm import FakeBackend
        from .llm import HTTPBackend
        if args.llm_url:
            os.environ["JARVIS_LLM_URL"] = args.llm_url
        cfg = config.load()
        live = bool(os.environ.get("JARVIS_LLM_URL"))
        demo.run(cfg, HTTPBackend(cfg) if live else FakeBackend(), real_tools=args.real_tools)
        return 0

    try:
        from .daemon import main as run_daemon
    except ImportError as e:
        sys.exit(f"Voice dependencies are missing ({e}). Install them with: pip install '.[voice]'\n"
                 "Or try the text demo: python -m jarvis --text")
    run_daemon()
    return 0


if __name__ == "__main__":
    sys.exit(main())
