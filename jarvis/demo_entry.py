"""`jarvis-demo`: shortcut for `jarvis --text`."""
import sys

from .__main__ import main as _main


def main() -> int:
    return _main(["--text", *sys.argv[1:]])
