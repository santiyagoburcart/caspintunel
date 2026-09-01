# frontend

Two React + Vite + Tailwind SPAs consuming `/api/v1`.

| App | Path | Auth | Route base |
|-----|------|------|-----------|
| `user/` | `/` | customer JWT (`/auth/`) | `/` |
| `admin/` | `/panel/` | staff JWT (`/admin/auth/`) | `/panel` |

**Design system** (shared): Midnight Aurora palette as CSS variables driven by
`ThemeProvider` (fetches `/api/v1/theme/` — a panel theme change restyles with no
rebuild), dark by default with a toggle, glassmorphism (`.glass`, `.card`),
Vazirmatn, bilingual fa/en with automatic `dir` switch, Jalali dates via
`Intl('fa-IR-u-ca-persian')`, dynamic `<title>`/favicon/logo from
`/api/v1/config/`.

## Dev

`docker compose up` runs both as Vite dev servers behind the main Nginx:
- user → `http://localhost/`  (also `:5173`)
- admin → `http://localhost/panel/`  (also `:5174`)
- API/`/admin/` (Django) proxied to `web:8000`

## Prod

`frontend/*/Dockerfile` builds static bundles served by their own Nginx;
`docker-compose.prod.yml` wires them behind the main Nginx (`nginx/prod.conf`).

## Screens

**user:** login · register · verify-email · reset-password · dashboard (service
cards, usage bars, QR, renew) · store · checkout (order → card + unique amount +
receipt upload + status) · history · profile (password, referral, theme, lang) ·
help (CMS pages)

**admin:** login · dashboard (services / revenue / health / resources) · users
(filter + enable/disable) · plans (CRUD) · payments (approval queue w/ receipt) ·
accounting (Jalali range + daily bar chart + breakdowns) · cards (per-card
deposit report) · monitoring (9 health targets, resource gauges, backups + run) ·
branding · pages · themes (activate) · roles
