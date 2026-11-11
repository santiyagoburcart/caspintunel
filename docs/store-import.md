# Store import — customers from a reseller's previous bot (v1.56)

Multi-tenant Phase 11 ([multi-tenant.md](multi-tenant.md) §15). Our staff bring a reseller's customers, services, wallet
balances and paid history from the bot they used before into the reseller's store. Code: `backend/apps/tenancy/importers/`.
Supported source today: **Mirza-family bots** (PHP + MySQL, `marzban_panel` table). A new source = one adapter file.

**Who:** our staff only (`agency.manage`), on «فروشگاه» → «ورود داده از ربات قبلی». A store's own panel never sees it.
On a store's domain the API path is blocked.

## What happens, step by step

1. **Upload** a `.zip` (one `.sql` inside), `.sql.gz` or `.sql`, max 15 MB (= nginx's request limit; zip a bigger dump).
   - The file must look like a MySQL dump. It is stored under `media/imports/<store>/<random>.sql`: the folder is 0700, the
     file 0600, and nginx answers 404 for `/media/imports/`.
   - The file is deleted once the import has finished, or 24 h after upload (hourly beat «store: import cleanup»).
   - **Nothing in the file is ever executed.** `importers/dump.py` reads `CREATE TABLE` / `INSERT INTO` as text.
2. **Scan** (Celery `scan_import_task`, inside the store). This step is read-only.
   - The adapter is picked by the tables present.
   - **One** paged listing of PasarGuard users (`GET /api/users`) is made, plus a check of which accounts are already linked
     in any store (one store at a time, no `unscoped()`).
   - The result is a **preview**: counts, masked samples, the plan map to choose and the store's sign-up rules. There is also
     a **report** with one row per service and customer and its outcome.
3. **Start**:
   - The page needs **«ربات قبلی فروش را متوقف کرده است»** ticked (also checked on the server, `old_bot_stopped`).
   - Each product of the old bot gets a plan of this store, or «بدون پلن». The matching plan (same GB and days) is
     pre-selected.
   - Each balance above 1,000,000 T must be confirmed separately.
   - Credit validity is 7–365 days (default 180).
4. **Run** (Celery `run_import_task`, inside the store):
   - The regular DB backup (`telegram.backup.run_database_backup`) runs first. If it fails, nothing is written.
   - Then the import runs: customers → services → referrals → credits → history. Ownership is re-checked live on PasarGuard
     first.
   - One summary alert goes to our staff (`platform=True`, silent). **No customer is messaged.**
5. **Report** (CSV, UTF-8 + BOM):
   - Every service row: outcome, bot status, whether it was live in the bot, PasarGuard status and owner, product, GB, days,
     sale date, customer.
   - Every customer row.
   - Missing / other-admin / failed services come first, so the reseller can check them.
6. **Undo** («بازگردانی»):
   - Removes what this import created **and nothing used since**. A customer with a new order, service or ticket is kept. So
     is a credit that was used or is held by an order, and a service with a newer order.
   - The kept items are listed.
   - PasarGuard is never touched in either direction.

## Mapping (Mirza)

| Mirza | Our model | Rule |
|---|---|---|
| `user.id` (Telegram id), `username`, `lang` | `accounts.User` (`source=bot`, random username + random password) | Matched by Telegram id **inside the store**: an existing customer is reused (never two accounts). |
| `user.number` | `User.phone` | Only when it is a valid Iranian mobile not used by another customer of the store. The word "none" = no phone. |
| `user.User_Status = block` | `User.is_active = False` | Noted in `admin_note`. |
| `user.affiliates` (referrer's Telegram id) | `User.referred_by` | Only when both are in the file and the customer has no referrer yet. |
| `user.Balance` | `crm.DiscountCode` kind **`credit`** | One customer, one use, fixed amount, valid N days. Above 1,000,000 T only when confirmed. |
| `invoice` (status active / send_on_hold / disabled / disabledn, > 1 day) | `panel.Service` + `imported` Order (0 T, `source=import`) via `panel.services.link_existing_service(owner_must_be=<reseller>)` | Only when the PasarGuard account exists and **its owner is the store's reseller** (case-insensitive). Usage, limit, expiry, on-hold and WireGuard peers come from PasarGuard. |
| `invoice` with `Service_time` ≤ 1 | — | The old bot's free test: skipped. |
| `invoice` unpaid / Unsuccessful / removebyuser | — | Never delivered: skipped. |
| `invoice.name_product` | `Service.current_plan` | Through the plan map chosen on the page (none = the customer picks a plan when renewing). |
| `Payment_report` with `payment_Status = paid` | `tenancy.ImportRecord` kind `history` | Read-only note on Customer 360 («ربات قبلی»). **Never** a `Payment` row and never revenue. The purpose comes from `id_invoice` («getconfigafterpay» = buy, «getextenduser» = renew, «0» = wallet). |
| `product` | (the page) | Grouped by product name for the plan map. Plans are never created by an import. |
| `marzban_panel` | (the page) | Only the panel name and type. URLs and credentials are never read. |

Everything else in the dump (cards, tokens, settings, texts, gift codes) is ignored.

## Service outcomes

`link` / `linked` · `test` · `not_sold` · `missing` (with «live in the bot» flag) · `other_admin` (never linked) ·
`linked_elsewhere` (already a service in any store) · `no_customer` · `duplicate` (an older row of the same account) ·
`already` (an earlier import of this store) · `failed` (PasarGuard refused while linking).

## The store's own sign-up rules

Imported customers are ordinary Telegram customers of the store:

- **Phone required** (`force_share_phone`, the reseller's setting): the bot / Mini App gate asks a customer without a phone
  for it on first contact. `handle_contact` saves it on the SAME imported account (status `phone_saved`).
- **Phone not required**: they come straight in.
- Iranian-number-only and channel join work as for any customer.
- The preview shows which rules the store has.

## What customers see

On their next /start in the store's bot (or the Mini App):

- their linked services, with live usage, expiry, WireGuard configs and renew;
- the store's plans;
- **«💳 استفاده از اعتبار …»** in the bot's discount step, and a credit chip at checkout (`GET /api/v1/orders/credits/`) —
  they never need to know the code.

A credit that covers the whole price still leaves the small unique amount to pay (same as any 100 % code).

## Idempotency

`ImportRecord` (`tenant`, `kind`, `source_key`) is unique. Running the same or a newer dump again only adds what is new.

## Adding a source

Write `importers/<name>.py` with `NAME`, `LABEL`, `detect(tables)` and `parse(tables) → importers.source.Source`, then register
it in `importers/__init__.py`. Test it with a synthetic dump. Never put a real customer dump in the repo or the tests.
