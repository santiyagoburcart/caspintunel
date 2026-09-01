# Install

## Requirements
- Linux host with Docker Engine + Compose v2
- A domain on Cloudflare (for DNS + mail records)
- Panel (PasarGuard) admin credentials

## Quick start

```bash
git clone <repo> caspintunel && cd caspintunel
./install.sh            # dev
./install.sh --prod     # production
```

`install.sh` will:
1. create `.env` (prompts for IP, domain, DB/panel/admin credentials, optional Cloudflare + GitHub tokens) and generate `SECRET_KEY` + `FIELD_ENCRYPTION_KEY`
2. build images and start the stack
3. `migrate`, `seed` (permissions, roles, Midnight Aurora theme, settings, CMS pages, panel row, beat schedules, a Super Admin `Staff` from the admin credentials)
4. create the Django superuser
5. optionally run `configure_dns --apply` and `scripts/setup_github.sh`

## After install

| URL | |
|---|---|
| `/` | user site |
| `/panel/` | admin panel — log in with the admin credentials from install |
| `/api/docs/` | Swagger |
| `/admin/` | Django admin (break-glass) |
| `:8080` | phpMyAdmin (dev only) |

Set in the panel (`/panel/`):
- **Panel → default group ids** — `Plan.group_ids` / `Panel.default_group_ids`; run `manage.py panel_check` to list them
- **Telegram** — paste the sales/backup bot tokens (stored encrypted); the bot containers pick them up within 60 s
- **Bank cards**, **plans**, **SMS sender numbers + device tokens**

## Manual `.env`

```bash
cp .env.example .env      # fill every blank; generate the two keys:
python3 -c "import secrets;print(secrets.token_urlsafe(64))"                 # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"  # FIELD_ENCRYPTION_KEY
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
