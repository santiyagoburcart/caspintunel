"""
Configure Cloudflare DNS for the self-hosted stack (idempotent).

    python manage.py configure_dns                 # dry-run: show planned changes
    python manage.py configure_dns --apply         # actually write records

Records managed (nothing else is touched — existing VPN-node records are left alone):
  A     <domain>            -> SERVER_IP   (proxied / orange cloud)
  A     www                 -> SERVER_IP   (proxied)
  A     mail                -> SERVER_IP   (DNS-only / grey cloud — SMTP needs a real IP)
  MX    <domain>            -> mail.<domain>  priority 10
  TXT   <domain>            -> "v=spf1 mx a:mail.<domain> ~all"
  TXT   _dmarc              -> "v=DMARC1; p=quarantine; rua=mailto:postmaster@<domain>; adkim=s; aspf=s"
  TXT   <sel>._domainkey    -> DKIM public key (generated if a keypair isn't supplied)

The DKIM private key is written to backend/mail-keys/<selector>.private — point your
mail server (OpenDKIM / docker-mailserver) at it.
"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ops.cloudflare import Cloudflare, CloudflareError

KEY_DIR = Path(settings.BASE_DIR) / "mail-keys"


class Command(BaseCommand):
    help = "Create/update Cloudflare DNS records for the site + self-hosted mail."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
        parser.add_argument("--server-ip", default=getattr(settings, "SERVER_IP", "") or None)
        parser.add_argument("--domain", default=getattr(settings, "CLOUDFLARE_ZONE", None)
                            or getattr(settings, "DOMAIN", "caspin.skin"))
        parser.add_argument("--dkim-selector", default="default")

    def handle(self, *args, **o):
        token = getattr(settings, "CLOUDFLARE_API_TOKEN", "")
        if not token:
            raise CommandError("CLOUDFLARE_API_TOKEN is not set")
        ip = o["server_ip"] or _detect_ip()
        if not ip:
            raise CommandError("could not determine the server IP — pass --server-ip")
        domain = o["domain"]
        selector = o["dkim_selector"]
        apply = o["apply"]

        cf = Cloudflare(token)
        try:
            zone = cf.zone_id(domain)
        except CloudflareError as exc:
            raise CommandError(str(exc))

        dkim_txt = self._ensure_dkim(selector, apply)

        plan = [
            dict(type="A", name=domain, content=ip, proxied=True),
            dict(type="A", name=f"www.{domain}", content=ip, proxied=True),
            dict(type="A", name=f"mail.{domain}", content=ip, proxied=False),   # DNS-only
            dict(type="MX", name=domain, content=f"mail.{domain}", priority=10),
            dict(type="TXT", name=domain, content=f"v=spf1 mx a:mail.{domain} ~all",
                 match_prefix="v=spf1"),
            dict(type="TXT", name=f"_dmarc.{domain}", match_prefix="v=DMARC1",
                 content=f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{domain}; adkim=s; aspf=s"),
            dict(type="TXT", name=f"{selector}._domainkey.{domain}", content=dkim_txt,
                 match_prefix="v=DKIM1"),
        ]

        self.stdout.write(f"zone {domain} ({zone[:8]}…) · server IP {ip} · {'APPLY' if apply else 'dry-run'}\n")
        for rec in plan:
            desc = f"{rec['type']:5} {rec['name']:34} -> {rec['content'][:52]}"
            if not apply:
                self.stdout.write(f"  plan  {desc}")
                continue
            try:
                res = cf.upsert(zone, **rec)
                self.stdout.write(self.style.SUCCESS(f"  {res['action']:9} {desc}"))
            except CloudflareError as exc:
                self.stdout.write(self.style.ERROR(f"  FAILED   {desc}\n           {exc}"))

        if not apply:
            self.stdout.write("\nre-run with --apply to write these records")
        else:
            self.stdout.write(self.style.WARNING(
                f"\nDKIM private key: {KEY_DIR / (selector + '.private')} — configure your mail server with it."
            ))

    def _ensure_dkim(self, selector: str, apply: bool) -> str:
        priv = KEY_DIR / f"{selector}.private"
        pub = KEY_DIR / f"{selector}.txt"
        if priv.exists() and pub.exists():
            return _dkim_record(pub.read_text())
        if not apply:
            return "v=DKIM1; k=rsa; p=<generated on --apply>"
        KEY_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["openssl", "genrsa", "-out", str(priv), "2048"],
                       check=True, capture_output=True)
        der = subprocess.run(["openssl", "rsa", "-in", str(priv), "-pubout", "-outform", "DER"],
                             check=True, capture_output=True).stdout
        p = base64.b64encode(der).decode()
        record = f"v=DKIM1; k=rsa; p={p}"
        pub.write_text(record)
        priv.chmod(0o600)
        return record


def _dkim_record(text: str) -> str:
    text = text.strip()
    return text if text.startswith("v=DKIM1") else f"v=DKIM1; k=rsa; p={text}"


def _detect_ip():
    import requests

    try:
        return requests.get("https://api.ipify.org", timeout=5).text.strip()
    except requests.RequestException:
        return None
