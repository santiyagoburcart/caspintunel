# WireGuard configs (v1.55)

## How PasarGuard 5.6 does it (researched read-only on 2026-11-11)

- WireGuard runs on **separate cores of type `wg`** — one per location, each with one interface = one inbound tag
  (today: `WG_7600` Italy, `WG_3434` Türkiye, `WG_3535` Germany, `WG_24300` Netherlands, `WG-ir_9210` Iran).
- A user gets WireGuard by being in a **group** whose inbounds are WireGuard interfaces (today «wirgard», id 10, all five).
- PasarGuard gives every user one key pair and **one peer IP per WireGuard interface** it can use
  (`proxy_settings.wireguard.peer_ips`); users without a WireGuard group have no peer IPs.
- Each WireGuard inbound has a host (remark `Ita {USERNAME}`, `tu …`, `de …`, `nl …`, `IR …`, address `wir.caspin.skin`).
- There is **no per-location endpoint**: `GET /api/user/{id}/subscription/wireguard` returns ONE zip with one `.conf` per
  host (`_Ita_<user>.conf`, `de_<user>.conf` …). Each `.conf` is complete (private key, address, DNS, server key, endpoint, PSK).

## What we do (`apps/panel/wireguard.py`)

- **Access**: `Service.wireguard` = the PasarGuard user has peer IPs — mirrored by every sync (`mappers.apply_user_to_service`).
  Any such service shows «وایرگارد», whatever plan it came from; others show nothing.
- **Files**: fetched from PasarGuard on every request and split per location — **never stored**. The location's name and flag
  come from **«مکان‌های وایرگارد»** (Plans page, our staff; `WireguardLocation`, matched by the remark code, case-insensitive);
  an unknown code shows as itself. File names: `<store initials>-<service id>-<slug>.conf` (e.g. `CT-12-germany.conf`),
  «دانلود همه» = `CT-12-wireguard.zip` with those names.
- **Where**: site (service card → «وایرگارد» → one «دانلود» per location + «دانلود همه»), Mini App (the bot sends the file to
  the user's chat — WebView downloads are unreliable), bot (service → «🔐 وایرگارد» → a location → the `.conf` as a document,
  «همه (zip)»). Stores get the same in their site and bot (their own initials in the file name).
- **Security**: only the service owner (`/api/v1/services/<id>/wireguard/…` is scoped to the signed-in customer), 60 / hour per
  account (`wireguard` throttle) and 30 / hour per Telegram user in the bot, every download audit-logged
  (`service.wireguard_download`, via site / miniapp / bot). Keys are always PasarGuard's current ones (fetched each time), so
  renewals and resets keep working.
- **Plans**: `Plan.vpn_type` = «ساب (V2Ray)» (default; existing plans) · «فقط وایرگارد» · «هر دو». The admin form checks the type
  against the chosen groups: a **WireGuard group = a group whose inbounds are all WireGuard interfaces** (`group_kinds`, from
  `/api/cores` type `wg` + `/api/groups`). Per-location groups created later on PasarGuard («wg-de» …) are therefore picked up
  by plans with no code change. «فقط وایرگارد» hides the subscription link everywhere (site, QR, Mini App, bot, delivery
  message: `panel.models.customer_sub_url`). Stores can sell WireGuard plans when their reseller role allows those groups.
