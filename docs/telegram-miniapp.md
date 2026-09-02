# Telegram Mini App

The Mini App **is the existing React user site**, opened inside Telegram. No
separate build, no separate API — the same SPA at `frontend/user/` and the same
`/api/v1/` endpoints. Telegram just launches `https://<domain>/` in its WebView
and the SPA notices it's running in Telegram, verifies the launch server-side,
and logs the person in.

## How a session starts (the security-critical path)

```
Telegram  ──(opens https://aicaspin.ir/ with a signed initData string)──►  SPA
   SPA    ──POST /api/v1/auth/telegram/miniapp/ { init_data }────────────►  backend
 backend  ── validate initData HMAC against the SALES BOT TOKEN ──────────►  reject on any failure (401)
 backend  ── link/create the site User by telegram_id (source=bot) ──────►
 backend  ── issue a normal SimpleJWT pair ─────────────────────────────►  SPA stores it, runs as a normal user
```

### 1. initData validation — `apps/accounts/telegram_auth.py :: validate_init_data`

Telegram's documented algorithm
(https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):

```python
fields = dict(parse_qsl(raw, keep_blank_values=True))   # url-decode each value once
received_hash = fields.pop("hash", "")
fields.pop("signature", None)                            # Ed25519 3rd-party check only — not in the HMAC
if not received_hash: reject("missing hash")

data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)          # note: key is the literal "WebAppData"
computed   = HMAC_SHA256(key=secret_key, msg=data_check_string).hexdigest()
if not hmac.compare_digest(computed, received_hash): reject("signature mismatch")   # constant-time

if now - int(fields["auth_date"]) > MINIAPP_INITDATA_MAX_AGE: reject("expired")     # default 3600 s
user = json.loads(fields["user"])
if not user.get("id"): reject("no Telegram user")
```

The bot token comes from `TelegramConfig(bot_type="sales").token` (Fernet-decrypted
by the field). It is read only on the server and **never sent to the frontend**.
If no sales bot token is configured the endpoint returns **503** and the Mini App
shows a "not configured" message.

### 2. Session / JWT issuance — `apps/accounts/views.py :: TelegramMiniAppLoginView`

Only after validation succeeds:

```python
user, created, _pw = ensure_bot_user(int(tg["id"]),
                                     telegram_username=tg.get("username"),
                                     name="<first last>")
# ensure_bot_user: existing telegram_id -> that user; otherwise create_user(
#   username="tg_<8hex>", random password, source=bot)  — identical to the
#   first-time bot-user flow, and race-safe (IntegrityError -> adopt the row).
if not user.is_active: return 403
user.last_login = now()
refresh = RefreshToken.for_user(user)      # ordinary SimpleJWT customer token
return { user, access, refresh, created }
```

The returned pair is an **ordinary customer JWT**. Inside the Mini App every
request goes through the same `api` client, the same `Authorization: Bearer`
header, the same DRF auth/permission/throttle classes, the same ownership checks
(orders, services, the auth-gated `/payments/<id>/receipt/` endpoint). A Mini App
session has **exactly** a logged-in customer's permissions — it cannot reach
`/api/v1/admin/…` (verified in `test_miniapp_session_has_no_admin_access`).

Rate limit: the endpoint is on the `auth` throttle scope (10/min per IP).

### 3. Frontend — `frontend/user/`

- `index.html` loads `https://telegram.org/js/telegram-web-app.js` (allowed by
  the user-site CSP only).
- `src/lib/telegram.js` — `isTelegramMiniApp()` (true only when `WebApp.initData`
  is a non-empty string), `initTelegramUi()` (`ready()` + `expand()` + header/bg
  colour = the site's `--c-bg`), `tgStartParam()`.
- `src/lib/auth.jsx` — on launch, if `isTelegramMiniApp()`, POST `initData` to the
  endpoint and store the JWT. **On failure it does NOT fall back to a stored
  token** — it clears tokens and shows a retry screen. initData is re-verified on
  every launch (it's freshly signed by Telegram each time).
- Everything else is the unchanged site. `?startapp=store|history|help|profile`
  deep-links to that route after login. The logout button is hidden in Telegram
  (identity == the Telegram account).

## The Mini App URL

```
https://aicaspin.ir/
```

Just the user site root over HTTPS (Telegram requires HTTPS). Configurable with
`MINIAPP_URL` in `.env` (defaults to `PUBLIC_BASE_URL`).

## Wiring the bot's "Open App" button

### Menu button (the button next to the message input) — automatic

Every time the **sales bot** starts (`run_sales_bot`), `build_bot()` calls
`_sync_menu_button()` → `setChatMenuButton` with a `web_app` button pointing at
`MINIAPP_URL`. Nothing to do once the sales bot token is set in the panel.

Manual trigger / re-point:

```bash
docker compose exec web python manage.py set_bot_menu
docker compose exec web python manage.py set_bot_menu --url https://aicaspin.ir/ --text "کاسپین"
```

### Inline button in `/start` and the main menu

`keyboards.main_menu()` adds `🌐 باز کردن اپ` as an inline `web_app` button when
`MINIAPP_URL` is https — it shows under the buy / my-services / support buttons.

### Manual alternatives (no code)

- **@BotFather** → `/mybots` → your bot → *Bot Settings* → *Menu Button* →
  *Configure menu button* → send `https://aicaspin.ir/` and a label.
- **Direct link / named app**: @BotFather → `/newapp` → pick the bot → set the
  Web App URL `https://aicaspin.ir/` → you get a `t.me/<bot>/<appname>` link and
  can use `?startapp=store` deep links.
- **Bot API**:
  ```bash
  curl -sX POST "https://api.telegram.org/bot<TOKEN>/setChatMenuButton" \
    -d 'menu_button={"type":"web_app","text":"کاسپین","web_app":{"url":"https://aicaspin.ir/"}}'
  ```

## CSP note

`nginx/prod.conf` (and the dev conf) now serve **two** CSPs via a `map`:

| path | `script-src` | `frame-ancestors` |
|---|---|---|
| `/` (user site / Mini App) | `'self' https://telegram.org` | `'self' https://telegram.org https://*.telegram.org` |
| `/panel/`, `/api/`, `/admin/` | `'self'` | `'none'` |

Only the user site can load the Telegram SDK and be framed by Telegram (needed
for Telegram Desktop / Web, which embed the Mini App in an iframe; mobile
Telegram uses a native WebView and isn't affected). The admin panel and API stay
locked to `frame-ancestors 'none'`; Django additionally sends its own
`X-Frame-Options: DENY` on `/api/` and `/admin/`.
