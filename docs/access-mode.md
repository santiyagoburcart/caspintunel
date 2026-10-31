# Access mode — Direct / Cloudflare proxy / Iran tunnel

**Settings → Domain & Cloudflare → Access mode** (super admins). One domain, no
subdomains, three ways for visitors to reach it. Switchable any time from the
panel, without downtime, with one click back. `mail.<domain>` is **never touched**
(always DNS-only → this server). The current mode is shown in the page header.

| Mode | DNS (`@` and `www`) | Real visitor IP | Notes |
|---|---|---|---|
| **Direct** | A → this server, grey cloud (TTL 60) | the TCP peer | |
| **Cloudflare proxy** | A → this server, **orange cloud** | `CF-Connecting-IP`, trusted **only from Cloudflare's published ranges** (refreshed daily) | SSL/TLS must be **Full (strict)** — checked and set with the token, else refused |
| **Iran tunnel** | A → the **Iran IP(s)** (panel field), grey cloud (TTL 60) | unknown without PROXY protocol (everyone = the tunnel source) | requests from the tunnel sources are limited per user / session, not per IP |

Nothing about the tunnel is hard-coded: the **Iran public IP(s)** (the A record —
editing it in tunnel mode updates DNS, verified), the **tunnel source IPs**
(IPv4 / IPv6 / CIDR, private ranges, `127.0.0.1`; **Auto-detect** sends a test
request through the tunnel and shows the address this server saw) and **PROXY
protocol per port** (off by default) are panel fields. Backhaul, GRE, GRE over
IPv6, GOST, plain port forwards — anything that delivers TCP 443 (and 80) here works.

`www` keeps pointing where `@` points in every mode; nginx answers it with a 301 to `https://<domain>` (docs/domain.md
"`www` → bare domain"). The re-render after a mode / source / PROXY change (`scripts/domain.sh access`) keeps that
redirect, including on the PROXY-protocol listeners.

## A switch (`settings_app/access.py`, Celery task)

1. **check** — Cloudflare token + zone; proxy mode: SSL/TLS Full (strict) (set via API, else stop).
2. **preverify** — the new path *before* DNS changes: a real HTTPS request for the domain
   (SNI + Host) to the Iran IP(s) (tunnel) or to this server (direct / proxy origin): our
   certificate, status 200 and our `X-Caspin-Instance` header (proves the answer came from
   THIS server, not something else on the Iran box). Failure → nothing changes.
3. **dns** — A records of `@` and `www` set exactly (updated in place first, extras removed
   last, so the name never resolves to nothing); previous records saved.
4. **propagate** — public DNS-over-HTTPS until it answers the new records (proxy: Cloudflare edges).
5. **verify** — the path again (proxy: through a Cloudflare edge). Failure → **DNS put back**
   automatically (`revert`), status *reverted* with the reason in fa/en + raw details.

**Back to the previous mode** = the same switch to the last mode. "Skip the path check" exists
only for an Iran IP that can't be reached from abroad — then nothing proves the path works.

## nginx (same in every mode; `scripts/domain.sh access`)

* `nginx/domain/realip.conf` — `set_real_ip_from <Cloudflare ranges>; real_ip_header CF-Connecting-IP;`
  in the HTTPS vhost and the port-80 server. A `CF-Connecting-IP` from anyone else is ignored.
* `X-Conn-Addr` — the TCP peer (`$realip_remote_addr`), set by nginx only, so Django can tell a
  tunnel request (peer in the source list and no better client address) from a normal one.
* PROXY protocol (optional, per port): extra listeners in `active.conf` —
  **443 → this server `:8843`** (TLS) and **80 → `:8880`**, `ACCESS_PROXY_HTTPS_PORT` /
  `ACCESS_PROXY_HTTP_PORT` in `.env`. They take the client address from the PROXY header, accept
  it only from the tunnel sources and close the connection (444) for anyone else. Point the tunnel
  at these ports only when it sends the PROXY header.
* Every change: render → `nginx -t` → reload → verify → restore on failure (host status in the panel).

## Limits behind a tunnel (`apps/common/throttling.py`)

DRF's anon / user / scoped throttles are tunnel-aware: a request from a tunnel source whose
client address nginx could not resolve is keyed by the SPA's random `X-Client-Id` (else a hash
of browser headers), logged-in users by account as always, and one cap (`THROTTLE_TUNNEL_TOTAL`,
6000/min) bounds all tunnel traffic together. No web fail2ban jail exists (only `sshd`, `3x-ipl`);
nginx has no per-IP limits. **Duplicate IP is expected in tunnel mode** (the panel says so).

On this server a tunnel that lands on the host (and every IPv6 visitor) reaches nginx through
Docker's userland proxy, so nginx sees the **Docker gateway, `172.19.0.1`** — that is the
address Auto-detect will report for such tunnels.

## Certificates — DNS-01 (`scripts/domain.sh dns01`)

**Certificates via DNS-01 → Enable** writes `nginx/letsencrypt/cloudflare.ini` (root-only, 0600,
the panel's token read through `manage.py cloudflare_token`; never in `backups/`) and runs
`certbot reconfigure --authenticator dns-cloudflare` for the live certificate (a dry run proves
it). The certbot container is `certbot/dns-cloudflare`. Renewal then never needs port 80, so it
works in all three modes; the domain wizard issues new certificates with DNS-01 too. Saving a new
token re-writes the credentials.

## Integrations in each mode

| | Direct | Cloudflare proxy | Iran tunnel |
|---|---|---|---|
| Telegram bots | long polling, outbound — unaffected | same | same |
| Mini App / site | ✓ | ✓ | ✓ (same domain + our certificate end to end) |
| PasarGuard API | outbound from this server — unaffected | same | same |
| SMS app / iPhone Shortcut (`/api/v1/payments/sms/…`) | ✓ | ⚠ Cloudflare *Bot Fight Mode* / WAF challenges can block non-browser POSTs → add a WAF skip rule for `/api/v1/payments/sms/` | ✓ |
| WebSockets (`/ws/`) | ✓ | ✓ (Cloudflare closes idle ones after ~100 s; the SPAs reconnect) | ✓ for TCP tunnels; an HTTP-level tunnel must pass `Upgrade` |
| Uploads (≤ 15 MB) | ✓ | ✓ (Cloudflare free: 100 MB, 100 s) | ✓; GRE / GRE6: set MTU / MSS clamping or large uploads stall |
| Certificates | DNS-01 (or HTTP-01) | DNS-01 (HTTP-01 also passes through) | DNS-01 (HTTP-01 only if port 80 is tunnelled) |
| Per-IP limits | per IP | per real IP (Cloudflare header) | per client / session (per IP with PROXY protocol) |
| Iranian SNI filtering of the domain | applies | applies (Cloudflare does not hide the SNI) | applies on the Iranian side too — a tunnel changes the route, not the SNI |

## Diagnosis — "Not secure" + 403 through the Iran IP (2026-10-24)

* This server never saw those requests: no request from `185.124.174.13` and **no 403 at all** in
  72 h of nginx logs; nginx has no allow/deny or rate limits, fail2ban only `sshd` / `3x-ipl`, the
  firewall does not filter 80/443. From here `https://caspintunel.com` via `185.124.174.13:443`
  answers **200 with our certificate** (tunnel works); `185.124.174.13:80` does not answer.
* So the 403 + invalid certificate came from **in front of** this server. Likely causes, in order:
  1. **SNI / HTTP filtering inside Iran** for the domain (an invalid certificate + 403 page is the
     classic look of the filter);
  2. the browser didn't go to the Iran IP (ISP DNS cache, or `@` and `www` pointing at different
     servers — at the time `www` → `185.124.174.13`, `@` → this server);
  3. something else listening on the Iran server's 443 (panel, web server, the tunnel's own TLS
     listener) — compare the certificate fingerprint;
  4. tunnel ports crossed (Iran 443 → our 80 / 80 → our 443 shows up here as `400`).

Commands on the **Iran server**:

```bash
ss -ltnp '( sport = :443 or sport = :80 )'                                   # who listens on 443 / 80
echo | openssl s_client -connect 127.0.0.1:443 -servername caspintunel.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -fingerprint -sha256                # must be OUR certificate
curl -s -o /dev/null -D - --resolve caspintunel.com:443:127.0.0.1 \
  https://caspintunel.com/api/v1/health/ | grep -iE '^HTTP|x-caspin-instance' # 200 + X-Caspin-Instance = reached us
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' -H 'Host: caspintunel.com' http://127.0.0.1/   # port 80 tunnel
iptables -S | grep -E 'dport (80|443)'; nft list ruleset 2>/dev/null | grep -E 'dport (80|443)'
```

On **this server**, our fingerprint: `openssl x509 -in nginx/letsencrypt/live/caspintunel.com/fullchain.pem -noout -fingerprint -sha256`.

From a **client inside Iran** (laptop on mobile data):

```bash
nslookup caspintunel.com            # 10.10.34.x = the filter's answer; else should be the Iran IP
curl -sv --resolve caspintunel.com:443:185.124.174.13 https://caspintunel.com/api/v1/health/ -o /dev/null 2>&1 \
  | grep -E 'subject:|issuer:|HTTP/|x-caspin-instance'
echo | openssl s_client -connect 185.124.174.13:443 -servername caspintunel.com 2>&1 | grep -E 'subject=|issuer='
echo | openssl s_client -connect 185.124.174.13:443 -servername example.com    2>&1 | grep -E 'subject=|issuer='
```

If the `caspintunel.com` SNI fails or shows a foreign certificate while `example.com` reaches the
Iran box, the domain is filtered on the path (no server-side setting fixes that).

## API

`GET domain/` → `access` · `POST domain/access/ {mode, skip_verify?}` · `POST domain/access/back/` ·
`POST domain/access/settings/ {iran_ips?, tunnel_sources?, proxy_protocol?}` · `POST domain/access/detect/` ·
`POST domain/access/dns01/` · public `GET /api/v1/domain-probe/<nonce>/` (only for a panel-made nonce).
Beat: *access mode: host nginx result + Cloudflare ranges (daily)* every 5 min.
Test: `scripts/test-domain.sh` stage 9 (simulated tunnel container, PROXY protocol, real nginx, DNS-01).
