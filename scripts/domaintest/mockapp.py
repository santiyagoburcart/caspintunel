"""Stand-ins for Django (`web:8000`) and the user SPA (`frontend_user:80`) behind the REAL nginx/prod.conf in
scripts/test-tenants.sh (never used in production). They only echo what reached them, so the test can see which upstream
answered, with which path and which X-Forwarded-Proto:

  web  : /.well-known/caspin/<tok> → <tok> · /api/v1/store-unavailable/ → 503 "unavailable <host>" · else "django <path> <proto>"
  spa  : "site <host>"
"""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = sys.argv[1] if len(sys.argv) > 1 else "web"


class H(BaseHTTPRequestHandler):
    def _answer(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        proto = self.headers.get("X-Forwarded-Proto", "-")
        status, body = 200, f"site {host}"
        if MODE == "web":
            if self.path.startswith("/.well-known/caspin/"):
                body = self.path.rsplit("/", 1)[-1] or self.path.rstrip("/").rsplit("/", 1)[-1]
            elif self.path == "/api/v1/store-unavailable/":
                status, body = 503, f"unavailable {host}"
            else:
                body = f"django {self.path} {proto}"
        data = (body + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = do_POST = do_HEAD = _answer

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("0.0.0.0", 8000 if MODE == "web" else 80), H).serve_forever()
