"""THROWAWAY #11 UI experiment.

Serves one synthetic fixture and the prototype's own files, from this folder
and nowhere else. It never reads ``imports/``, a bank export or a private
report, and it binds to loopback only.

    py -3.12 prototypes/dashboard-11/serve.py [--port 8011]
"""

from __future__ import annotations

import argparse
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from collections.abc import Sequence

HERE = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8011
ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/example.json": ("example.json", "application/json; charset=utf-8"),
}
RUNTIME_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'"
    ),
}
NO_CONTENT_PATHS = frozenset({"/favicon.ico"})


class Handler(BaseHTTPRequestHandler):
    """Answer one prototype request at a time."""

    def do_GET(self) -> None:
        """Serve one known file, or report that the path is unknown."""
        path = self.path.split("?", 1)[0]
        if path in NO_CONTENT_PATHS:
            # Browsers ask for a favicon on their own; answer without content so
            # the prototype leaves no error behind in the console.
            self.send_response(204)
            self.end_headers()
            return
        route = ROUTES.get(path)
        if route is None:
            self.send_error(404)
            return
        name, content_type = route
        body = (HERE / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for header, value in RUNTIME_HEADERS.items():
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(body)

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the console clear of per-request lines."""


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description="Serve the #11 prototype.")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"loopback port to serve on (default {DEFAULT_PORT})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Serve the prototype until the operator stops it."""
    port = int(parse_arguments(sys.argv[1:] if argv is None else argv).port)
    server = ThreadingHTTPServer((HOST, port), Handler)
    sys.stdout.write(
        f"Prototype til afproevning: http://{HOST}:{port} - stop med Ctrl+C\n"
    )
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("\nStoppet.\n")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
