"""Mock Cloudflare API + DNS-over-HTTPS for scripts/test-domain.sh (never used in production).
The DoH endpoint answers from the records created through the mock API."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "mock-cloudflare-token-0123456789abcdef"
ZONES = [{"id": "z1", "name": "new.test", "status": "active", "permissions": ["#zone:read", "#dns_records:read", "#dns_records:edit"]},
         {"id": "z2", "name": "bad.test", "status": "active", "permissions": ["#zone:read", "#dns_records:read", "#dns_records:edit"]},
         {"id": "z3", "name": "view-only.test", "status": "active", "permissions": ["#zone:read", "#dns_records:read"]}]
RECORDS = {}
SSL = {"value": "full"}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ok(self, result):
        self._send(200, {"success": True, "errors": [], "result": result})

    def _route(self, method):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/dns-query":
            t = q.get("type", "A")
            recs = [r for r in RECORDS.values() if r["name"] == q.get("name") and r["type"] == t]
            def data(r):
                if t == "MX":
                    return f"{r.get('priority', 10)} {r['content']}."
                if t == "TXT":   # quoted 255-byte chunks, like real resolvers
                    return " ".join(f'"{r["content"][i:i + 255]}"' for i in range(0, len(r["content"]), 255))
                return r["content"]
            return self._send(200, {"Status": 0, "Answer": [{"name": q.get("name"), "type": {"A": 1, "MX": 15, "TXT": 16}[t], "data": data(r)} for r in recs]})
        if u.path == "/records":                       # for the test script
            return self._send(200, list(RECORDS.values()))
        if u.path == "/client/v4/ips":                 # public, like Cloudflare's
            return self._ok({"ipv4_cidrs": ["173.245.48.0/20", "104.16.0.0/13"], "ipv6_cidrs": ["2606:4700::/32"]})
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(403, {"success": False, "errors": [{"code": 9109, "message": "Invalid access token"}], "result": None})
        p = u.path.removeprefix("/client/v4")
        if p.endswith("/settings/ssl"):
            if method == "PATCH":
                SSL["value"] = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}").get("value", SSL["value"])
            return self._ok({"id": "ssl", "value": SSL["value"]})
        if p == "/user/tokens/verify":
            return self._ok({"id": "tok1", "status": "active"})
        if p == "/zones":
            return self._ok([z for z in ZONES if not q.get("name") or z["name"] == q["name"]])
        parts = p.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "zones" and parts[2] == "dns_records":
            zone = next((z for z in ZONES if z["id"] == parts[1]), None)
            if not zone:
                return self._send(404, {"success": False, "errors": [{"code": 7003, "message": "Could not route to /zones/" + parts[1]}], "result": None})
            if method == "GET":
                return self._ok([r for r in RECORDS.values() if r["zone"] == parts[1] and q.get("name", r["name"]) == r["name"]
                                 and q.get("type", r["type"]) == r["type"]])
            if "#dns_records:edit" not in zone["permissions"]:     # like Cloudflare: a read-only token can't write
                return self._send(403, {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}], "result": None})
            if method == "DELETE":
                RECORDS.pop(parts[3] if len(parts) > 3 else "", None)
                return self._ok({"id": parts[3] if len(parts) > 3 else ""})
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if method == "PATCH" and len(parts) > 3 and parts[3] in RECORDS:      # merge
                RECORDS[parts[3]].update(body)
                return self._ok(RECORDS[parts[3]])
            rid = parts[3] if len(parts) > 3 else f"r{len(RECORDS) + 1}"
            while method == "POST" and rid in RECORDS:
                rid += "x"
            RECORDS[rid] = {**body, "id": rid, "zone": parts[1]}
            return self._ok(RECORDS[rid])
        self._send(404, {"success": False, "errors": [{"code": 7003, "message": "no route"}], "result": None})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_PATCH(self):
        self._route("PATCH")

    def do_DELETE(self):
        self._route("DELETE")

    def log_message(self, *a):
        pass


HTTPServer(("0.0.0.0", 8080), H).serve_forever()
