import { useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { useConfirm } from './ConfirmDialog'
import { Ic } from './AgencyIcons'

// v1.49 (multi-tenant Phase 6, D5) the store's own Telegram bot on «فروشگاه» — our staff only (backend apps/tenancy/bots.py).
// Webhook mode: Telegram calls OUR host; the menu button opens the store's Mini App (its domain). The token is write-only.
const T = {
  fa: {
    title: 'ربات تلگرام فروشگاه', none: 'هنوز رباتی وصل نشده — فروشگاه فعلاً فقط سایت دارد.',
    how: 'نماینده در @BotFather یک ربات می‌سازد (‎/newbot‎) و توکن را به ما می‌دهد. ربات‌های خودمان پذیرفته نمی‌شوند.',
    token: 'توکن ربات (از BotFather)', set: 'اتصال ربات', replace: 'جایگزینی توکن', st_ok: 'وصل و سالم', st_error: 'خطا',
    last_update: 'آخرین پیام از تلگرام', webhook: 'وبهوک تنظیم شد', never: 'هنوز نه', error: 'خطا',
    check: 'بررسی', reapply: 'اعمال دوباره (وبهوک، دکمهٔ مینی‌اپ، توضیحات)', remove: 'حذف ربات',
    miniapp: 'دکمهٔ منوی ربات، سایت فروشگاه را به‌عنوان مینی‌اپ باز می‌کند (به دامنهٔ فعال نیاز دارد).',
    s_title: 'اتصال ربات فروشگاه', s_msg: 'وبهوک این ربات روی سرور ما تنظیم می‌شود و از این به بعد مشتری‌های همین فروشگاه با آن کار می‌کنند.',
    s_replace: ' ربات قبلی \u200e@{u}\u200e دیگر به سرور ما پیام نمی‌دهد.', s_btn: 'بله، وصل کن',
    r_title: 'حذف ربات فروشگاه', r_msg: 'وبهوک \u200e@{u}\u200e حذف می‌شود و ربات دیگر جواب نمی‌دهد؛ اعلان‌های تلگرامی مشتری‌های این فروشگاه هم قطع می‌شود. سایت فروشگاه کار می‌کند.',
    r_btn: 'بله، حذف شود',
  },
  en: {
    title: 'Store Telegram bot', none: 'No bot connected yet — the store only has its site for now.',
    how: 'The reseller creates a bot with @BotFather (/newbot) and gives us the token. Our own bots are refused.',
    token: 'Bot token (from BotFather)', set: 'Connect bot', replace: 'Replace token', st_ok: 'Connected', st_error: 'Error',
    last_update: 'Last update from Telegram', webhook: 'Webhook set', never: 'not yet', error: 'Error',
    check: 'Check', reapply: 'Apply again (webhook, Mini App button, description)', remove: 'Remove bot',
    miniapp: 'The bot’s menu button opens the store’s site as its Mini App (needs an active domain).',
    s_title: 'Connect the store bot', s_msg: 'This bot’s webhook is set to our server; from now on this store’s customers use it.',
    s_replace: ' The previous bot (@{u}) stops calling our server.', s_btn: 'Yes, connect it',
    r_title: 'Remove the store bot', r_msg: '@{u}’s webhook is deleted and the bot stops answering; this store’s customers get no Telegram notifications. The store site keeps working.',
    r_btn: 'Yes, remove it',
  },
}

export default function StoreBot({ base, bot, manage, onChanged }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const url = base + 'bot/'

  const connect = async (e) => {
    e.preventDefault()
    const t = token.trim()
    if (!t) return
    const ok = await confirm({ tone: 'primary', icon: 'link', title: s.s_title, targetLabel: s.title, targetId: bot ? '@' + bot.username : undefined,
      message: s.s_msg + (bot ? s.s_replace.replace('{u}', bot.username) : ''), confirmLabel: s.s_btn,
      action: () => api.post(url, { token: t }) })
    if (ok) { setToken(''); onChanged() }
  }
  const check = async (apply) => {
    setBusy(true)
    try { await api.post(url + 'check/', apply ? { apply: true } : {}); onChanged() } catch { /* the toast shows why */ } finally { setBusy(false) }
  }
  const remove = async () => {
    const ok = await confirm({ tone: 'danger', icon: 'trash', title: s.r_title, targetLabel: s.title, targetId: '@' + bot.username,
      message: s.r_msg.replace('{u}', bot.username), confirmLabel: s.r_btn, action: () => api.delete(url) })
    if (ok) onChanged()
  }

  return (
    <section className="sb" data-testid="store-bot">
      <style>{CSS}</style>
      <div className="sb-sub"><Ic n="bell" size={14} />{s.title}</div>
      {!bot && <p className="text-sm text-muted">{s.none}</p>}
      {bot && (
        <div className="sb-card" data-state={bot.state}>
          <div className="sb-head">
            <a className="sb-name" href={`https://t.me/${bot.username}`} target="_blank" rel="noreferrer"><bdi dir="ltr">@{bot.username}</bdi></a>
            <span className="sb-pill" data-st={bot.state}>{s['st_' + bot.state] || bot.state}</span>
          </div>
          <p className="text-xs text-muted sb-meta">
            {s.webhook}: {bot.webhook_set_at ? jalali(bot.webhook_set_at, true, lang) : s.never} ·{' '}
            {s.last_update}: {bot.last_update_at ? jalali(bot.last_update_at, true, lang) : s.never}
          </p>
          {bot.state === 'error' && bot.last_error && <p className="sb-err"><b>{s.error}:</b> <bdi dir="ltr">{bot.last_error}</bdi></p>}
          <p className="text-xs text-muted">{s.miniapp}</p>
          {manage && (
            <div className="sb-acts">
              <button type="button" className="ag-act" onClick={() => check(false)} disabled={busy}><Ic n="sync" />{s.check}</button>
              <button type="button" className="ag-act" onClick={() => check(true)} disabled={busy}>{s.reapply}</button>
              <button type="button" className="ag-act" data-tone="danger" onClick={remove} disabled={busy}><Ic n="trash" />{s.remove}</button>
            </div>
          )}
        </div>
      )}
      {manage && (
        <form className="sb-form" onSubmit={connect} data-testid="store-bot-form">
          <label className="sb-f"><span>{s.token}</span>
            <input className="input" type="password" dir="ltr" autoComplete="off" autoCapitalize="none" spellCheck={false}
              value={token} onChange={(e) => setToken(e.target.value)} placeholder="123456789:AA…" /></label>
          <button className="btn-primary text-sm sb-btn" disabled={!token.trim()}>{bot ? s.replace : s.set}</button>
          <p className="text-xs text-muted sb-how">{s.how}</p>
        </form>
      )}
    </section>
  )
}

const CSS = `
.sb { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--c-border); padding-top: 12px; min-width: 0; }
.sb-sub { display: flex; align-items: center; gap: 6px; font-weight: 800; font-size: 13.5px; }
.sb-card { display: flex; flex-direction: column; gap: 6px; padding: 12px; border-radius: 14px; border: 1px solid var(--c-border); background: var(--c-bg); min-width: 0; }
.sb-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.sb-name { font-weight: 800; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 13.5px; color: var(--c-text); overflow-wrap: anywhere; }
.sb-pill { font-size: 12px; font-weight: 800; padding: 2px 10px; border-radius: 999px; color: var(--c-success-fg);
  background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.sb-pill[data-st="error"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.sb-meta { margin: 0; }
.sb-err { margin: 0; font-size: 12.5px; color: var(--c-danger-fg); overflow-wrap: anywhere; }
.sb-acts { display: flex; flex-wrap: wrap; gap: 6px; }
.sb-acts .ag-act { min-height: 44px; }
.sb-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 8px; align-items: end; }
.sb-f { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.sb-btn { min-height: 44px; }
.sb-how { grid-column: 1 / -1; margin: 0; }
@media (max-width: 767px) { .sb-f .input { font-size: 16px; min-height: 44px; } }
`
