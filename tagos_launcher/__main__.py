"""Entry point: ``python -m tagos_launcher``.

Only one launcher runs at a time. Starting it again while it's running passes
a message to the running copy instead, so these work from a shortcut, a script
or TagOS Manager:

    python -m tagos_launcher                 # start (stays in the tray)
    python -m tagos_launcher --show          # open the launcher
    python -m tagos_launcher --show "obs:"   # open it with text pre-filled
    python -m tagos_launcher --settings      # open the settings window
    python -m tagos_launcher --quit          # stop the running launcher
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from typing import List, Optional

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import __app_name__, __version__
from .config import config_dir


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"SNTag.TagOSLauncher.{user}"


def _setup_logging() -> None:
    handlers: List[logging.Handler] = [
        logging.FileHandler(os.path.join(config_dir(), "launcher.log"), encoding="utf-8")
    ]
    # Under pythonw there is no console; under TagOS Manager stdout is its tab.
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _send_to_running(message: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(500):
        return False
    sock.write(message.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="tagos_launcher", description=__app_name__)
    parser.add_argument("--show", nargs="?", const="", metavar="TEXT",
                        help="open the launcher (optionally pre-filled with TEXT)")
    parser.add_argument("--settings", action="store_true", help="open the settings window")
    parser.add_argument("--quit", action="store_true", help="stop the running launcher")
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    args, _qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.quit:
        message = "quit"
    elif args.settings:
        message = "settings"
    elif args.show is not None:
        message = "show:" + args.show if args.show else "show"
    else:
        message = ""

    app = QApplication(sys.argv[:1])
    app.setApplicationName(__app_name__)
    app.setQuitOnLastWindowClosed(False)

    if _send_to_running(message or "noop"):
        return 0  # the running copy handles it
    if args.quit:
        return 0

    _setup_logging()
    server = QLocalServer()
    QLocalServer.removeServer(_server_name())  # clear a stale socket after a crash
    if not server.listen(_server_name()):
        logging.warning("Single-instance server failed: %s", server.errorString())

    from .app import LauncherApp

    launcher = LauncherApp(app, server)
    logging.info("%s %s started", __app_name__, __version__)
    if message:
        launcher.handle_command(message)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
