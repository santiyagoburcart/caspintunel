import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, digits } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'
import { useToast } from '../components/Toast'
import { EmptyState } from '../components/Art'

const L = {
  fa: {
    title: 'اطلاعیه‌ها', subtitle: 'ارسال اطلاعیهٔ فوری به همهٔ کاربران یا یک کاربر خاص از طریق سایت، ربات یا ایمیل',
    f_title: 'عنوان (فارسی)', f_title_en: 'عنوان (انگلیسی)',
    f_body: 'متن پیام (فارسی)', f_body_en: 'متن پیام (انگلیسی)',
    f_target: 'مخاطب', target_all: 'همهٔ کاربران', target_user: 'کاربر خاص',
    f_user_search: 'جستجوی کاربر (نام، نام کاربری، تلفن)...', f_user_pick: 'یک کاربر را انتخاب کنید',
    f_channels: 'کانال‌های ارسال', ch_site: 'سایت', ch_bot: 'ربات', ch_email: 'ایمیل',
    send: 'ارسال اطلاعیه', sending: 'در حال ارسال...',
    history_title: 'تاریخچهٔ اطلاعیه‌های ارسال‌شده',
    col_title: 'عنوان', col_sent_by: 'ارسال‌کننده', col_target: 'مخاطب', col_channels: 'کانال‌ها',
    col_sent_at: 'زمان ارسال', col_recipients: 'تعداد گیرنده',
    err_title: 'عنوان فارسی الزامی است', err_body: 'متن فارسی الزامی است', err_user: 'یک کاربر را انتخاب کنید',
    err_channel: 'حداقل یک کانال را انتخاب کنید', sent_ok: 'اطلاعیه با موفقیت ارسال شد',
    none_found: 'اطلاعیه‌ای ثبت نشده است',
  },
  en: {
    title: 'Notifications', subtitle: 'Send an instant broadcast to all users or one specific user over site, bot, or email',
    f_title: 'Title (Persian)', f_title_en: 'Title (English)',
    f_body: 'Body (Persian)', f_body_en: 'Body (English)',
    f_target: 'Target', target_all: 'All users', target_user: 'Specific user',
    f_user_search: 'Search user (name, username, phone)…', f_user_pick: 'Pick a user',
    f_channels: 'Send channels', ch_site: 'Site', ch_bot: 'Bot', ch_email: 'Email',
    send: 'Send broadcast', sending: 'Sending…',
    history_title: 'Broadcast history',
    col_title: 'Title', col_sent_by: 'Sent by', col_target: 'Target', col_channels: 'Channels',
    col_sent_at: 'Sent at', col_recipients: 'Recipients',
    err_title: 'Persian title is required', err_body: 'Persian body is required', err_user: 'Pick a user',
    err_channel: 'Pick at least one channel', sent_ok: 'Broadcast sent successfully',
    none_found: 'No broadcasts yet',
  },
}

const blank = { title: '', title_en: '', body: '', body_en: '', target: 'all', target_user: null, via_site: true, via_bot: false, via_email: false }

function UserPicker({ s, value, onPick }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!q.trim()) { setRows([]); return }
    setBusy(true)
    const h = setTimeout(() => {
      api.get(`/admin/users/?search=${encodeURIComponent(q)}&limit=8`)
        .then((r) => setRows(r.data.results || []))
        .catch(() => setRows([]))
        .finally(() => setBusy(false))
    }, 350)
    return () => clearTimeout(h)
  }, [q])

  return (
    <div className="ntf-picker">
      <input className="input" placeholder={s.f_user_search} value={q} onChange={(e) => setQ(e.target.value)} />
      {value && <div className="ntf-picker-selected">#{value.id} — {value.name || value.username}</div>}
      {busy && <div className="text-xs text-muted mt-1">…</div>}
      {rows.length > 0 && (
        <div className="ntf-picker-list">
          {rows.map((u) => (
            <button type="button" key={u.id} className="ntf-picker-row"
              onClick={() => { onPick(u); setQ(''); setRows([]) }}>
              <span>{u.name || u.username || '—'}</span>
              <span className="text-xs text-muted">#{u.id} {u.phone || ''}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Notifications() {
  const { t, lang } = useI18n()
  const s = L[lang] || L.fa
  const toast = useToast()
  const [f, setF] = useState(blank)
  const [pickedUser, setPickedUser] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [rows, setRows] = useState(null)

  const load = () =>
    api.get('/admin/notifications/').then((r) => setRows(r.data.results || r.data)).catch(() => setRows([]))
  useEffect(() => { load() }, [])

  const submit = async (e) => {
    e.preventDefault(); setErr('')
    if (!f.title.trim()) return setErr(s.err_title)
    if (!f.body.trim()) return setErr(s.err_body)
    if (f.target === 'specific_user' && !pickedUser) return setErr(s.err_user)
    if (!f.via_site && !f.via_bot && !f.via_email) return setErr(s.err_channel)

    setBusy(true)
    toast.loading(t('action_in_progress') || s.sending)
    try {
      await api.post('/admin/notifications/broadcast/', {
        title: f.title, title_en: f.title_en, body: f.body, body_en: f.body_en,
        target_user: f.target === 'specific_user' ? pickedUser.id : null,
        via_site: f.via_site, via_bot: f.via_bot, via_email: f.via_email,
      })
      toast.success(s.sent_ok)
      setF(blank); setPickedUser(null)
      load()
    } catch (e2) { setErr(apiError(e2)); toast.error(apiError(e2)) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.title}</h1>
        <p className="text-sm text-muted mt-1">{s.subtitle}</p>
      </div>

      <form className="card ntf-form" onSubmit={submit}>
        <Alert>{err}</Alert>
        <div className="ntf-grid">
          <Field label={s.f_title}>
            <input className="input" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </Field>
          <Field label={s.f_title_en}>
            <input className="input" dir="ltr" value={f.title_en} onChange={(e) => setF({ ...f, title_en: e.target.value })} />
          </Field>
        </div>
        <div className="ntf-grid">
          <Field label={s.f_body}>
            <textarea className="input" rows={3} required value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} />
          </Field>
          <Field label={s.f_body_en}>
            <textarea className="input" dir="ltr" rows={3} value={f.body_en} onChange={(e) => setF({ ...f, body_en: e.target.value })} />
          </Field>
        </div>

        <Field group label={s.f_target}>
          <div className="ntf-target-row">
            <label className="ntf-radio">
              <input type="radio" name="target" checked={f.target === 'all'}
                onChange={() => { setF({ ...f, target: 'all' }); setPickedUser(null) }} />
              {s.target_all}
            </label>
            <label className="ntf-radio">
              <input type="radio" name="target" checked={f.target === 'specific_user'}
                onChange={() => setF({ ...f, target: 'specific_user' })} />
              {s.target_user}
            </label>
          </div>
          {f.target === 'specific_user' && <UserPicker s={s} value={pickedUser} onPick={setPickedUser} />}
        </Field>

        <Field group label={s.f_channels}>
          <div className="ntf-ch-row">
            <label className="ntf-ch"><Toggle checked={f.via_site} onChange={(v) => setF({ ...f, via_site: v })} label={s.ch_site} /> {s.ch_site}</label>
            <label className="ntf-ch"><Toggle checked={f.via_bot} onChange={(v) => setF({ ...f, via_bot: v })} label={s.ch_bot} /> {s.ch_bot}</label>
            <label className="ntf-ch"><Toggle checked={f.via_email} onChange={(v) => setF({ ...f, via_email: v })} label={s.ch_email} /> {s.ch_email}</label>
          </div>
        </Field>

        <div className="flex justify-end">
          <button type="submit" className="btn-primary text-sm" disabled={busy}>{busy ? '…' : s.send}</button>
        </div>
      </form>

      <div className="card p-0 overflow-hidden">
        <div className="ntf-hist-head"><h3 className="text-sm font-bold">{s.history_title}</h3></div>
        {rows === null ? (
          <div className="grid place-items-center py-10"><Spinner /></div>
        ) : rows.length === 0 ? (
          <EmptyState art="bell" text={s.none_found} compact />
        ) : (
          <div className="overflow-x-auto rtable-wrap">
            <table className="w-full text-sm rtable">
              <thead>
                <tr className="text-start text-xs text-muted border-b" style={{ borderColor: 'var(--c-border)' }}>
                  <th className="p-3 text-start">{s.col_title}</th>
                  <th className="p-3 text-start">{s.col_sent_by}</th>
                  <th className="p-3 text-start">{s.col_target}</th>
                  <th className="p-3 text-start">{s.col_channels}</th>
                  <th className="p-3 text-start">{s.col_sent_at}</th>
                  <th className="p-3 text-start">{s.col_recipients}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((n) => (
                  <tr key={n.id} className="border-b last:border-0" style={{ borderColor: 'var(--c-border)' }}>
                    <td data-label={s.col_title} className="p-3 font-semibold">{(lang === 'en' && n.title_en) || n.title}</td>
                    <td data-label={s.col_sent_by} className="p-3 text-muted">{n.sent_by || '—'}</td>
                    <td data-label={s.col_target} className="p-3">{n.target_user ? `#${n.target_user}` : s.target_all}</td>
                    <td data-label={s.col_channels} className="p-3 text-xs text-muted">
                      {[n.via_site && s.ch_site, n.via_bot && s.ch_bot, n.via_email && s.ch_email].filter(Boolean).join(', ')}
                    </td>
                    <td data-label={s.col_sent_at} className="p-3 text-xs text-muted mono-num">{jalali(n.created_at, true, lang)}</td>
                    <td data-label={s.col_recipients} className="p-3 mono-num">{digits(n.delivery_count ?? 0, lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

const CSS = `
.ntf-form { display: flex; flex-direction: column; gap: 16px; }
.ntf-grid { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 640px) { .ntf-grid { grid-template-columns: 1fr 1fr; } }
.ntf-target-row { display: flex; gap: 18px; align-items: center; padding-top: 4px; }
.ntf-radio { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.ntf-ch-row { display: flex; flex-wrap: wrap; gap: 18px; padding-top: 4px; }
.ntf-ch { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; }
.ntf-picker { position: relative; margin-top: 10px; }
.ntf-picker-selected { margin-top: 6px; font-size: 12px; padding: 6px 10px; border-radius: 8px;
  background: color-mix(in srgb, var(--c-primary) 10%, transparent); color: var(--c-primary-fg); display: inline-block; }
.ntf-picker-list { margin-top: 6px; border: 1px solid var(--c-border); border-radius: 10px; overflow: hidden; max-height: 220px; overflow-y: auto; }
.ntf-picker-row { width: 100%; display: flex; justify-content: space-between; gap: 10px; padding: 8px 12px;
  background: var(--c-surface); border: 0; border-bottom: 1px solid var(--c-border); text-align: start; cursor: pointer; font-size: 13px; }
.ntf-picker-row:last-child { border-bottom: 0; }
.ntf-picker-row:hover { background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); }
.ntf-hist-head { padding: 14px 16px; border-bottom: 1px solid var(--c-border); }
`
