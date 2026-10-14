"""Control the running Jarvis daemon over its UNIX socket.

Usage: jarvis-ctl listen|stop|mute|unmute|toggle-mute|say <text>|ask <text>
"""
import socket
import subprocess
import sys

from .config import RUNTIME_DIR


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(RUNTIME_DIR / "ctl.sock"))
            s.sendall((" ".join(sys.argv[1:]) + "\n").encode())
            s.recv(16)
    except OSError:
        subprocess.run(["notify-send", "-a", "Jarvis", "Jarvis n'est pas lancé", "systemctl --user start jarvis"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
