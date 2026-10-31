# Data model (ERD)

Every table of the application, grouped by area, as Mermaid ER diagrams (rendered
on GitHub and in the admin Documentation page). Diagrams
list the key columns only; the models in `backend/apps/*/models.py` are the
source of truth. Table names are the real MySQL names.

Conventions: every domain table has `id` (bigint PK); `created_at` / `updated_at`
where noted (`TimeStampedModel`). Money is `DECIMAL` in **tomans**; volumes are
**bytes** (`BIGINT`; 1 GB = 1024³). Times are stored in UTC and shown in Jalali.
Fields marked *enc* are Fernet-encrypted (`FIELD_ENCRYPTION_KEY`).

Related: [architecture.md](architecture.md) · [flows.md](flows.md).

## 1. Users, auth and RBAC (`accounts`, `common`)

```mermaid
erDiagram
    user ||--o{ user : "referred_by"
    staff }o--o| role : "role"
    role }o--o{ permission : "role_permission"
    user ||--o{ deleted_user_archive : "snapshots"
    staff |o--o{ deleted_user_archive : "deleted_by / restored_by"
    staff |o--o{ user : "deleted_by"

    user {
        bigint id PK
        string username UK
        string email
        bool email_verified
        string phone "09xxxxxxxxx, app-level unique"
        bigint telegram_id UK
        string telegram_username
        string referral_code UK
        bigint referred_by_id FK
        string source "site | bot"
        bool is_legacy "imported from the old system"
        string language "fa | en"
        datetime terms_accepted_at
        datetime deleted_at "soft delete"
        datetime purged_at "permanent delete: anonymous placeholder"
        bigint purged_by_id FK "staff"
        bigint deleted_by_id FK
    }
    staff {
        bigint id PK
        string username UK
        string password_hash
        bigint role_id FK
        bool is_superadmin
        int token_version "JWT tv claim"
        string email "ticket notifications"
        string display_name "shown to customers if enabled"
        bigint telegram_id UK "linked via the sales bot"
        datetime telegram_linked_at
    }
    role {
        bigint id PK
        string name UK
        string name_fa "v1.25.2 Persian label"
        string description_fa
    }
    permission {
        bigint id PK
        string code UK "e.g. payment.approve"
        string name_fa "v1.25.2 Persian label"
    }
    staff_revoked_token {
        bigint id PK
        string jti UK
        datetime expires_at
    }
    deleted_user_archive {
        bigint id PK
        bigint user_id FK
        json snapshot
        int orders_count
        decimal total_paid
        bigint deleted_by_id FK
        bigint restored_by_id FK
    }
    audit_log {
        bigint id PK
        bigint staff_id "no FK, survives staff delete"
        string action "e.g. payment.sms_auto_confirmed"
        string target_type
        bigint target_id
        json detail
        string ip
    }
```

| Table | Description |
|---|---|
| `user` | Customer account (site, bot or legacy import). Soft-deleted first; excluded from lists, stats and renewals once `deleted_at` is set. A Super Admin can then permanently delete it (v1.31.2, `accounts/purge.py`): the row stays as «کاربر حذف‌شده #id» (no name / phone / email / Telegram / card / notes, unusable password, `purged_at`) so orders and payments — and every total — are unchanged; services, tickets, CRM rows, notifications, tokens and its `deleted_user_archive` rows are deleted. |
| `staff` | Admin-panel operator — a separate model from `user`, with its own JWT; `token_version` ends all sessions when bumped. Optional `email` and linked `telegram_id` receive ticket notifications. |
| `role` / `permission` / `role_permission` | RBAC: roles bundle permission codes (`users.view`, `payment.approve`, `agency.view`, `agency.accounting`, `settings.email`, …). Super-admins bypass checks. `name_fa` / `description_fa` (v1.25.2) are shown when the panel is Persian (seeded for built-in roles and every permission). |
| `staff_revoked_token` | Spent / revoked staff refresh tokens (by `jti`) until they expire. |
| `deleted_user_archive` | Full snapshot of a user taken right before a soft delete; restore writes `restored_at/_by`. |
| `audit_log` | Immutable record of staff and system actions (`write_audit`). `staff_id` is a plain column, not an FK. |

## 2. Plans and services (`plans`, `panel`)

```mermaid
erDiagram
    panel ||--o{ plan : "sold on"
    panel ||--o{ service : "hosts"
    user ||--o{ service : "owns"
    plan |o--o{ service : "current_plan"

    panel {
        bigint id PK
        string name
        string base_url
        string admin_username
        text admin_password_enc "enc"
        text token_cache "enc"
        json default_group_ids
        string subscription_base_url
        bool is_active
    }
    plan {
        bigint id PK
        string name_fa
        string name_en
        bigint panel_id FK
        string type "fixed | custom_volume"
        bigint data_limit "bytes, 0 = unlimited"
        int duration_days
        int device_limit
        decimal price
        decimal discount_percent
        string renewal_mode "reset | carry_over"
        string carry_over_data "both | volume_only | time_only"
        json group_ids
        int min_gb
        int max_gb
        decimal price_per_gb
        bool is_active
    }
    service {
        bigint id PK
        bigint user_id FK
        bigint panel_id FK
        string panel_username
        string subscription_url
        string status "pending | on_hold | active | limited | expired | disabled"
        bigint data_limit
        bigint data_used
        datetime expire_at
        int on_hold_duration
        int device_limit "HWID limit"
        bigint current_plan_id FK
        string source "how it was created, e.g. import = linked existing account"
        bool alert_vol_sent
        bool alert_exp_sent
    }
```

| Table | Description |
|---|---|
| `panel` | A PasarGuard panel we provision on (multi-panel); credentials and the cached API token encrypted. |
| `plan` | A sales plan: fixed (volume + days) or custom-volume (GB range × price per GB); panel groups; renewal behaviour copied into each scheduled renewal. |
| `service` | One VPN account = one username on a panel; mirrors the panel after every operation; synced periodically (usage, expiry, online). Alert flags stop repeated warnings. |

## 3. Orders, payments and SMS (`orders`, `payments_sms`)

```mermaid
erDiagram
    user ||--o{ order : "places"
    plan |o--o{ order : "for"
    service |o--o{ order : "renews / tops up"
    order ||--o| payment : "paid by"
    bank_card |o--o{ payment : "into"
    sms_message |o--o{ payment : "evidence"
    blu_transaction |o--o{ payment : "evidence"
    order |o--o{ blu_transaction : "matched_order"
    staff |o--o{ payment : "confirmed_by_staff"
    sms_source |o--o{ sms_message : "sender"
    sms_app_device |o--o{ sms_message : "forwarded by"
    order |o--o{ sms_message : "matched_order"
    order |o--o{ sms_message : "mismatch_order"
    service ||--o| scheduled_renewal : "pending renewal"
    plan ||--o{ scheduled_renewal : "plan"
    order ||--o{ scheduled_renewal : "paid by"

    order {
        bigint id PK
        bigint user_id FK
        bigint service_id FK
        bigint plan_id FK
        string type "new | renew | addon_volume | manual | imported"
        int custom_volume_gb
        decimal amount "plan price"
        decimal amount_unique "amount + 200..1500 T surcharge"
        decimal amount_unique_lock UK "set while pending/paid"
        datetime unique_expire_at "reservation, 30 min"
        string status "pending_payment | paid | completed | rejected | failed | expired | cancelled"
        string source "site | bot | admin"
    }
    payment {
        bigint id PK
        bigint order_id FK "one per order"
        bigint bank_card_id FK
        string method "card_manual | sms_auto | sms_mismatch | blu_auto | blu_mismatch | gateway"
        decimal amount
        string status "pending | approved | rejected"
        string receipt_image "private media"
        string receipt_sha256 "image hash (duplicate check)"
        string receipt_ref "bank document / tracking no., digits"
        decimal receipt_amount "amount on the receipt, tomans (staff)"
        bigint sms_message_id FK
        bigint blu_transaction_id FK
        string confirmed_by "admin | system"
        bigint confirmed_by_staff_id FK
        string reject_reason
        int number UK "TX-000123 (= id, backfilled)"
        datetime voided_at "Super Admin delete (void); null = live"
        bigint voided_by_id FK "staff"
        string void_reason
        string void_service_action "keep | disable | delete"
        string void_prev_order_status "put back by restore"
    }
    bank_card {
        bigint id PK
        string card_number
        string holder_name
        string bank_name
        int sort_order
        bool is_active
    }
    sms_source {
        bigint id PK
        string phone_number "bank sender (number or name)"
        string amount_unit "rial | toman (default for unit-less SMS)"
        bool is_active
    }
    sms_app_device {
        bigint id PK
        string name
        string api_token UK "X-Device-Token"
        datetime last_seen_at
    }
    sms_message {
        bigint id PK
        bigint sms_source_id FK
        bigint device_id FK
        text raw_text
        string sender
        decimal parsed_amount "tomans"
        bigint parsed_raw
        string parsed_unit
        bigint matched_order_id FK
        bigint mismatch_order_id FK
        string mismatch_kind "less | more"
        string note "why matched / not matched"
    }
    blu_transaction {
        bigint id PK
        string bank_id UK "collector item id (idempotency)"
        bigint amount_irr
        decimal amount_toman "null unless amount_irr % 10 == 0"
        datetime occurred_at "bank timestamp (UTC)"
        string direction "بستانکار = deposit"
        string payer_name
        string payer_card "masked first6******last4"
        string payer_last4
        string receipt "tracking no."
        string reference "reference no."
        string account_iban
        bigint balance_after_irr
        json raw "item, card numbers masked"
        string status "unmatched | matched | duplicate | ignored"
        bigint matched_order_id FK
        bigint matched_payment_id FK
        string match_note
    }
    blu_collector {
        bigint id PK "single row"
        datetime last_batch_at
        string last_batch_id
        int last_items
        int batches
        datetime stale_alerted_at
        string svc_state "systemctl is-active (SSH check)"
        datetime svc_checked_at
        string svc_error_line "last journal error, masked"
        int svc_error_count "error lines in 10 min"
        int ssh_failures "in a row"
        string ssh_error
        string svc_alert "'' | inactive | ssh | errors"
    }
    scheduled_renewal {
        bigint id PK
        bigint service_id FK "one per service"
        bigint plan_id FK
        bigint order_id FK
        string renewal_mode
        string carry_over_data
        datetime applied_at
    }
```

| Table | Description |
|---|---|
| `order` | Purchase intent. `amount_unique` = price + a random surcharge, reserved via the unique `amount_unique_lock` while pending/paid (never a value the same user had in the last 24 h). Expires after `unique_amount_reservation_minutes`. |
| `payment` | One per order: receipt (card-to-card), SMS / Blu auto-confirm, or an SMS / Blu near-miss under review. Approved / rejected only through `approve_payment` / `reject_payment`. `number` = human transaction number `TX-000123` (v1.25). A Super Admin "delete" voids it (`voided_*`, `payments_sms/voiding.py`): out of every list and total, restorable for 30 days; never a hard delete. |
| `bank_card` | Receiving cards shown at checkout; per-card deposit report in Accounting. |
| `sms_source` | Allow-list of bank senders and the default amount unit for unit-less SMS. |
| `sms_app_device` | Operator phones (Android app / iPhone Shortcut) allowed to forward bank SMS. |
| `sms_message` | Every forwarded SMS with the parsed amount, the matched order or the near-miss order (`less` / `more`), and a human-readable note (admin SMS log). |
| `blu_transaction` | One Blu Bank account row pushed by the Iran-side collector (v1.31). `bank_id` unique = retries are no-ops. Debits are stored as `ignored`. A deposit auto-confirms only an order whose unique amount equals it exactly and whose time window contains it (`matched`); an order already paid by SMS → `duplicate`; a near amount stays `unmatched` linked to the order (`blu_mismatch` payment for review). Card numbers are stored masked. |
| `blu_collector` | One row: the collector's last signed batch (an empty batch = heartbeat) and whether the offline alert went out; since v1.31.1 also the SSH service check (state, last check, last error line, SSH failures, current alert). |
| `scheduled_renewal` | A paid renewal waiting for the service to reach the end of its cycle; applied once (`applied_at`). One per service; an unapplied one is never replaced (a second paid renewal → order `failed` + staff alert). |

## 4. Agency panel (`agency`)

PAMP v1.5.3 tables (verbatim columns, renamed to `agency_*`) plus the
caspintunel additions: reseller sessions, prices and the ledger. Resellers are
**not** `user` rows — they are linked by the panel `username`.

```mermaid
erDiagram
    agency_panel_admin ||--o| agency_admin_limit : "limit config"
    agency_panel_admin ||--o{ agency_user_traffic_snapshot : "last-known users"
    agency_panel_admin ||..o{ agency_admin_group : "owner / members (by username)"
    agency_panel_admin ||..o{ agency_reseller_session : "portal logins (by username)"
    agency_panel_admin ||..o{ agency_admin_price : "price per GB (by username)"
    agency_panel_admin ||..o{ agency_ledger_entry : "account lines (by username)"
    agency_panel_admin ||..o{ agency_limit_change : "limit history (by username)"
    agency_ledger_entry |o--o{ agency_limit_change : "charge of a change"
    agency_group_manager ||--o{ agency_group_manager_group : "runs"
    agency_admin_group ||--o{ agency_group_manager_group : "managed by"
    agency_group_manager ||--o{ agency_manager_session : "legacy portal logins (unused since v1.25)"
    agency_group_manager |o--o| staff : "signs in to /panel/ as (role Group manager)"
    agency_group_manager |o--o{ agency_volume_request : "gave volume"
    agency_admin_group |o--o{ agency_volume_request : "for an admin of"
    agency_volume_request |o--o| agency_ledger_entry : "charge when approved"
    agency_volume_request |o--o| agency_limit_change : "the change it approves"

    agency_panel_admin {
        bigint id PK
        string username UK "PasarGuard admin"
        bool is_sudo
        string status
        bool has_data_limit
        bigint admin_limit_bytes
        bigint admin_remaining
        bigint total_user_limit "Total Sold"
        bigint total_user_used
        int user_count
        int active_user_count
        bool pamp_blocked "disabled by enforcement"
        bigint deleted_users_used_bytes
        datetime deleted_traffic_reset_at
        datetime last_synced_at
        json raw_data
    }
    agency_admin_limit {
        bigint id PK
        bigint panel_admin_id FK
        bigint limit_bytes
        bool warning_sent_80
        string support_telegram
    }
    agency_user_traffic_snapshot {
        bigint id PK
        bigint panel_admin_id FK
        string user_username
        bigint used_traffic_bytes
        datetime last_seen
    }
    agency_sync_log {
        bigint id PK
        string status "success | partial | failed"
        int admins_synced
        text error_message
        float duration_seconds
    }
    agency_admin_group {
        bigint id PK
        string name
        string owner_username
        text member_usernames
        string note
    }
    agency_reseller_session {
        bigint id PK
        string username
        string key_hash "SHA-256 only"
        datetime expires_at "10 days"
        bool revoked
    }
    agency_admin_price {
        bigint id PK
        string admin_username
        decimal price_per_gb "tomans"
        date valid_from
    }
    agency_ledger_entry {
        bigint id PK
        string admin_username
        string kind "quota_charge | manual_charge | adjustment | payment"
        decimal amount
        date date
        decimal gb
        decimal price_per_gb
        bigint old_limit_bytes
        bigint new_limit_bytes
        string method
        bool voided
    }

    agency_limit_change {
        bigint id PK
        string admin_username
        bigint old_limit_bytes "0 = unlimited, null = unknown"
        bigint new_limit_bytes
        string action "create | set | add | reduce | remove | external | baseline"
        string source "panel | pasarguard | history | manager"
        string staff
        bigint ledger_entry_id FK
        datetime created_at
    }

    agency_group_manager {
        bigint id PK
        string username UK "= its staff username"
        string password "Django hash (legacy; the staff hash is used)"
        bigint staff_id FK "v1.25: the /panel/ staff account"
        bool is_active
        decimal max_unapproved_gb "null = no cap"
        datetime last_login_at
    }

    agency_group_manager_group {
        bigint id PK
        bigint manager_id FK
        bigint group_id FK
        json allowed_role_ids "PasarGuard roles = inbound sets (never owner)"
    }

    agency_manager_session {
        bigint id PK
        bigint manager_id FK
        string key_hash UK "sha256 of the bearer token"
        datetime expires_at
        bool revoked
    }

    agency_volume_request {
        bigint id PK
        bigint group_id FK
        bigint manager_id FK
        string admin_username
        string kind "create | add"
        decimal gb
        bigint old_limit_bytes
        bigint new_limit_bytes
        string status "pending | approved | rejected"
        string decided_by
        bigint ledger_entry_id FK
        bigint limit_change_id FK
    }
```

| Table | Description |
|---|---|
| `agency_panel_admin` | One PasarGuard admin (reseller) with the PAMP counters refreshed by every sync: limit, used, sold, remaining, user counts, deleted-users traffic, blocked flag. |
| `agency_admin_limit` | Per-admin limit settings and the 80 % warning flag (PAMP). |
| `agency_user_traffic_snapshot` | Last-known `used_traffic` per user of each admin — a user missing on the next sync counts as deleted and their traffic is kept in `deleted_users_used_bytes`. |
| `agency_sync_log` | One row per sync run (Sync logs page). |
| `agency_admin_group` | Several admin accounts under one owner (combined numbers, portal group view). |
| `agency_reseller_session` | Reseller-portal logins (password checked against the panel); hashed token, revocable. |
| `agency_admin_price` | Price per GB for an admin from a date on. |
| `agency_group_manager` | A group manager (caspintunel): active flag, optional cap on unapproved GB, groups. Since v1.25 it signs in to `/panel/` as the linked `staff` row (role *Group manager*); that link restricts the staff to its own groups on every admin API. |
| `agency_group_manager_group` | Which agency groups a manager runs, and the PasarGuard roles (= inbound sets) it may give per group. |
| `agency_manager_session` | Legacy group-manager portal logins (before v1.25); no longer accepted, kept for one release (drop next). |
| `agency_volume_request` | "Pending approval": volume a manager gave (new admin / +GB), already live on PasarGuard; approve → quota charge, reject → volume taken back. |
| `agency_ledger_entry` | The reseller's account: automatic quota charges on limit increases, manual charges, signed adjustments, payments; voidable, never deleted. Balance = charges − payments. |

## 5. Tickets (`tickets`)

```mermaid
erDiagram
    user ||--o{ ticket : "opens"
    ticket_topic ||--o{ ticket : "topic"
    staff |o--o{ ticket : "assigned_to / closed_by"
    service |o--o{ ticket : "related service"
    order |o--o{ ticket : "related order"
    ticket ||--o{ ticket_message : "conversation"
    ticket_message ||--o{ ticket_attachment : "files"
    ticket ||--o{ ticket_event : "history"
    staff }o--o{ ticket_topic : "ticket_staff_topic (scope)"
    ticket_topic |o--o{ ticket_canned_reply : "saved replies (null = all topics)"
    user |o--o{ ticket_message : "author_user"
    staff |o--o{ ticket_message : "author_staff"

    ticket_topic {
        bigint id PK
        string name_fa
        string name_en
        string description_fa
        string description_en
        bool requires_active_service "true = anyone who ever had a service, false = pre-purchase (everyone)"
        bool is_active
        int sort_order
    }
    ticket {
        bigint id PK
        string number UK "100000 + id"
        bigint user_id FK
        bigint topic_id FK
        string subject
        string status "open | awaiting_admin | awaiting_user | on_hold | closed"
        string priority "low | normal | high | urgent"
        bigint assigned_to_id FK
        bigint service_id FK
        bigint order_id FK
        string source "site | bot"
        datetime first_response_at
        datetime last_activity_at
        datetime status_changed_at "auto-close clock"
        bigint closed_by_id FK
        string closed_by_kind "user | staff | system"
        datetime closed_at
    }
    ticket_message {
        bigint id PK
        bigint ticket_id FK
        bigint author_user_id FK
        bigint author_staff_id FK
        text body
        bool is_internal "staff-only note"
        string channel "site | bot | panel"
        datetime read_by_user_at
        datetime read_by_staff_at
    }
    ticket_attachment {
        bigint id PK
        bigint message_id FK
        string file "media/tickets/, random name, private"
        string original_name
        string content_type "image/* or application/pdf"
        int size
    }
    ticket_canned_reply {
        bigint id PK
        string title
        text body
        bigint topic_id FK
        bool is_active
        int sort_order
        string created_by
    }
    ticket_event {
        bigint id PK
        bigint ticket_id FK
        string kind "created | user_replied | staff_replied | internal_note | assigned | status | priority | closed | reopened | auto_closed"
        bigint actor_user_id FK
        bigint actor_staff_id FK
        string actor_label "kept if the actor is deleted"
        string old_value
        string new_value
        bigint message_id FK
    }
```

| Table | Description |
|---|---|
| `ticket_topic` | Ticket categories, editable in the panel. Seeded once (migration): Pre-purchase questions (open to everyone), Payment problem, Connection problem, Renewal & upgrade, Other (customers = anyone who ever had a service). |
| `ticket_canned_reply` | Saved replies for the staff composer, per topic or for all topics. |
| `ticket_staff_topic` | Staff topic scopes: a staff member with rows here sees only those topics; none = all. |
| `ticket` | One support conversation of a customer, with status, priority, owner (assignee), optional related service / order, first-response and activity times, and who closed it. |
| `ticket_message` | A message from the customer or staff (or a staff-only internal note), with per-side read times. |
| `ticket_attachment` | Validated image / PDF files of a message; served only through the API. |
| `ticket_event` | Full history: every reply, assignment, status / priority change, close and reopen with the actor and old → new value. |

## 6. CRM (`crm`)

```mermaid
erDiagram
    user ||--o| crm_customer_profile : "stage, owner"
    staff |o--o{ crm_customer_profile : "owner"
    crm_customer_profile }o--o{ crm_tag : "crm_profile_tag"
    user ||--o{ crm_customer_note : "notes"
    user ||--o{ crm_followup_case : "cases"
    service |o--o{ crm_followup_case : "inactive service"
    crm_case_reason |o--o{ crm_followup_case : "reason"
    ticket |o--o{ crm_followup_case : "linked ticket"
    staff |o--o{ crm_followup_case : "assigned_to / closed_by"
    user ||--o{ crm_event : "timeline"
    crm_warning_rule |o--o{ crm_service_warning : "rule"
    service ||--o{ crm_service_warning : "warnings (once per period)"
    service ||--o| crm_service_end : "ended (expired / used up)"
    user ||--o{ crm_discount_code : "win-back codes"
    crm_followup_case |o--o{ crm_discount_code : "issued from"
    order |o--o{ crm_discount_code : "reserved by"
    crm_discount_code |o--o{ order : "order.discount_code_id (v1.26)"
    crm_discount_code ||--o{ crm_discount_code_customer : "selected customers"
    crm_discount_code ||--o{ crm_discount_code_plan : "selected plans"
    crm_followup_case |o--o{ crm_event : "case events"

    crm_customer_profile {
        bigint id PK
        bigint user_id FK
        string stage "lead | new | active | at_risk | expired | churned | won_back"
        string stage_override "manual, wins over stage"
        datetime stage_changed_at
        bigint owner_id FK
    }
    crm_tag {
        bigint id PK
        string name UK
        string color
    }
    crm_customer_note {
        bigint id PK
        bigint user_id FK
        bigint staff_id FK
        text body
    }
    crm_followup_case {
        bigint id PK
        bigint user_id FK
        bigint service_id FK
        string kind "no_connection | never_connected | lead | manual | winback"
        string status "open | closed"
        string outcome "resolved | still_inactive | lost | won_back"
        datetime ended_at "win-back"
        decimal recovered_amount "win-back"
        bigint reason_id FK
        text notes
        bigint assigned_to_id FK
        bigint ticket_id FK
        datetime last_online_at
        datetime inactive_since
        datetime auto_message_at
        datetime opened_at
        datetime closed_at
        bool closed_by_system
    }
    crm_case_reason {
        bigint id PK
        string name_fa
        string name_en
        bool is_active
    }
    crm_message_template {
        bigint id PK
        string title
        text body_fa "placeholders {name} {username} {service} {site} {guide}"
        text body_en
        bool is_active
    }
    crm_warning_rule {
        bigint id PK
        string kind "data | time"
        int threshold "percent used / days left"
        bool is_active
        string title_fa
        text body_fa
    }
    crm_service_warning {
        bigint id PK
        bigint service_id FK
        string kind
        int threshold
        string period_key "expiry + volume: changes on renewal"
        datetime due_at "bot / email not before (quiet hours)"
        datetime site_sent_at
        datetime bot_sent_at
        datetime email_sent_at
        datetime renewed_at "converted"
    }
    crm_service_end {
        bigint id PK
        bigint service_id FK
        string status "expired | limited"
        datetime ended_at
    }
    crm_discount_code {
        bigint id PK
        string code UK "up to 32"
        string kind "winback | campaign"
        string name
        bool is_active
        datetime starts_at
        datetime expires_at "null = no end"
        bigint user_id FK "win-back owner"
        string discount_type "percent | fixed"
        int percent
        decimal max_discount
        decimal amount_off
        string audience "all | selected"
        bool first_purchase_only
        string applies_to "new | renew | both"
        int max_uses
        int max_uses_per_customer
        decimal min_order_amount
        bigint case_id FK
        bigint order_id FK "win-back open invoice"
        datetime used_at
    }
    crm_discount_code_customer {
        bigint discountcode_id FK
        bigint user_id FK
    }
    crm_discount_code_plan {
        bigint discountcode_id FK
        bigint plan_id FK
    }
    crm_event {
        bigint id PK
        bigint user_id FK
        string kind "stage | owner | tags | note | case_opened | case_updated | case_closed | message | ticket"
        string actor_label
        json detail
        bigint case_id FK
    }
```

| Table | Description |
|---|---|
| `crm_customer_profile` | CRM data per customer: computed lifecycle stage (+ manual override), owner, tags. |
| `crm_tag` / `crm_profile_tag` | Free tags (name + colour) on customers. |
| `crm_customer_note` | Internal staff notes about a customer. |
| `crm_followup_case` | A "needs follow-up" case: detected inactivity (no connection / never connected), lead or manual; reason, notes, assignee, outcome, linked ticket. |
| `crm_case_reason` | Configurable inactivity reasons (seeded: app not installed, config / setup, filtering / ISP, device, no need now, price, other). |
| `crm_message_template` | Editable follow-up messages (seeded: help connecting). |
| `crm_event` | Timeline of stage changes and staff actions (merged with orders, payments, tickets and notifications on the 360 page). |
| `crm_warning_rule` | Pre-expiry warning thresholds (data % / days left) with their fa / en messages. |
| `crm_service_warning` | One warning per service, threshold and period, with per-channel send times (quiet hours) and conversion. |
| `crm_service_end` | When a service was first seen expired / used up (drives the win-back grace period). |
| `crm_discount_code` | Discount codes (v1.26): the Discount codes page codes (`campaign`) and the single-use win-back codes (`winback`, `user` = owner). Percent (+ cap) or fixed amount, start/end, all or selected customers (`crm_discount_code_customer`), first purchase only, plans (`crm_discount_code_plan`, none = all), new / renewal / both, total and per-customer uses, minimum order. |

Analytics (Phase 5, `crm/analytics.py`) adds no tables — it reads payments, orders, services, CRM and ticket tables.

`crm_case_reason` and `crm_message_template` have a `category` (inactivity / winback); `order.original_amount − order.discount_amount = order.amount` (the final price; `amount_unique` = amount + surcharge is what is paid); `order.discount_code_id` / `discount_code_text` name the code (v1.26).

## 7. Notifications (`notifications`)

```mermaid
erDiagram
    notification ||--o{ notification_delivery : "per user × channel"
    user |o--o{ notification : "target_user (null = broadcast)"
    user ||--o{ notification_delivery : "recipient"
    staff |o--o{ notification : "created_by_staff"

    notification {
        bigint id PK
        string type "event | broadcast | order_confirmed | service_ready | volume_warning | expiry_warning | admin_broadcast | ticket"
        string title
        text body
        string title_en
        text body_en
        bigint target_user_id FK
        string link "user-site path, e.g. /tickets/12"
        bool via_site
        bool via_bot
        bool via_email
    }
    notification_delivery {
        bigint id PK
        bigint notification_id FK
        bigint user_id FK
        string channel "site | bot | email"
        string status "sent | failed | read"
        string error
        datetime sent_at
    }
```

| Table | Description |
|---|---|
| `notification` | A message to one user (event) or everyone (broadcast), with the channels to use and an optional `link` the bell opens (ticket replies → the chat). |
| `notification_delivery` | One delivery attempt per recipient and channel; a failing channel never blocks the others. |

## 8. Settings, CMS, Telegram and ops (`settings_app`, `telegram`, `ops`)

```mermaid
erDiagram
    panel |o--o{ health_check : "panel target"

    setting {
        bigint id PK
        string key UK
        text value
        string value_type "str | int | bool | json"
    }
    site_config {
        bigint id PK "single row"
        string site_name_fa
        string site_name_en
        string site_domain
        string logo
        string support_telegram
        string qr_background
    }
    theme {
        bigint id PK
        string name
        json palette
        bool is_active
    }
    page {
        bigint id PK
        string slug UK "rules | tutorial | faq"
        string title_fa
        text body_fa
        bool is_active
    }
    app_release {
        bigint id PK
        string platform "android | ios"
        string file
        string version
    }
    email_settings {
        bigint id PK "single row"
        bool enabled
        string host
        int port
        text password "enc"
        datetime last_success_at
        text last_error
    }
    domain_config {
        bigint id PK "single row"
        text cloudflare_token "enc, write-only"
        json last_test
        int transition_days
    }
    domain_change {
        bigint id PK
        string old_domain
        string new_domain
        bool include_www
        string mode "cloudflare | manual"
        string zone_name
        string status "draft | applying | transition | done | rolled_back | cancelled"
        json steps "state per step"
        json checklist
        datetime old_until
    }
    telegram_config {
        bigint id PK
        string bot_type "sales | backup"
        text token "enc"
        string proxy_url
        bigint backup_chat_id
    }
    required_channel {
        bigint id PK
        string channel_id
        string invite_link
        int member_count
        bool bot_is_admin
    }
    telegram_stats {
        bigint id PK
        int bot_member_count
        int overlap_bot_channels
    }
    health_check {
        bigint id PK
        string target "site | mysql | redis | celery_worker | celery_beat | bot_sales | bot_backup | panel | mail"
        bigint panel_id FK
        bool is_up
        int latency_ms
    }
    resource_stat {
        bigint id PK
        float cpu_percent
        float ram_percent
        float disk_percent
        bigint net_in
        bigint net_out
    }
    backup_log {
        bigint id PK
        string filename
        bigint size
        string status "ok | failed"
        bool sent_to_telegram
        datetime local_deleted_at
    }
    cleanup_run {
        bigint id PK
        bigint freed_bytes
        json deleted
        json warnings
        bool alerted
    }
```

| Table | Description |
|---|---|
| `setting` | Typed key/value runtime settings (intervals, unique-amount range, alert thresholds, agency switches, retention, ticket limits, CRM thresholds, …) edited in the panel. |
| `site_config` | Branding singleton: names, domain, logo / favicon, bot texts, support contacts, QR background. |
| `theme` | Colour themes; exactly one active. |
| `page` | CMS pages (rules, tutorial, FAQ) in fa/en. |
| `app_release` | Operator tools served from this server (Android SMS app, iPhone Shortcut). |
| `email_settings` | Outgoing-mail relay (single row), with the last success / error. |
| `domain_config` | Settings → Domain & Cloudflare (single row): encrypted Cloudflare token, last token test, transition days ([domain.md](domain.md)). |
| `domain_change` | One run of the domain-change wizard: old → new, DNS mode / zone, status, per-step state and messages, checklist, end of the transition. |
| `telegram_config` | The two bots (sales, backup): encrypted token, proxy, backup chat. |
| `required_channel` | Forced-join channels of the sales bot with member counts. |
| `telegram_stats` | Periodic bot / channel member snapshot. |
| `health_check` / `resource_stat` | Monitoring samples (targets incl. each panel; CPU / RAM / disk / network). |
| `backup_log` / `cleanup_run` | Every DB backup (and whether Telegram got it) and every retention run. |

Framework tables (`django_celery_beat_*` periodic tasks, `django_session`,
`django_migrations`, `auth_*`, `django_content_type`, `django_admin_log`) are
not listed.
