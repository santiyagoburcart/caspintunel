// v1.60.1 store «ربات تلگرام» (store panels only, settings.manage): the store's bot (read-only — our support connects it),
// «اشتراک شماره تلفن اجباری باشد», mandatory channels (the bot must be admin there; checked per channel) and the staff's
// own Telegram link (numeric id + confirm button, or a one-time link) so the store bot treats them as the store's staff.
import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { digits, jalali } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import { Spinner, Toggle } from '../components/ui'

const T = {
  fa: {
    h1: 'ربات تلگرام', sub: 'ربات فروشگاه، شرط‌های ورود مشتری و اتصال تلگرام ادمین‌ها',
    bot_h: 'ربات فروشگاه', no_bot: 'هنوز رباتی وصل نشده — برای اتصال، توکن ربات خود (از ‎@BotFather‎) را به پشتیبانی بدهید.',
    ok: 'وصل و سالم', error: 'خطا — پشتیبانی در جریان است', last_update: 'آخرین پیام', never: 'هنوز پیامی نرسیده',
    phone_h: 'شماره تلفن', phone_l: 'اشتراک شماره تلفن اجباری باشد',
    phone_d: 'روشن: مشتری قبل از هر کاری در ربات باید با دکمهٔ «ارسال شماره» شمارهٔ خودش را بفرستد؛ در مینی‌اپ هم همین را می‌خواهد و در ثبت‌نام سایت شماره الزامی است.',
    ch_h: 'کانال‌های اجباری', ch_d: 'مشتری فقط بعد از عضویت در این کانال‌ها از ربات و مینی‌اپ استفاده می‌کند. ربات فروشگاه باید ادمین کانال باشد؛ کانالی که ربات در آن ادمین نیست اعمال نمی‌شود. بدون کانال = خاموش.',
    ch_none: 'کانالی ثبت نشده (عضویت اجباری خاموش است).', ch_id: 'یوزرنیم کانال یا آیدی عددی (مثلاً ‎@mychannel‎ یا ‎-100…‎)',
    ch_link: 'لینک دعوت (برای کانال خصوصی)', ch_title: 'نام نمایشی (اختیاری)', add: 'افزودن کانال',
    admin_ok: 'فعال — ربات ادمین است', admin_no: 'اعمال نمی‌شود — ربات را ادمین کانال کنید', members: 'عضو', checked: 'بررسی',
    check: 'بررسی دوباره', active: 'فعال', remove: 'حذف', r_title: 'حذف کانال', r_msg: 'کانال {c} از عضویت اجباری برداشته می‌شود.', r_btn: 'بله، حذف شود',
    staff_h: 'اتصال تلگرام من (ادمین ربات)', staff_d: 'بعد از اتصال، ربات فروشگاه شما را ادمین فروشگاه می‌شناسد: هشدارها، دکمه‌های تأیید / رد پرداخت و تیکت‌ها — فقط در حد دسترسی‌های شما. هر ادمین حساب خودش را از همین‌جا وصل می‌کند.',
    linked: 'تلگرام شما وصل است', not_linked: 'هنوز وصل نیست', since: 'از', unlink: 'قطع اتصال',
    tid: 'آیدی عددی تلگرام', tid_send: 'ارسال پیام تأیید', how: 'چطور آیدی عددی‌ام را پیدا کنم؟',
    how_t: ['در تلگرام یکی از ربات‌های نمایش آیدی (مثلاً ‎@userinfobot‎) را باز کنید و Start را بزنید.', 'عددی که جلوی Id نشان می‌دهد آیدی عددی شماست (فقط رقم، مثلاً 123456789).', 'قبل از ارسال، ربات فروشگاه را یک‌بار باز کنید و Start را بزنید — بعد پیام تأیید را در همان ربات می‌گیرید.'],
    or: 'یا', one_link: 'لینک یک‌بارمصرف', link_l: 'این لینک را در گوشی‌ای که تلگرامتان روی آن است باز کنید (۱۰ دقیقه اعتبار):', copy: 'کپی', copied: 'کپی شد', open: 'باز کردن در تلگرام',
  },
  en: {
    h1: 'Telegram bot', sub: 'Your store’s bot, the customer sign-in rules and your staff’s Telegram link',
    bot_h: 'Store bot', no_bot: 'No bot connected yet — give support your bot token (from @BotFather) to connect it.',
    ok: 'Connected', error: 'Error — support has been told', last_update: 'last update', never: 'no update yet',
    phone_h: 'Phone number', phone_l: 'Phone sharing is required',
    phone_d: 'On: before anything else in the bot the customer must send their own number with the «Share number» button; the Mini App asks the same and site sign-up requires a phone.',
    ch_h: 'Mandatory channels', ch_d: 'Customers use the bot and the Mini App only after joining these channels. Your bot must be an admin there — a channel where it is not admin is not enforced. No channel = off.',
    ch_none: 'No channel (mandatory join is off).', ch_id: 'Channel username or numeric id (e.g. @mychannel or -100…)',
    ch_link: 'Invite link (for a private channel)', ch_title: 'Display name (optional)', add: 'Add channel',
    admin_ok: 'Enforced — the bot is admin', admin_no: 'Not enforced — make the bot an admin', members: 'members', checked: 'checked',
    check: 'Check again', active: 'Active', remove: 'Remove', r_title: 'Remove channel', r_msg: 'Channel {c} is no longer mandatory.', r_btn: 'Yes, remove it',
    staff_h: 'My Telegram (bot admin)', staff_d: 'Once linked, the store bot treats you as the store’s staff: alerts, approve / reject buttons for payments and tickets — within your permissions. Every staff member links their own account here.',
    linked: 'Your Telegram is linked', not_linked: 'Not linked yet', since: 'since', unlink: 'Unlink',
    tid: 'Numeric Telegram id', tid_send: 'Send confirmation', how: 'How do I find my numeric id?',
    how_t: ['In Telegram open an id bot (e.g. @userinfobot) and press Start.', 'The number shown next to Id is your numeric id (digits only, e.g. 123456789).', 'Before sending, open the store bot once and press Start — the confirmation arrives in that bot.'],
    or: 'or', one_link: 'One-time link', link_l: 'Open this link on the phone where your Telegram is (valid 10 minutes):', copy: 'Copy', copied: 'Copied', open: 'Open in Telegram',
  },
}

export default function BotSettings() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [d, setD] = useState(null)
  const load = () => api.get('/admin/channels/').then((r) => setD(r.data)).catch(() => setD({ results: [], enforcement: {}, bot: null }))
  useEffect(() => { load() }, [])
  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="bs space-y-4" data-testid="store-bot-page">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.h1}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      <BotCard bot={d.bot} s={s} lang={lang} />
      <PhoneCard on={!!d.enforcement?.force_share_phone} s={s} onChanged={load} />
      <Channels rows={d.results || []} s={s} lang={lang} onChanged={load} />
      <MyTelegram s={s} lang={lang} />
    </div>
  )
}

function BotCard({ bot, s, lang }) {
  return (
    <section className="card bs-card" data-testid="bs-bot">
      <h2 className="bs-h">{s.bot_h}</h2>
      {!bot ? <p className="text-sm text-muted">{s.no_bot}</p> : (
        <div className="bs-row">
          <a className="bs-name" href={`https://t.me/${bot.username}`} target="_blank" rel="noreferrer"><bdi dir="ltr">@{bot.username}</bdi></a>
          <span className="bs-pill" data-ok={bot.state === 'ok' ? '1' : '0'}>{bot.state === 'ok' ? s.ok : s.error}</span>
          <span className="text-xs text-muted">{s.last_update}: {bot.last_update_at ? jalali(bot.last_update_at, true, lang) : s.never}</span>
        </div>
      )}
    </section>
  )
}

function PhoneCard({ on, s, onChanged }) {
  const [busy, setBusy] = useState(false)
  const flip = async () => {
    setBusy(true)
    try { await api.put('/admin/channels/enforcement/', { force_share_phone: !on }); onChanged() } catch { /* toast */ } finally { setBusy(false) }
  }
  return (
    <section className="card bs-card" data-testid="bs-phone">
      <h2 className="bs-h">{s.phone_h}</h2>
      <div className="bs-toggle">
        <span className="bs-tl">{s.phone_l}</span>
        <Toggle checked={on} onChange={flip} disabled={busy} label={s.phone_l} />
      </div>
      <p className="text-xs text-muted leading-6">{s.phone_d}</p>
    </section>
  )
}

function Channels({ rows, s, lang, onChanged }) {
  const confirm = useConfirm()
  const [f, setF] = useState({ channel_id: '', invite_link: '', title: '' })
  const [busy, setBusy] = useState(null)
  const add = async (e) => {
    e.preventDefault()
    if (!f.channel_id.trim()) return
    setBusy('add')
    try { await api.post('/admin/channels/', { ...f, channel_id: f.channel_id.trim(), invite_link: f.invite_link.trim() }); setF({ channel_id: '', invite_link: '', title: '' }); onChanged() }
    catch { /* toast */ } finally { setBusy(null) }
  }
  const check = async (c) => { setBusy(c.id); try { await api.post(`/admin/channels/${c.id}/test/`); onChanged() } catch { /* toast */ } finally { setBusy(null) } }
  const toggle = async (c) => { try { await api.patch(`/admin/channels/${c.id}/`, { is_active: !c.is_active }); onChanged() } catch { /* toast */ } }
  const remove = async (c) => {
    const ok = await confirm({ tone: 'danger', icon: 'trash', title: s.r_title, targetLabel: s.ch_h, targetId: c.title || c.channel_id,
      message: s.r_msg.replace('{c}', c.title || c.channel_id), confirmLabel: s.r_btn, action: () => api.delete(`/admin/channels/${c.id}/`) })
    if (ok) onChanged()
  }
  return (
    <section className="card bs-card" data-testid="bs-channels">
      <h2 className="bs-h">{s.ch_h}</h2>
      <p className="text-xs text-muted leading-6">{s.ch_d}</p>
      {rows.length === 0 && <p className="text-sm text-muted">{s.ch_none}</p>}
      {rows.map((c) => (
        <div key={c.id} className="bs-ch" data-testid="bs-channel" data-admin={c.bot_is_admin ? '1' : '0'}>
          <div className="bs-ch-top">
            <b className="bs-ch-name">{c.title || c.channel_id}</b>
            <bdi dir="ltr" className="bs-mono">{c.channel_id}</bdi>
            <span className="bs-pill" data-ok={c.bot_is_admin && c.is_active ? '1' : '0'}>{c.bot_is_admin ? s.admin_ok : s.admin_no}</span>
          </div>
          <div className="bs-ch-meta">
            {c.member_count ? <span>{digits(c.member_count, lang)} {s.members}</span> : null}
            {c.last_synced_at && <span>{s.checked}: {jalali(c.last_synced_at, true, lang)}</span>}
            {c.invite_link && <bdi dir="ltr" className="bs-mono">{c.invite_link}</bdi>}
          </div>
          <div className="bs-acts">
            <button type="button" className="bs-act" onClick={() => check(c)} disabled={busy === c.id}>{busy === c.id ? <Spinner /> : s.check}</button>
            <label className="bs-act bs-act--tg"><Toggle checked={c.is_active} onChange={() => toggle(c)} label={s.active} /><span>{s.active}</span></label>
            <button type="button" className="bs-act" data-tone="danger" onClick={() => remove(c)}>{s.remove}</button>
          </div>
        </div>
      ))}
      <form className="bs-add" onSubmit={add} data-testid="bs-channel-add">
        <input className="input" dir="ltr" placeholder={s.ch_id} aria-label={s.ch_id} value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })} />
        <input className="input" dir="ltr" placeholder={s.ch_link} aria-label={s.ch_link} value={f.invite_link} onChange={(e) => setF({ ...f, invite_link: e.target.value })} />
        <input className="input" placeholder={s.ch_title} aria-label={s.ch_title} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        <button className="btn-primary text-sm bs-btn" disabled={!f.channel_id.trim() || busy === 'add'}>{s.add}</button>
      </form>
    </section>
  )
}

// Persian / Arabic digits typed on a phone keyboard count too (input normalization only — CLAUDE.md digits rule)
const latinDigits = (v) => String(v || '').replace(/[۰-۹]/g, (x) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(x)))
  .replace(/[٠-٩]/g, (x) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(x))).replace(/\D/g, '')

function MyTelegram({ s, lang }) {
  const toast = useToast()
  const [st, setSt] = useState(null)
  const [tid, setTid] = useState('')
  const [link, setLink] = useState(null)
  const load = () => api.get('/admin/tickets/telegram-link/').then((r) => setSt(r.data)).catch(() => setSt({ linked: false }))
  useEffect(() => { load() }, [])
  const send = async (e) => {
    e.preventDefault()
    try { await api.put('/admin/tickets/telegram-link/', { telegram_id: latinDigits(tid) }) }
    catch { /* toast */ }
  }
  const oneTime = async () => {
    try { const r = await api.post('/admin/tickets/telegram-link/', null, { quiet: true }); setLink(r.data) } catch (e) { toast.error(apiError(e)) }
  }
  const unlink = async () => { try { await api.delete('/admin/tickets/telegram-link/'); setLink(null); load() } catch { /* toast */ } }
  if (!st) return null
  return (
    <section className="card bs-card" data-testid="bs-staff">
      <h2 className="bs-h">{s.staff_h}</h2>
      <p className="text-xs text-muted leading-6">{s.staff_d}</p>
      <div className="bs-row">
        <span className="bs-pill" data-ok={st.linked ? '1' : '0'}>{st.linked ? s.linked : s.not_linked}</span>
        {st.linked && st.linked_at && <span className="text-xs text-muted">{s.since} {jalali(st.linked_at, true, lang)}</span>}
        {st.linked && <button type="button" className="bs-act" data-tone="danger" onClick={unlink}>{s.unlink}</button>}
      </div>
      <form className="bs-tid" onSubmit={send}>
        <label className="bs-fld"><span className="label">{s.tid}</span>
          <input className="input" dir="ltr" inputMode="numeric" placeholder="123456789" value={tid} onChange={(e) => setTid(e.target.value)} data-testid="bs-tid" /></label>
        <button className="btn-primary text-sm bs-btn" disabled={latinDigits(tid).length < 5}>{s.tid_send}</button>
      </form>
      <details className="bs-how"><summary>{s.how}</summary>
        <ol>{s.how_t.map((x, i) => <li key={x}><b>{digits(i + 1, lang)}</b><span>{x}</span></li>)}</ol>
      </details>
      <div className="bs-row"><span className="text-xs text-muted">{s.or}</span>
        <button type="button" className="bs-act" onClick={oneTime} data-testid="bs-onetime">{s.one_link}</button></div>
      {link && (
        <div className="bs-link">
          <span className="text-xs text-muted">{s.link_l}</span>
          {link.deep_link && <a className="btn-primary text-sm bs-btn" href={link.deep_link} target="_blank" rel="noreferrer">{s.open}</a>}
          <div className="bs-copy"><code dir="ltr">{link.deep_link || link.command}</code>
            <button type="button" className="bs-act" onClick={async () => { if (await copyToClipboard(link.deep_link || link.command)) toast.success(s.copied) }}>{s.copy}</button></div>
        </div>
      )}
    </section>
  )
}

const CSS = `
.bs-card { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.bs-h { font-size: 15px; font-weight: 800; }
.bs-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.bs-name { font-weight: 800; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.bs-pill { font-size: 12px; font-weight: 800; padding: 2px 10px; border-radius: 999px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.bs-pill[data-ok="1"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.bs-toggle { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 44px; padding: 6px 12px; border-radius: 12px; border: 1px solid var(--c-border); }
.bs-tl { font-weight: 700; font-size: 14px; }
.bs-ch { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: 14px; border: 1px solid var(--c-border); background: var(--c-bg); min-width: 0; }
.bs-ch-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.bs-ch-name { font-size: 14px; }
.bs-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; overflow-wrap: anywhere; color: var(--c-text-muted); }
.bs-ch-meta { display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: var(--c-text-muted); min-width: 0; }
.bs-acts { display: flex; flex-wrap: wrap; gap: 6px; }
.bs-act { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--c-border); background: var(--c-bg); font-size: 13px; font-weight: 700; color: var(--c-text); }
.bs-act[data-tone="danger"] { color: var(--c-danger-fg); }
.bs-add { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 8px; align-items: center; }
.bs-add .input, .bs-tid .input { min-height: 44px; min-width: 0; }
.bs-btn { min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
.bs-tid { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; }
.bs-fld { display: flex; flex-direction: column; gap: 6px; flex: 1 1 220px; min-width: 0; }
.bs-how { border: 1px dashed var(--c-border); border-radius: 12px; padding: 0 12px; }
.bs-how summary { min-height: 44px; display: flex; align-items: center; cursor: pointer; font-size: 13px; font-weight: 700; color: var(--c-primary); }
.bs-how ol { display: flex; flex-direction: column; gap: 6px; padding-bottom: 10px; font-size: 12.5px; line-height: 1.9; }
.bs-how li { display: flex; gap: 8px; align-items: flex-start; }
.bs-how b { width: 22px; height: 22px; flex: 0 0 auto; border-radius: 999px; display: grid; place-items: center; font-size: 11px; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.bs-link { display: flex; flex-direction: column; gap: 8px; }
.bs-copy { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.bs-copy code { flex: 1; min-width: 0; font-size: 12px; overflow-wrap: anywhere; }
@media (max-width: 767px) { .bs-add .input, .bs-tid .input { font-size: 16px; } .bs-btn { flex: 1 1 100%; } }
`
