"""THROWAWAY #11 UI experiment. Serves frozen reports, never reads bank CSVs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIVATE = HERE.parents[1] / "imports" / ".dashboard-11" / "reports.json"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/": (HERE / "index.html", "text/html; charset=utf-8"),
            "/style.css": (HERE / "style.css", "text/css; charset=utf-8"),
            "/app.js": (HERE / "app.js", "text/javascript; charset=utf-8"),
            "/reports.json": (PRIVATE if PRIVATE.exists() else HERE / "example.json", "application/json"),
            "/example.json": (HERE / "example.json", "application/json"),
        }
        path = self.path.split("?", 1)[0]
        if path not in routes:
            self.send_error(404)
            return
        file, content_type = routes[path]
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Throwaway dashboard: http://127.0.0.1:8011 — Ctrl+C to stop", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8011), Handler).serve_forever()
