# Offline / air-gapped install

For a server with **no internet access** (e.g. behind national filtering). The
codebase is already offline-friendly:

- **Fonts** (Vazirmatn) and all JS/CSS are bundled at build time — nothing is
  fetched from a CDN at runtime.
- **Images** can be built on an online machine and carried over.
- **TLS** can be a manually-uploaded cert instead of Let's Encrypt.
- The installer has an **offline mode** that skips every internet step.

## 1. On an ONLINE machine (same CPU arch as the target)

```bash
git clone <repo> caspintunel && cd caspintunel
./scripts/save-images.sh                 # -> dist/caspintunel-images-<version>.tar.gz
```

This builds `caspintunel-backend`, `caspintunel-nginx`,
`caspintunel-frontend-user`, `caspintunel-frontend-admin`, pulls `mysql`,
`redis`, `phpmyadmin`, `certbot`, `docker-mailserver`, and `docker save`s them
all into one gzip.

## 2. Get a TLS cert (online, once)

Obtain a cert for the domain on any reachable machine — DNS-01 with your DNS
provider, or HTTP-01 on a jump host, or a commercial cert. You need two files:
`fullchain.pem` (leaf + intermediates) and `privkey.pem`.

## 3. Carry to the air-gapped server

Copy over: the **repo**, `caspintunel-images-<version>.tar.gz`, and the two cert
files.

## 4. On the AIR-GAPPED server

```bash
./scripts/load-images.sh caspintunel-images-<version>.tar.gz
./install.sh --offline
```

In the menu → **1) Install**. Offline mode:
- uses the loaded images (no build, no pull)
- forces **manual TLS** — after install run:
  ```bash
  ./scripts/ssl-manual.sh --prod  /path/fullchain.pem  /path/privkey.pem
  ```
- generates `SECRET_KEY` + `FIELD_ENCRYPTION_KEY` locally (needs `python3` +
  `cryptography`, or run the install once on the online box to seed `.env`)
- skips DNS automation — set the `A @` / `A www` records at your DNS provider by
  hand, pointing at the server IP

Then log into `/panel/` and enter the Pasargad panel credentials + bot tokens.

## 5. Updates (offline)

On the online machine: `git pull` → `./scripts/save-images.sh`. Carry the new
bundle over, `./scripts/load-images.sh <new bundle>`, then `./install.sh --offline`
→ **2) Update**.

## What is NOT done yet (final Iran step)

- No pinned image digests / private registry mirror — `save-images.sh` captures
  whatever tags are current.
- `configure_dns` (Cloudflare automation) is unused offline; DNS is manual.
- The mail server can still only relay outbound through `SMTP_RELAY_*` (or a
  reachable smarthost) — direct MX delivery needs outbound port 25.
- Fail2ban / host hardening for a public Iran IP is out of scope here.
