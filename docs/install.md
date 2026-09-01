# Install

## Requirements
- Linux host with Docker Engine + Compose v2
- A domain (DNS you control)
- Ports 80 + 443 reachable (for Let's Encrypt; not required with a manual cert)

## One command

```bash
git clone <repo> caspintunel && cd caspintunel
./install.sh
```

`./install.sh` opens a menu:

```
1) Install    2) Update    3) Uninstall    4) Exit
```

It detects whether the stack is already installed and shows the deployed VERSION.

### Install
Prompts for: **domain**, **site-admin username / password / email**, **DB password**
+ **DB root password**, timezone, phpMyAdmin port, and the **TLS mode**:

- **auto** — Let's Encrypt (needs inbound port 80 from the internet)
- **manual** — you upload `fullchain.pem` + `privkey.pem` (`./scripts/ssl-manual.sh`)

It generates `SECRET_KEY` + `FIELD_ENCRYPTION_KEY`, writes `.env` (`chmod 600`),
builds, starts, migrates, seeds, and creates the superuser.

**It does NOT ask for the Pasargad panel credentials.** After install, log into
`https://<domain>/panel/` (or `/admin/`) and enter the panel base URL + admin
username/password under **Panel settings** — plus bot tokens, bank cards, plans,
SMS devices.

### Update
Fails with *"not installed"* if there's no `.env`/stack. Otherwise: `git pull` →
build → `up` → `migrate` + `seed` → `collectstatic`.

### Uninstall
Confirms by re-typing the domain, then `docker compose down -v` and (optionally)
removes `.env`, certs, mail data and backups.

## Offline / air-gapped

`./install.sh --offline` — see **[offline.md](offline.md)**.

## Manual `.env`

```bash
cp .env.example .env      # fill every blank; generate the two keys:
python3 -c "import secrets;print(secrets.token_urlsafe(64))"                 # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"  # FIELD_ENCRYPTION_KEY
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
