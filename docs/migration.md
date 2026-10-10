# Moving to a new server

فارسی: [migration-fa.md](migration-fa.md)

Move the whole installation (database, media, settings, keys, mail config, TLS)
to another server with a few minutes of downtime, and with the old server kept
as a ready rollback.

| Script | Where | What |
|---|---|---|
| `scripts/migrate-export.sh` | OLD server | one encrypted archive + manifest; `--final` = maintenance + bots/celery on hold first |
| `scripts/migrate-import.sh` | NEW server | verify, restore, migrate, compare counts; bots/celery stay on hold until `--start-workers` |
| `scripts/migrate-check.sh` | anywhere | test the new server before DNS is switched |
| `scripts/test-migration.sh` | dev | end-to-end test of the toolkit on two throw-away stacks |

## What moves — and what does not

**In the archive** (AES-256, passphrase): a consistent MySQL dump (single
transaction), the complete media volume (receipts, branding, uploaded apps, QR
backgrounds), `.env`, `mail/config` (DKIM keys, if this server has any), the TLS
certificates (`nginx/letsencrypt`, `nginx/manual-certs`) and `manifest.json`:
version, commit, exact row count of every table, number of media files, SHA-256
of every part and of every media file, and hashes of `SECRET_KEY` /
`FIELD_ENCRYPTION_KEY` (hashes only — to prove the same keys arrived).

**Kept from the new server's own `.env`:** `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`DB_ROOT_PASSWORD`, `DB_HOST`, `DB_PORT`, `COMPOSE_FILE`, `SERVER_IP` (its MySQL
volume was created with those passwords). Everything else — above all
`SECRET_KEY` and `FIELD_ENCRYPTION_KEY` — comes from the old server, so sessions
stay valid and the panel password, bot tokens and SMTP password still decrypt.

**Not moved:** Redis (cache, bot "typing" state — rebuilt on its own), the old
`backups/` folder (copy it separately with `rsync` if you want the history),
mail queue and logs, Docker images (rebuilt by the install), the host's cron
lines, and anything on the old server that is not part of caspintunel.

## Two safety switches

- **Maintenance mode** — the file `nginx/flags/maintenance`. While it exists
  every request gets a 503 "moving to a new server" page (fa/en) and nothing
  reaches Django: no order, receipt or bank SMS can arrive. Let's Encrypt
  challenges keep working.
- **Worker hold** — `MIGRATION_HOLD=1` in `.env`. The four worker containers
  (`bot_sales`, `bot_backup`, `celery_beat`, `celery_worker`) start but stay idle.
  It survives reboots and `./update.sh`. This is what guarantees the same
  Telegram bot never polls from two servers, and that no scheduled task changes
  the data during the copy.

`migrate-export.sh --final` turns both on (old server); `migrate-import.sh`
leaves the hold on (new server) until you run `--start-workers`.

## Recommended server

Measured on the current server (October 2026): the caspintunel containers use
about **1.2 GB RAM** at rest, the database is ~31 MB, media ~15 MB (828 files),
`backups/` 3.3 GB, Docker images + build cache ~15 GB; CPU load ≈ 0.2 on 2 vCPU.

| | Minimum | Recommended |
|---|---|---|
| CPU | 2 vCPU | 2–4 vCPU |
| RAM | 4 GB (+ 2 GB swap; image builds need it) | 8 GB |
| System disk | 40 GB SSD | 40–60 GB SSD |
| Data disk | — | separate 40–50 GB volume mounted at `/data` |
| OS | Ubuntu 22.04 / 24.04, Docker Engine + Compose v2 | same |
| Network | ports 80/443 in; **587 out** (SMTP relay); reaches the PasarGuard panel and api.telegram.org (or a `TELEGRAM_PROXY_URL`) | same |

Using the data disk — do this **before** installing:

```bash
# /data is the mounted data volume
mkdir -p /data/docker /data/caspintunel-backups
echo '{ "data-root": "/data/docker" }' > /etc/docker/daemon.json && systemctl restart docker   # DB + media volumes live here
git clone https://github.com/santiyagoburcart/caspintunel.git /root/caspintunel
ln -s /data/caspintunel-backups /root/caspintunel/backups     # DB dumps + migration archives
```

Growing or replacing the server later then only means re-attaching `/data`.

## Runbook

Downtime = steps 4 → 7, typically 5–15 minutes. Steps 1–3 can be done days ahead.

### 1. Prepare (days before)

1. Old server: be on the latest release (`./update.sh`) — the toolkit and the
   maintenance switch arrive with v1.8.2.
2. Cloudflare → DNS: lower the **TTL** of the `A` records (`@`, `www`, `mail`) to
   **1–2 minutes** at least a day before (or as long as the old TTL). With the
   orange-cloud proxy the switch is instant and the TTL does not matter.
3. New server: prepare `/data` (above), then install the **same version**:
   ```bash
   cd /root/caspintunel && git checkout v$(ssh root@OLD_IP cat /root/caspintunel/VERSION)
   ./install.sh        # same domain; any admin user (it is replaced by the import)
   ```
   Let's Encrypt cannot issue yet (DNS still points to the old server) — that is
   expected; the import brings the existing certificate.
4. If the PasarGuard panel or the SMTP provider has an **IP allow-list**, add the
   new server's IP now.
5. Choose a passphrase (12+ characters) and keep it somewhere safe:
   `echo 'your long passphrase' > /root/.migrate-pass && chmod 600 /root/.migrate-pass`
   on both servers (or type it when asked).

### 2. Test copy (site stays online)

```bash
# OLD server — read-only, no downtime
./scripts/migrate-export.sh --passphrase-file /root/.migrate-pass

# NEW server
mkdir -p backups/migration
rsync -avP -e ssh root@OLD_IP:/root/caspintunel/backups/migration/caspintunel-migration-*.tar.enc* backups/migration/
./scripts/migrate-import.sh backups/migration/caspintunel-migration-<…>.tar.enc --passphrase-file /root/.migrate-pass
```

The import ends with web running and **bots + celery on hold**. A test copy of a
live site may show a few differing row counts in busy tables (rows written
between the dump and the count); the final export must match exactly.

### 3. Test the new server before switching DNS

```bash
./scripts/migrate-check.sh NEW_IP aicaspin.ir       # from anywhere; DNS is not touched
```

It checks TLS, the user site, the panel, the API, that the SMS device API and the
WebSocket endpoint answer, and that receipts are not public. Then test in a
browser by pointing **your own computer** at the new server — add to its hosts
file (`/etc/hosts`, or `C:\Windows\System32\drivers\etc\hosts`), test in a private
window, and remove the line afterwards:

```
NEW_IP  aicaspin.ir
```

Checklist:

- [ ] customer login → dashboard shows the same services and usage
- [ ] a service's **QR** opens (branded background); the subscription link is unchanged
- [ ] purchase history shows the old orders
- [ ] `/panel/` staff login → dashboard numbers equal the old server's
- [ ] **payments queue** lists the pending payments, a receipt opens, the "online" dot is green (**WebSocket**)
- [ ] Panel connection → **Test connection** is green (**PasarGuard** reachable from the new IP); `docker compose exec web python manage.py panel_check`
- [ ] Services → open one → live usage loads
- [ ] Settings → Email → **Send test email** arrives
- [ ] Settings → SMS devices are listed; SMS log shows the old messages (**SMS inbound** itself is verified by `migrate-check.sh`; phones keep posting to the domain, so they follow DNS)
- [ ] branding, plans, bank cards, pages, themes look the same
- [ ] `./scripts/migrate-import.sh --status` → `MIGRATION_HOLD 1`

Do **not** pay or approve a real order on the new server yet: nothing is
delivered while the workers are on hold, and the final import replaces this copy.

### 4. Maintenance + final export (downtime starts)

Pick a quiet hour. Approve or reject what is in the payments queue first.

```bash
# OLD server
./scripts/migrate-export.sh --final --passphrase-file /root/.migrate-pass
```

Site → 503 page, bots + celery → on hold, then the export. A bank SMS that
arrives during the downtime is not received: check the card statement for
payments made in that window and approve them by hand afterwards.

### 5. Import the final archive

```bash
# NEW server
rsync -avP -e ssh root@OLD_IP:/root/caspintunel/backups/migration/caspintunel-migration-*-final.tar.enc* backups/migration/
./scripts/migrate-import.sh backups/migration/caspintunel-migration-<…>-final.tar.enc --passphrase-file /root/.migrate-pass
```

It must print **"row counts match the manifest in every table"** and the media
checksum line. If it does not, stop and roll back (below).

### 6. Switch DNS

Cloudflare → DNS → change the `A` records `@`, `www` (and `mail`) to the new IP,
or on the new server: `docker compose exec web python manage.py configure_dns`
(dry run; add `--apply`) — it uses this server's `SERVER_IP` and also rewrites the
SPF record. Check: `dig +short aicaspin.ir` shows the new IP.

### 7. TLS, then start the workers (downtime ends)

The copied certificate already works. Renewal runs by itself once DNS points
here; to issue a fresh one now: `./scripts/init-letsencrypt.sh --prod`.

```bash
# NEW server — only after DNS points here and the old server is in maintenance/hold
./scripts/migrate-import.sh --start-workers
```

### 8. Verify

- `./scripts/migrate-check.sh NEW_IP aicaspin.ir` again, then without the hosts line
- send `/start` to the sales bot; open the Mini App
- `docker compose logs --tail 20 bot_sales celery_worker` — no errors
- Monitoring page: all health targets green; run a backup
- one small real purchase end to end (order → pay → SMS/receipt → service)
- re-add the host cron lines you use (e.g. `scripts/watch-update.sh` for the Update button, see `deploy.md`)

### 9. Keep the old server parked

Leave it **running in maintenance with the hold on** (or powered off) for a few
days — do not delete it. Do **not** run `--resume` there while the new server is
live. After a few good days: take a last copy of `backups/`, then destroy it and
set the DNS TTL back to normal.

## Rollback

**Before the workers were started on the new server** (steps 4–6) — nothing was
written anywhere else, so going back is instant:

```bash
# OLD server
./scripts/migrate-export.sh --resume     # site open, bots + celery running again
```

and point DNS back to the old IP if you had already changed it.

**After the new server went live** — orders and payments now exist only on the
new server. Either fix the problem there, or move *back* with the same procedure
in the other direction: `migrate-export.sh --final` on the new server → import on
the old one →
DNS back → `--start-workers` on the old one. Never just `--resume` the old server
at that point: its data is stale and two bots would run.

**A failed import on the new server** changes nothing on the old one. What the
new server had before each import is kept in `backups/migration/before-import-<time>/`
(`env`, `db.sql.gz`, `mail-config.tar`); simply run the import again.

## Migration day — the commands

```bash
# OLD
./scripts/migrate-export.sh --final --passphrase-file /root/.migrate-pass
# NEW
rsync -avP -e ssh root@OLD_IP:/root/caspintunel/backups/migration/caspintunel-migration-*-final.tar.enc* backups/migration/
./scripts/migrate-import.sh backups/migration/caspintunel-migration-*-final.tar.enc --passphrase-file /root/.migrate-pass
./scripts/migrate-check.sh NEW_IP aicaspin.ir
#   → change the A records in Cloudflare to NEW_IP
./scripts/migrate-import.sh --start-workers
```

## Testing the toolkit

`./scripts/test-migration.sh` builds two throw-away stacks (`migtest-src`,
`migtest-dst`: own networks and volumes, no published ports, different keys and DB
passwords), fills the first with fake data, and runs export → import → compare,
the guards (wrong passphrase, damaged archive, import on the source machine), the
final export with maintenance + hold, the second import with an exact per-table
comparison, `--start-workers` and `--resume`. It never touches the live stack.
