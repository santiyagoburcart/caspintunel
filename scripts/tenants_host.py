#!/usr/bin/env python3
"""Store domains on the HOST (docs/multi-tenant.md §7) — run by scripts/tenants.sh (cron, every minute). Standard library only.

The web app writes backups/.tenant-domains.json (verified store hosts); this reconciles the server with it:

  1. a host without a valid certificate (covering www when asked): first a free PRE-CHECK — a random file in the ACME webroot
     fetched as http://<host>/.well-known/acme-challenge/… through the PUBLIC path (our IP, the Iran tunnel or the reseller's
     Cloudflare, whatever their DNS says). Only when that comes back do we ask Let's Encrypt (HTTP-01, webroot, served by
     nginx on 80 and 443 for every name). At most one issuance per run; a failed attempt waits 30 min (pre-check: 5 min)
     unless staff pressed «تلاش دوباره» (the retry counter changed).
  2. nginx/tenants/<host>.conf for every host with a valid certificate; files of hosts no longer wanted are removed (and their
     certificates deleted). Any change: nginx -t → reload → each changed host verified over TLS on 127.0.0.1:443 with its
     SNI → on failure every file is restored and nginx reloaded.
  3. backups/.tenant-status.json: per host what happened (the panel shows it, Celery advances the domain).

Never edits our own domain's files (scripts/domain.sh) and never touches .env.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = os.environ.get("TENANTS_COMPOSE", "docker compose -f docker-compose.yml -f docker-compose.prod.yml").split()
DESIRED = Path(os.environ.get("TENANTS_DESIRED", ROOT / "backups/.tenant-domains.json"))
STATUS = Path(os.environ.get("TENANTS_STATUS", ROOT / "backups/.tenant-status.json"))
CONF_DIR = Path(os.environ.get("TENANTS_CONF_DIR", ROOT / "nginx/tenants"))
LE = Path(os.environ.get("TENANTS_LE", ROOT / "nginx/letsencrypt"))
WEBROOT = Path(os.environ.get("TENANTS_WEBROOT", ROOT / "nginx/certbot-webroot"))
CERTBOT = os.environ.get("TENANTS_CERTBOT", "")          # test stacks: a fake certbot (cert-name, domains…)
VERIFY_ADDR = os.environ.get("TENANTS_VERIFY_ADDR", "127.0.0.1")
VERIFY_PORT = os.environ.get("TENANTS_VERIFY_PORT", "443")
PRECHECK_ADDR = os.environ.get("TENANTS_PRECHECK_ADDR", "")   # test stacks only: fetch the pre-check here (Host = the name),
PRECHECK_PORT = os.environ.get("TENANTS_PRECHECK_PORT", "")   # not wherever public DNS points
INSECURE = os.environ.get("TENANTS_INSECURE") == "1"         # test stacks: self-signed certificates
CERT_BACKOFF = 30 * 60
PRECHECK_BACKOFF = 5 * 60
NGINX_BACKOFF = 10 * 60
HOST_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def say(msg: str) -> None:
    print(f"{now_iso()} {msg}", flush=True)


def ago(iso: str | None) -> float:
    if not iso:
        return 1e12
    try:
        return time.time() - datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 1e12


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def compose(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([*COMPOSE, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def lineage(host: str) -> str:
    return f"store-{host}"


# ------------------------------------------------------------------ certificates
def cert_info(host: str) -> dict:
    """{'ok', 'names', 'expires', 'error'} of nginx/letsencrypt/live/store-<host>/fullchain.pem."""
    c = LE / "live" / lineage(host) / "fullchain.pem"
    k = LE / "live" / lineage(host) / "privkey.pem"
    if not (c.exists() and k.exists()):
        return {"ok": False, "error": "no certificate yet"}
    p = subprocess.run(["openssl", "x509", "-in", str(c), "-noout", "-enddate", "-ext", "subjectAltName"],
                       capture_output=True, text=True)
    if p.returncode:
        return {"ok": False, "error": "certificate unreadable"}
    names = sorted(set(re.findall(r"DNS:([^,\s]+)", p.stdout)))
    end = re.search(r"notAfter=(.+)", p.stdout)
    expires = ""
    if end:
        try:
            expires = datetime.strptime(end.group(1).strip(), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc) \
                .strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    fresh = subprocess.run(["openssl", "x509", "-in", str(c), "-noout", "-checkend", "3600"], capture_output=True).returncode == 0
    return {"ok": fresh, "names": names, "expires": expires, "error": "" if fresh else "the certificate has expired"}


def covers(info: dict, host: str, www: bool) -> bool:
    need = {host} | ({f"www.{host}"} if www else set())
    return info.get("ok") and need <= set(info.get("names") or [])


def precheck(names: list[str]) -> str:
    """'' when a random file in the webroot comes back through the public path for every name, else why not."""
    d = WEBROOT / ".well-known" / "acme-challenge"
    d.mkdir(parents=True, exist_ok=True)
    tok = "caspin-check-" + secrets.token_hex(12)
    f = d / tok
    f.write_text(tok)
    os.chmod(f, 0o644)
    try:
        for n in names:
            addr = (PRECHECK_ADDR or n) + (f":{PRECHECK_PORT}" if PRECHECK_PORT else "")
            url = f"http://{addr}/.well-known/acme-challenge/{tok}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "caspin-acme-precheck", "Host": n})
                import ssl

                ctx = ssl.create_default_context()
                ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE   # Let's Encrypt ignores the certificate on redirects
                with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                    body = r.read(200).decode("utf-8", "replace").strip()
                if body != tok:
                    return f"{url} answered something else (HTTP {r.status}) — the name does not reach this server"
            except urllib.error.HTTPError as exc:
                return f"{url} answered HTTP {exc.code} — the name does not reach this server's challenge folder"
            except Exception as exc:  # noqa: BLE001
                return f"{url}: no answer ({exc.__class__.__name__}: {str(exc)[:120]})"
        return ""
    finally:
        f.unlink(missing_ok=True)


def issue(host: str, www: bool, email: str) -> str:
    """'' on success, else the reason (Let's Encrypt's own words when it gave some)."""
    names = [host] + ([f"www.{host}"] if www else [])
    doms = [a for n in names for a in ("-d", n)]
    if CERTBOT:
        p = subprocess.run([CERTBOT, lineage(host), *names], capture_output=True, text=True, timeout=600)
    else:
        p = compose("run", "--rm", "--no-deps", "-T", "--entrypoint", "certbot", "certbot", "certonly",
                    "--webroot", "-w", "/var/www/certbot", "--cert-name", lineage(host), *doms,
                    "--email", email or f"admin@{host}", "--agree-tos", "--no-eff-email", "--non-interactive",
                    "--keep-until-expiring", timeout=600)
    if p.returncode:
        out = (p.stdout or "") + (p.stderr or "")
        why = [l.strip() for l in out.splitlines() if re.search(r"Type:|Detail:|Error|error:", l)][-3:]
        return " ".join(why) or " ".join(out.strip().splitlines()[-2:])[:400] or "certbot failed"
    return ""


def delete_cert(host: str) -> None:
    if CERTBOT or not (LE / "renewal" / f"{lineage(host)}.conf").exists():
        shutil.rmtree(LE / "live" / lineage(host), ignore_errors=True)
        return
    compose("run", "--rm", "--no-deps", "-T", "--entrypoint", "certbot", "certbot", "delete",
            "--cert-name", lineage(host), "--non-interactive", timeout=120)


# ------------------------------------------------------------------ nginx
def redirect(host: str) -> str:
    return ("location / { if ($request_method !~ ^(GET|HEAD)$) { return 308 https://%s$request_uri; } "
            "return 301 https://%s$request_uri; }" % (host, host))


UNAVAILABLE = "/api/v1/store-unavailable/"
PROXY = ["        proxy_pass http://127.0.0.1:80;",
         "        proxy_set_header Host $host;",
         "        proxy_set_header X-Real-IP $remote_addr;",
         "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
         "        proxy_set_header X-Forwarded-Proto https;",
         "        proxy_set_header X-Conn-Addr $realip_remote_addr;   # the TCP peer (tunnel source check)"]


def render(h: dict) -> str:
    """The store's vhosts. A PARKED store (v1.53.2: not active — draft / suspended / closed) keeps its certificate, the ACME
    challenge and our /.well-known/caspin/ probe, and answers every other path with its «در دسترس نیست» page (Django, 503)."""
    host, www = h["host"], h["www"]
    live = f"/etc/letsencrypt/live/{lineage(host)}"
    tls = (f"    ssl_certificate     {live}/fullchain.pem;\n    ssl_certificate_key {live}/privkey.pem;\n"
           "    ssl_protocols       TLSv1.2 TLSv1.3;\n    ssl_ciphers         HIGH:!aNULL:!MD5;\n    ssl_prefer_server_ciphers on;\n")
    out = [f"# generated by scripts/tenants.sh — store {h.get('tenant')} · {host} (docs/multi-tenant.md §7) — do not edit",
           "server {", "    listen 443 ssl;", "    http2 on;", f"    server_name {host};", tls.rstrip("\n"),
           "    client_max_body_size 15m;",
           "    include /etc/nginx/domain/realip*.conf;        # CF-Connecting-IP only from Cloudflare's ranges",
           "    location /.well-known/acme-challenge/ { root /var/www/certbot; }"]
    if h.get("parked"):
        out += ["    # parked: the store is not active — every path shows its «در دسترس نیست» page (503)",
                "    location ^~ /.well-known/caspin/ {", *PROXY, "    }",
                "    location / {", f"        rewrite ^ {UNAVAILABLE}? break;", *PROXY, "    }", "}"]
    else:
        out += ["    location / {", *PROXY,
                "        proxy_http_version 1.1;",
                "        proxy_set_header Upgrade $http_upgrade;",
                "        proxy_set_header Connection $connection_upgrade;",
                "    }", "}"]
    if www:
        out += ["", f"# www.{host} → https://{host} (one host = one browser storage)",
                "server {", "    listen 443 ssl;", "    http2 on;", f"    server_name www.{host};", tls.rstrip("\n"),
                "    location /.well-known/acme-challenge/ { root /var/www/certbot; }", f"    {redirect(host)}", "}",
                "server {", "    listen 80;", f"    server_name www.{host};",
                "    location /.well-known/acme-challenge/ { root /var/www/certbot; }", f"    {redirect(host)}", "}"]
    return "\n".join(out) + "\n"


def nginx_test_reload() -> str:
    p = compose("exec", "-T", "nginx", "nginx", "-t", timeout=60)
    if p.returncode:
        line = next((l for l in (p.stderr or p.stdout).splitlines() if "[emerg]" in l or "[error]" in l), "")
        return "nginx -t rejected the config: " + (line[line.find("["):] if line else (p.stderr or "").strip()[-200:])
    p = compose("exec", "-T", "nginx", "nginx", "-s", "reload", timeout=60)
    return "" if p.returncode == 0 else "nginx reload failed"


def verify_tls(host: str, probe: str, token: str) -> str:
    """'' when https://<host><probe> answered the token over TLS on our own nginx (SNI = host, valid certificate)."""
    import http.client
    import socket
    import ssl

    ctx = ssl.create_default_context()
    if INSECURE:
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE

    class SNIConnection(http.client.HTTPSConnection):
        def connect(self):
            self.sock = ctx.wrap_socket(socket.create_connection((VERIFY_ADDR, int(VERIFY_PORT)), timeout=10),
                                        server_hostname=host)

    why = ""
    for i in range(4):
        try:
            conn = SNIConnection(VERIFY_ADDR, int(VERIFY_PORT), timeout=10)
            conn.request("GET", probe, headers={"Host": host, "User-Agent": "caspin-tenants-verify"})
            r = conn.getresponse()
            body = r.read(200).decode("utf-8", "replace").strip()
            conn.close()
            if r.status == 200 and body == token:
                return ""
            why = f"https://{host}{probe} answered HTTP {r.status}"
        except Exception as exc:  # noqa: BLE001
            why = f"TLS check of {host} failed: {exc.__class__.__name__}: {str(exc)[:160]}"
        time.sleep(2 * (i + 1))
    return why


# ------------------------------------------------------------------ one run
def run() -> int:
    want = load(DESIRED, None)
    if want is None:
        return 0
    email = want.get("email") or env_value("LETSENCRYPT_EMAIL")
    hosts = []
    for h in want.get("hosts") or []:
        host = str(h.get("host") or "").lower()
        if HOST_RE.match(host) and TOKEN_RE.match(str(h.get("token") or "")):
            hosts.append({"host": host, "www": bool(h.get("www")), "tenant": int(h.get("tenant") or 0),
                          "retry": int(h.get("retry") or 0), "token": h["token"], "probe": f"/.well-known/caspin/{h['token']}",
                          "parked": h.get("parked") is True})
        else:
            say(f"skipped an invalid entry: {host!r}")
    old = load(STATUS, {}).get("hosts") or {}
    tokens = {h["host"]: h["token"] for h in hosts}
    status: dict[str, dict] = {}
    issued_one = False
    for h in hosts:
        host, st = h["host"], dict(old.get(h["host"]) or {})
        if st.get("retry") != h["retry"]:                       # staff pressed «تلاش دوباره»: no waiting
            st.pop("cert_tried_at", None), st.pop("challenge_at", None)
        st["retry"] = h["retry"]
        info = cert_info(host)
        if not covers(info, host, h["www"]) and not issued_one:
            names = [host] + ([f"www.{host}"] if h["www"] else [])
            if ago(st.get("cert_tried_at")) >= CERT_BACKOFF and ago(st.get("challenge_at")) >= PRECHECK_BACKOFF:
                why = precheck(names)
                st["challenge_at"], st["challenge_ok"], st["challenge_error"] = now_iso(), not why, why
                if not why:
                    issued_one = True
                    say(f"{host}: requesting a certificate for {' '.join(names)}")
                    err = issue(host, h["www"], email)
                    st["cert_tried_at"], st["cert_error"] = now_iso(), err
                    info = cert_info(host)
                    if not err and not covers(info, host, h["www"]):
                        st["cert_error"] = "certbot finished but the certificate does not cover " + " ".join(names)
                    say(f"{host}: {'certificate ok' if not st['cert_error'] else 'certificate failed: ' + st['cert_error']}")
                else:
                    say(f"{host}: pre-check failed — {why}")
        st["cert_ok"] = covers(info, host, h["www"])
        st["cert_expires"] = info.get("expires", "")
        if st["cert_ok"]:
            st["cert_error"] = ""
        status[host] = st

    # nginx files: every wanted host with a certificate (a host whose file just failed waits 10 min)
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {h["host"]: render(h) for h in hosts if status[h["host"]]["cert_ok"]}
    current = {p.stem: p.read_text() for p in CONF_DIR.glob("*.conf")}
    changed = [n for n, txt in wanted.items() if current.get(n) != txt
               and not (status[n].get("nginx_error") and ago(status[n].get("nginx_at")) < NGINX_BACKOFF)]
    gone = [n for n in current if n not in wanted]
    if changed or gone:
        backup = Path(tempfile.mkdtemp(prefix=".bak-", dir=CONF_DIR.parent))
        try:
            for n in current:
                shutil.copy2(CONF_DIR / f"{n}.conf", backup / f"{n}.conf")
            for n in changed:
                (CONF_DIR / f"{n}.conf").write_text(wanted[n])
                os.chmod(CONF_DIR / f"{n}.conf", 0o644)
            for n in gone:
                (CONF_DIR / f"{n}.conf").unlink(missing_ok=True)
            why = nginx_test_reload()
            bad = {} if why else {n: e for n in changed
                                  if (e := verify_tls(n, f"/.well-known/caspin/{tokens[n]}", tokens[n]))}
            if why or bad:
                for p in CONF_DIR.glob("*.conf"):
                    p.unlink()
                for p in backup.glob("*.conf"):
                    shutil.copy2(p, CONF_DIR / p.name)
                nginx_test_reload()
                say(f"nginx: restored the previous store files — {why or bad}")
                for n in changed:
                    status[n].update(nginx_error=why or bad.get(n) or "another store's file failed", nginx_at=now_iso())
            else:
                say(f"nginx: applied {len(changed)} changed, {len(gone)} removed store file(s)")
                for n in changed:
                    status[n].update(nginx_error="", nginx_at=now_iso())
        finally:
            shutil.rmtree(backup, ignore_errors=True)
    for n, st in status.items():
        f = CONF_DIR / f"{n}.conf"
        st["nginx_ok"] = n in wanted and f.exists() and f.read_text() == wanted[n]
        if st["nginx_ok"]:
            st["nginx_error"] = ""
        st["at"] = now_iso()
    # certificates of hosts nobody wants any more
    if (LE / "live").exists():
        keep = {lineage(h["host"]) for h in hosts}
        for d in (LE / "live").iterdir():
            if d.name.startswith("store-") and d.name not in keep:
                say(f"removing the certificate of {d.name[6:]} (domain no longer wanted)")
                delete_cert(d.name[6:])
    save(STATUS, {"at": now_iso(), "hosts": status})
    return 0


def env_value(key: str) -> str:
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def show() -> int:
    print(json.dumps({"desired": load(DESIRED, None), "status": load(STATUS, None),
                      "files": sorted(p.name for p in CONF_DIR.glob("*.conf"))}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    sys.exit(run() if cmd == "apply-request" else show() if cmd == "show" else 2)
