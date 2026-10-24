# Domain & Cloudflare

**Settings → Domain & Cloudflare** (`/panel/settings/domain`, super admins only) holds the Cloudflare API token and
moves the whole site to a new domain step by step, with a status per step, a transition period for the old domain
and a one-click rollback. Recovery on the server: `./scripts/domain.sh show | rollback`.

## Cloudflare token

* Stored **encrypted** in the DB (`domain_config.cloudflare_token`, `FIELD_ENCRYPTION_KEY`), write-only like the bot
  tokens: the API never returns it. `.env` `CLOUDFLARE_API_TOKEN` stays the fallback (`ops/cloudflare.configured_token`:
  panel first, then .env — also used by `manage.py configure_dns`).
* **Test** verifies the typed token, or else the saved one: `GET /user/tokens/verify` (must be *active*), then every
  zone it can see is **really checked** (`Cloudflare.check_zone`): list its records (*can read*), create a temporary TXT
  `_caspintunel-check-<random>.<zone>` and delete it right away (*can edit DNS*) — Cloudflare's reported permissions
  alone are not trusted. The page shows a table *zone | can read | can edit DNS* with the fix under each refused zone
  (first 25 zones; a test record that could not be deleted is named so it can be removed by hand). Token for the
  wizard: *Zone → Zone → Read* + *Zone → DNS → Edit*, Zone Resources including the domain.
* The same check runs automatically for the chosen zone **before step b** writes anything; a refused zone stops there
  (`dns` step *failed*, nothing written).

## Errors

Every failure is explained (`apps/settings_app/domain_errors.py`) as `{key, en, fa, raw}`: a sentence with the fix in
both languages, and under it a small *details* line with the raw code + message (Cloudflare `code: message`, the DoH
answers, certbot's `Type:` / `Detail:`, the `nginx -t` error, …). API: a refused action answers 400 with
`detail` (en), `detail_fa`, `error` ({key, en, fa, raw}); steps carry `detail.error`, DNS / mail rows `why`, the token
test `explain` (+ `error`, `error_fa`), the last host result `explain`.

| Source | Keys |
|---|---|
| Cloudflare API | `cf_perm` (10000, 9109, 6003, 9103 — no DNS edit in zone X: *My Profile → API Tokens → Edit → Permissions: Zone·DNS·Edit, Zone Resources incl. X*), `cf_invalid` (1000, 6111, 9106, "Invalid access token"), `cf_inactive`, `cf_ip` (client IP filtering), `cf_zone` (7003, 7000, 1001, 1049 / not among the token's zones), `cf_rate` (HTTP 429, 971), `cf_exists` (81057/81058), `cf_cname` (81053–81055), `cf_record` (1004, 9xxx), `cf_down` (network / 5xx), `cf_no_zones`, `cf_no_edit`, `cf_no_token` |
| DNS check | `dns_none`, `dns_proxied` (answer in Cloudflare's IP ranges = orange cloud), `dns_wrong` (other IP / TTL), `dns_partial` (propagating), `dns_doh` (resolvers unreachable) |
| Mail DNS | `mail_missing`, `mail_mx` (MX elsewhere), `spf_multi` (two `v=spf1`), `mail_diff` (old DKIM / foreign SPF), `mail_no_dkim` |
| certbot | `le_rate`, `le_dns`, `le_caa`, `le_port80`, `le_challenge`, `le_check`, `manual_cert`, `dkim_fail`, `le_other` |
| switch | `nginx_test`, `apply_health`, `apply_redirect`, `apply_container`, `apply_mail`, `apply_env`, `apply_moved`, `rb_none`, `apply_other` |
| wizard rules | `bad_domain`, `same_domain`, `busy_change`, `queued`, `need_dns`, `need_tls`, `need_mail`, `nothing_rb`, … |

## The wizard

| Step | Where | What happens |
|---|---|---|
| a) new domain | panel | domain (+ `www`), the Cloudflare zone (auto-picked from the token's zones) or **manual DNS** |
| b) DNS | panel → Cloudflare API | A records `@`, `www`, `mail` → this server's IP (`SERVER_IP`), DNS-only. Manual: the exact records to create. **Check DNS** asks public DNS-over-HTTPS resolvers (Cloudflare, Google) — what Let's Encrypt sees; all three must answer this IP |
| c) TLS + DKIM | host | `certbot certonly --webroot --cert-name <domain>` for `@`, `www`, `mail.` in the certbot container; the cert is checked (valid, covers the names). The **mail server makes the DKIM key** for the new domain (`setup config dkim domain <new>`, selector `mail`, kept if it exists); its public record goes to `backups/.domain-dkim.json` |
| c2) mail DNS | panel → Cloudflare API | right after the certificate: **MX** `mail.<new>` (10), **SPF** `v=spf1 ip4:<IP> mx ~all`, **DMARC** `v=DMARC1; p=none; adkim=r; aspf=r`, **DKIM** `mail._domainkey` (other TXT records on those names are left alone). Manual: the exact records. Checked through public DoH — apply waits until all four answer |
| d) apply | host | see below — all or nothing |
| e) transition | host | the old domain answers **301** to the new one (308 for POST etc., so e.g. the SMS app's POSTs keep their body) for `transition_days` (setting, default 14; 0 = none). Then the beat task asks the host to remove it, or **Remove the old domain now** |
| f) checklist | panel | manual steps with links: iPhone Shortcut URL, Android SMS app URL, BotFather (login domain / Mini App link), **reverse DNS (PTR)** of the IP → `mail.<new>` in the Hetzner console (the only manual mail step), tell resellers / customers |

**Apply** (`scripts/domain.sh`): certificate check → `nginx/domain/active.conf` (HTTPS vhost of the new domain + the
old domain's redirect vhosts) → `nginx -t` + reload → `.env`: `DOMAIN`, `PUBLIC_BASE_URL`, `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS` (+ the new names; the old ones stay until the transition ends), `MINIAPP_URL` (if it used the old
domain), `CLOUDFLARE_ZONE`, **`MAIL_DOMAIN`** = new (mail server hostname `mail.<new>`, its TLS cert from
`live/<new>/`, postmaster) and `DEFAULT_FROM_EMAIL` `@old` → `@new` → app containers recreated with the new `.env`
(`web`, `daphne` rolling like `update.sh`; celery, bots, **mailserver**) → **verify through nginx over TLS**:
`https://<new>/api/v1/health/` = 200, the old domain redirects, and the mail server is healthy as `mail.<new>`. Any failure:
`.env`, the nginx config and the containers go back to the previous state and the reason is shown.

After a successful apply the panel updates the email sender (`email_settings.from_email` `@old` → `@new`), `site_config.site_domain` (portal / renew / ticket / bot / Shortcut links —
unless it was set by hand to something else) and the sales bot's **Mini App menu button** (Telegram
`setChatMenuButton`). Email links follow `PUBLIC_BASE_URL`.

**Rollback** (panel button or `./scripts/domain.sh rollback`): the same switch back to the previous domain (mail too:
`MAIL_DOMAIN` back, mail server recreated) (its
certificate must still be valid — certbot keeps renewing it while its DNS points here); the current domain is no
longer served.

Every step is audit-logged (`domain.*`); every action and host result is a toast with the real reason.

## Files

| File | Written by | |
|---|---|---|
| `backups/.domain-request.json` | panel | one request at a time; the host deletes it before acting (never a loop) |
| `backups/.domain-status.json` | host | last result `{id, action, ok, message, at}` — folded into the wizard by `domain.sync()` (on every panel call and every 5 min in beat) |
| `backups/.domain-state.json` | host | current / old / previous domain (no secrets) |
| `backups/.domain-dkim.json` | host | public DKIM record of the new domain (from the mail server) for the mail DNS step |
| `mail/config/opendkim/keys/<domain>/` | mail server | DKIM keys (private key never leaves the mail server's config) |
| `nginx/domain/active.conf` | host | mounted at `/etc/nginx/domain`; when present the nginx entrypoint includes it instead of the `.env` domain's vhost (a manual upload in `nginx/manual-certs` still wins — the wizard refuses while one is active) |
| `.domain-state/` | host | root-only: `state.json`, the `.env` / nginx backups of the switch in progress |

The host side runs from cron, like Paths:

```cron
* * * * * /root/caspintunel/scripts/domain.sh apply-request >> /var/log/caspintunel-domain.log 2>&1
```

## Test

`./scripts/test-domain.sh` — throw-away stack (`domaintest`), fake domains `old.test → new.test`, a mock Cloudflare
API + DoH (`scripts/domaintest/cfmock.py`) and a fake certbot (self-signed); everything else real: token save / test,
DNS records, DNS check, certificate, **real docker-mailserver**: DKIM key, mail records (MX/SPF/DMARC/DKIM) published and
checked, mail server recreated as `mail.<new>` with a STARTTLS cert covering it, sender moved; apply (redirects 301/308, `.env`, rolling restart, nginx restart), retire,
panel rollback, an apply that fails `nginx -t` and is rolled back, CLI rollback, audit. Unit tests:
`apps/adminpanel/tests/test_domain.py`.
