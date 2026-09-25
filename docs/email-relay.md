# Email relay — making verification / reset / notification mail actually deliver

## Why you need this

The stack runs its own mail server (`mailserver` container, docker-mailserver in
`SMTP_ONLY` mode: Postfix only, no mailboxes/Dovecot — the app only sends). The
app hands mail to it on port 25 inside the Docker network — but **outbound port
25 is blocked by almost every cloud provider**
(Vultr, DigitalOcean, Hetzner, AWS, …). So mail addressed to Gmail / Outlook /
Yahoo / etc. just sits in the Postfix queue and never leaves.

Verified on the aicaspin.ir server (2026-09-25): connections to Gmail/Outlook MX
on port 25 time out (the message stays deferred in the queue), while outbound
587 works — so a relay on 587 is required there.

The fix is an **SMTP relay**: the mail server authenticates to a third-party
provider on port 587 and hands them every outgoing message. They do the actual
delivery (and reputation management) for you.

Email is always optional. With no relay configured the app still runs fine —
verification / reset / notification emails are simply skipped, never a crash, and
email verification is **off by default** (toggle it in the admin panel only once
delivery works).

---

## Step 1 — pick a provider and sign up

You need an account with **one** of these. Free tiers are enough for a VPN shop's
transactional volume. Pick based on what you can sign up for from your region.

| Provider | Free tier | Signup | Notes |
|---|---|---|---|
| **Mailgun** | 100 emails/day (trial 5 000/mo) | mailgun.com | Easiest. Card required. |
| **Brevo** (ex-Sendinblue) | 300 emails/day | brevo.com | No card. Good if Mailgun won't take your signup. |
| **SendGrid** | 100 emails/day | sendgrid.com | Twilio account. |
| **Amazon SES** | 3 000/mo (in the free tier window) | aws.amazon.com | Needs an AWS account + a "move out of sandbox" request. |
| **Gmail** | ~500/day | your existing Google account | Lowest effort, but `From:` **must** be your Gmail address, and Google may rate-limit. Fine for a small shop. |

## Step 2 — verify your sending domain (do NOT skip)

In the provider's dashboard, add and **verify your domain** (`aicaspin.ir` or
whatever `DOMAIN` is). They give you 2–4 DNS records (a domain-key TXT, a CNAME
or two, sometimes an MX for bounces). Add them at your DNS host (Cloudflare —
**DNS-only / grey cloud** for any mail-related record).

Without domain verification your mail will be rejected or land in spam. (Gmail is
the exception — it sends as your Gmail address and needs no domain setup.)

Also make sure your own SPF record lets the provider send:

```
TXT  @   v=spf1 include:mailgun.org include:_spf.google.com mx ~all
```

(use the `include:` your provider tells you — Mailgun `mailgun.org`,
SendGrid `sendgrid.net`, Brevo `spf.brevo.com`, SES `amazonses.com`, Gmail
`_spf.google.com`.)

## Step 3 — get the SMTP credentials

Each provider has an **"SMTP" / "SMTP relay"** page (not the HTTP API page):

| Provider | `SMTP_RELAY_HOST` | `SMTP_RELAY_PORT` | `SMTP_RELAY_USER` | `SMTP_RELAY_PASSWORD` |
|---|---|---|---|---|
| Mailgun | `smtp.mailgun.org` | `587` | `postmaster@mg.<domain>` (shown on the Sending → Domain settings → SMTP page) | the SMTP password on that page (**not** your login password) |
| Brevo | `smtp-relay.brevo.com` | `587` | your Brevo account email | an **SMTP key** from Settings → SMTP & API |
| SendGrid | `smtp.sendgrid.net` | `587` | literally the word `apikey` | an API key with "Mail Send" permission |
| Amazon SES | `email-smtp.<region>.amazonaws.com` | `587` | the SES SMTP username | the SES SMTP password (generated once, in "SMTP settings → Create credentials") |
| Gmail | `smtp.gmail.com` | `587` | `you@gmail.com` | a 16-char **App Password** (Google Account → Security → 2-Step Verification → App passwords) |

## Step 4 — put them in `.env`

On the server, edit `/opt/caspintunel/.env` (or wherever you deployed):

```ini
SMTP_RELAY_HOST=smtp.mailgun.org
SMTP_RELAY_PORT=587
SMTP_RELAY_USER=postmaster@mg.aicaspin.ir
SMTP_RELAY_PASSWORD=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# make sure the From address is on the verified domain (or your Gmail address)
DEFAULT_FROM_EMAIL=no-reply@aicaspin.ir
```

`.env` is git-ignored and `chmod 600`. Never commit these.

> The relay credentials are read by the **mailserver container at start-up**, not
> by Django — that's why they live in `.env` and not in the panel UI. The panel
> shows the resulting status and has a "send test" button.

## Step 5 — apply and test

```bash
cd /opt/caspintunel
docker compose up -d --force-recreate mailserver      # picks up the new RELAY_* env
docker compose exec web python manage.py send_test_email you@personal-inbox.com
```

`send_test_email` prints the effective config and hands the message to Postfix.
Check the inbox. If it doesn't arrive within a minute:

```bash
docker compose logs --tail=50 mailserver | grep -Ei 'relay|sasl|auth|status='
```

Common errors:

| Log line | Meaning | Fix |
|---|---|---|
| `SASL authentication failed` | wrong `SMTP_RELAY_USER` / `PASSWORD` | re-copy from the provider's SMTP page (not the API/login page) |
| `Sender address rejected: not owned by user` | `DEFAULT_FROM_EMAIL` isn't on a verified domain | verify the domain, or set the From to your Gmail address |
| `Relay access denied` | domain not verified / still in provider sandbox | finish domain verification; for SES request production access |
| mail sends but lands in spam | SPF/DKIM/DMARC not aligned | add the provider's DNS records; keep our `default._domainkey` TXT too |

## Step 6 — turn on verification (optional)

Once a test email arrives: admin panel → **Pasargad Panel** page shows the email
status, or you can flip **email verification required** wherever that setting
lives. New signups then get a verify link; the account still works immediately if
the mail fails.

---

## Alternative: skip the local mail server entirely

If you don't care about receiving mail at `@<domain>` and just want outbound to
work, point Django straight at the provider and stop the `mailserver` container:

```ini
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_USER=postmaster@mg.aicaspin.ir
EMAIL_PASSWORD=xxxxxxxxxxxx
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=no-reply@aicaspin.ir
```

```bash
docker compose up -d --force-recreate web
docker compose stop mailserver          # optional
```

DKIM is then handled by the provider (from their domain verification), not our
OpenDKIM. Simpler, but you lose inbound mail and the DMARC alignment from our own
signing.
