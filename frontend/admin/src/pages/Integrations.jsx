import { useEffect, useMemo, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

function Ico({ d, w = 15 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const ICONS = {
  bot: <><rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4M8 16h.01M16 16h.01" /></>,
  cart: <><circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" /><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6" /></>,
  backup: <><path d="M21 12a9 9 0 11-3-6.7L21 8" /><path d="M21 3v5h-5" /></>,
  link: <><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" /></>,
  edit: <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />,
  trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>,
  eye: <><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" /><path d="M1 1l22 22" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
}

// password/secret input with a show/hide eye toggle
function SecretInput({ value, onChange, placeholder, autoComplete = 'new-password' }) {
  const { t } = useI18n()
  const [show, setShow] = useState(false)
  return (
    <div className="int-secret">
      <input className="input" dir="ltr" type={show ? 'text' : 'password'} autoComplete={autoComplete}
        placeholder={placeholder} value={value} onChange={onChange} />
      <button type="button" className="int-secret-eye" onClick={() => setShow((v) => !v)}
        aria-label={t(show ? 'hide_password' : 'show_password')}>
        <Ico d={show ? ICONS.eyeOff : ICONS.eye} w={15} />
      </button>
    </div>
  )
}

const INT_CSS = `
.int-secret { position: relative; }
.int-secret .input { width: 100%; padding-inline-end: 40px; }
.int-secret-eye { position: absolute; inset-inline-end: 10px; top: 50%; transform: translateY(-50%); color: var(--c-text-muted); }
.int-secret-eye:hover { color: var(--c-text); }
.int-head { display: flex; align-items: flex-start; gap: 12px; }
.int-head-ico { width: 40px; height: 40px; border-radius: 12px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.int-card-head { display: flex; align-items: center; gap: 11px; }
.int-card-ico { width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.int-icon-btn { display: inline-flex; padding: 6px; border-radius: 8px; color: var(--c-text-muted); }
.int-icon-btn:hover { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.int-icon-btn--del:hover { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }
`

const T = {
  fa: {
    panel_intro: 'پنل‌های پاسارگارد/PasarGuard خود را اینجا مدیریت کنید. هر پلن به یک پنل متصل می‌شود. رمز عبور رمزنگاری‌شده ذخیره می‌شود و دیگر نمایش داده نمی‌شود.',
    add_panel: 'افزودن پنل', panel_name: 'نام پنل', new_panel: 'پنل جدید',
    del_panel: 'حذف پنل', confirm_del: 'این پنل حذف شود؟',
    in_use: 'پلن', in_use2: 'سرویس',
    base_url: 'آدرس پایه پنل (Base URL)', admin_user: 'نام کاربری ادمین پنل',
    admin_pass: 'رمز عبور ادمین پنل', sub_url: 'آدرس پایهٔ اشتراک (اختیاری)',
    verify_ssl: 'بررسی گواهی SSL پنل', panel_active: 'این پنل فعال است',
    unchanged: '•••••••• (بدون تغییر)',
    pass_stored: 'رمزی ذخیره شده است؛ برای تغییر، رمز جدید را وارد کنید.',
    pass_none: 'هنوز رمزی ذخیره نشده است.',
    saved: 'ذخیره شد.', save: 'ذخیره', test: 'تست اتصال',
    groups: 'گروه‌های پیش‌فرض این پنل', fetch_groups: 'دریافت گروه‌ها از پنل',
    fetching: 'در حال دریافت…',
    groups_hint: 'وقتی یک پلن روی این پنل گروهی تعیین نکند، این گروه‌ها استفاده می‌شوند.',
    groups_none_fetched: 'برای انتخاب از روی نام گروه‌ها، دکمهٔ «دریافت گروه‌ها از پنل» را بزنید. شناسه‌های ذخیره‌شدهٔ فعلی:',
    groups_empty: 'هیچ شناسه‌ای انتخاب نشده است.',
    group_word: 'گروه',
    bots_intro: 'هر ربات توکن جداگانه دارد. توکن‌ها رمزنگاری‌شده ذخیره می‌شوند و نمایش داده نمی‌شوند.',
    sales_bot: 'ربات فروش', backup_bot: 'ربات بک‌آپ', active: 'فعال',
    bot_token: 'توکن ربات (BotFather)', proxy: 'پروکسی (اختیاری)',
    chat_id: 'شناسهٔ چت بک‌آپ (chat_id)',
    token_stored: 'توکنی ذخیره شده است؛ برای تغییر، توکن جدید را وارد کنید.',
    token_none: 'هنوز توکنی ذخیره نشده است.',
    chat_hint: 'فایل‌های پشتیبان به این چت ارسال می‌شوند. برای گرفتن شناسه، در آن چت به ربات بک‌آپ /id بفرستید.',
    bots_saved: 'ذخیره شد. برای اعمال توکن جدید، کانتینر ربات ظرف یک دقیقه به‌روز می‌شود (در صورت نیاز ری‌استارت کنید).',
    email_title: 'ارسال ایمیل', email_host: 'میزبان', email_from: 'فرستنده',
    email_relay_on: 'رله فعال است', email_relay_off: 'رله تنظیم نشده — ایمیل خارجی ارسال نمی‌شود',
    email_ready: 'آمادهٔ ارسال بیرونی', email_not_ready: 'ارسال بیرونی فعال نیست',
    email_relay_hint: 'اطلاعات رله در فایل .env تنظیم می‌شود (SMTP_RELAY_*) — راهنما: docs/email-relay.md',
    email_test_to: 'ارسال ایمیل آزمایشی به', email_send_test: 'ارسال آزمایشی',
    email_verif_on: 'تأیید ایمیل الزامی است', email_verif_off: 'تأیید ایمیل اختیاری است',
    inactive: 'غیرفعال',
    ch_title_h: 'کانال‌های اجباری (عضویت پیش از استفاده از ربات)',
    ch_intro: 'کاربر باید پیش از استفاده از ربات فروش، در همهٔ کانال‌های فعال زیر عضو باشد.',
    ch_add: 'افزودن کانال', ch_cancel: 'انصراف', ch_confirm_del: 'این کانال حذف شود؟',
    ch_none: 'هنوز کانالی اضافه نشده است.',
    ch_id: 'شناسهٔ کانال (@username یا -100...)', ch_title: 'عنوان (اختیاری)',
    ch_invite: 'لینک دعوت (برای کانال خصوصی)',
    ch_invite_hint: 'برای کانال خصوصی که username ندارد، لینک دعوت را وارد کنید تا دکمهٔ «عضویت» به کاربر نمایش داده شود.',
    ch_members: 'اعضا', ch_test: 'تست دسترسی',
    force_join: 'عضویت اجباری در کانال‌ها (force_channel_join)',
    force_phone: 'اشتراک‌گذاری اجباری شمارهٔ تلفن (force_share_phone)',
    ch_admin_hint: 'برای بررسی عضویت کاربران، ربات فروش باید «ادمین» هر کانال باشد. پس از افزودن کانال، ربات را در آن ادمین کنید و سپس «تست دسترسی» را بزنید.',
  },
  en: {
    panel_intro: 'Manage your Pasargad / PasarGuard panels here. Every plan is bound to one panel. Passwords are stored encrypted and never shown again.',
    add_panel: 'Add panel', panel_name: 'Panel name', new_panel: 'New panel',
    del_panel: 'Delete panel', confirm_del: 'Delete this panel?',
    in_use: 'plan', in_use2: 'service',
    base_url: 'Panel Base URL', admin_user: 'Panel admin username',
    admin_pass: 'Panel admin password', sub_url: 'Subscription base URL (optional)',
    verify_ssl: 'Verify panel SSL certificate', panel_active: 'Panel is active',
    unchanged: '•••••••• (unchanged)',
    pass_stored: 'A password is stored; type a new one only to change it.',
    pass_none: 'No password stored yet.',
    saved: 'Saved.', save: 'Save', test: 'Test connection',
    groups: "This panel's default groups", fetch_groups: 'Fetch groups from panel',
    fetching: 'Fetching…',
    groups_hint: 'Used whenever a plan on this panel does not set its own groups.',
    groups_none_fetched: 'Click “Fetch groups from panel” to pick them by name. Currently saved ids:',
    groups_empty: 'No ids selected.',
    group_word: 'group',
    bots_intro: 'Each bot has its own token. Tokens are stored encrypted and never shown.',
    sales_bot: 'Sales bot', backup_bot: 'Backup bot', active: 'Active',
    bot_token: 'Bot token (BotFather)', proxy: 'Proxy (optional)',
    chat_id: 'Backup chat_id',
    token_stored: 'A token is stored; type a new one only to change it.',
    token_none: 'No token stored yet.',
    chat_hint: 'Backups are sent to this chat. Send /id to the backup bot there to get the id.',
    bots_saved: 'Saved. The bot container picks up a new token within a minute (restart it if needed).',
    email_title: 'Email delivery', email_host: 'Host', email_from: 'From',
    email_relay_on: 'Relay configured', email_relay_off: 'No relay — external email will not be delivered',
    email_ready: 'Ready for external delivery', email_not_ready: 'External delivery not active',
    email_relay_hint: 'Relay credentials are set in .env (SMTP_RELAY_*) — see docs/email-relay.md',
    email_test_to: 'Send a test email to', email_send_test: 'Send test',
    email_verif_on: 'Email verification is required', email_verif_off: 'Email verification is optional',
    inactive: 'Disabled',
    ch_title_h: 'Required channels (join before using the bot)',
    ch_intro: 'A user must be a member of every active channel below before using the sales bot.',
    ch_add: 'Add channel', ch_cancel: 'Cancel', ch_confirm_del: 'Delete this channel?',
    ch_none: 'No channels added yet.',
    ch_id: 'Channel (@username or -100...)', ch_title: 'Title (optional)',
    ch_invite: 'Invite link (for private channels)',
    ch_invite_hint: 'For a private channel with no username, add its invite link so users get a “Join” button.',
    ch_members: 'members', ch_test: 'Test access',
    force_join: 'Force channel join (force_channel_join)',
    force_phone: 'Force phone-number share (force_share_phone)',
    ch_admin_hint: 'To check user membership, the sales bot must be an ADMIN of each channel. After adding a channel, make the bot an admin there, then click “Test access”.',
  },
}

/* ================================================================== *
 *  Pasargad / PasarGuard Panels  —  /panel/panel-link                *
 *  Multi-panel manager: list, add, edit, disable, delete.            *
 * ================================================================== */
export function PanelConnection() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [panels, setPanels] = useState(null)
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState('')

  const load = () =>
    api.get('/admin/panels/')
      .then((r) => { setPanels(r.data.results || r.data || []); setErr('') })
      .catch((e) => { setPanels([]); setErr(apiError(e)) })

  useEffect(() => { load() }, [])

  if (!panels) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <style>{INT_CSS}</style>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="int-head">
          <span className="int-head-ico"><Ico d={ICONS.link} w={20} /></span>
          <div>
            <h1 className="text-lg font-bold">{t('panel_link')}</h1>
            <p className="mt-1 text-sm text-muted">{s.panel_intro}</p>
          </div>
        </div>
        {!adding && (
          <button className="btn-primary shrink-0 text-sm inline-flex items-center gap-1.5" onClick={() => setAdding(true)}>
            <Ico d={ICONS.plus} w={14} /> {s.add_panel}
          </button>
        )}
      </div>

      <Alert>{err}</Alert>

      {(adding || panels.length === 0) && (
        <PanelCard s={s} isNew
          onSaved={() => { setAdding(false); load() }}
          onCancel={() => setAdding(false)} />
      )}

      {panels.map((p) => (
        <PanelCard key={p.id} s={s} panel={p} onSaved={load} onDeleted={load} />
      ))}

      <EmailCard s={s} />
    </div>
  )
}

function PanelCard({ s, panel, isNew = false, onSaved, onDeleted, onCancel }) {
  const { t } = useI18n()
  const blank = {
    name: '', base_url: '', admin_username: '', admin_password: '',
    subscription_base_url: '', verify_ssl: true, is_active: true,
  }
  const [form, setForm] = useState(
    isNew ? blank : {
      name: panel.name || '', base_url: panel.base_url || '',
      admin_username: panel.admin_username || '', admin_password: '',
      subscription_base_url: panel.subscription_base_url || '',
      verify_ssl: panel.verify_ssl ?? true, is_active: panel.is_active ?? true,
    },
  )
  const [selected, setSelected] = useState(panel?.default_group_ids || [])
  const [groups, setGroups] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const toggleGroup = (id) =>
    setSelected((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))

  const groupRows = useMemo(() => {
    if (!groups) return null
    const byId = new Map(groups.map((g) => [g.id, g.name]))
    selected.forEach((id) => { if (!byId.has(id)) byId.set(id, `${s.group_word} ${id}`) })
    return [...byId.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.id - b.id)
  }, [groups, selected, s.group_word])

  const fetchGroups = async () => {
    setFetching(true); setMsg(null)
    try {
      const r = await api.get(`/admin/panels/${panel.id}/groups/`)
      setGroups(r.data.groups || [])
    } catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
    finally { setFetching(false) }
  }

  const test = async () => {
    setTesting(true); setMsg(null)
    try {
      const r = await api.post(`/admin/panels/${panel.id}/test/`)
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
    } catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
    finally { setTesting(false) }
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true); setMsg(null)
    const body = { ...form, default_group_ids: selected }
    if (!body.admin_password) delete body.admin_password
    try {
      if (isNew) await api.post('/admin/panels/', body)
      else await api.patch(`/admin/panels/${panel.id}/`, body)
      onSaved?.()
      if (!isNew) setMsg({ kind: 'success', text: s.saved })
    } catch (e2) { setMsg({ kind: 'danger', text: apiError(e2) }) }
    finally { setSaving(false) }
  }

  const del = async () => {
    if (!confirm(s.confirm_del)) return
    try { await api.delete(`/admin/panels/${panel.id}/`); onDeleted?.() }
    catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
  }

  const inUse = !isNew && (panel.plan_count > 0 || panel.service_count > 0)

  return (
    <form onSubmit={save} className="card grid gap-4 sm:grid-cols-2">
      <div className="flex flex-wrap items-center justify-between gap-2 sm:col-span-2">
        <span className="int-card-head font-bold">
          <span className="int-card-ico"><Ico d={ICONS.link} w={16} /></span>
          {isNew ? s.new_panel : (form.name || panel.name)}
        </span>
        {!isNew && (
          <span className="text-xs text-muted">
            {panel.plan_count} {s.in_use} · {panel.service_count} {s.in_use2}
          </span>
        )}
      </div>

      {msg && <div className="sm:col-span-2"><Alert kind={msg.kind}>{msg.text}</Alert></div>}

      <Field label={s.panel_name}>
        <input className="input" required placeholder="Wireguard / Unlimited / Volume"
          value={form.name} onChange={(e) => set('name', e.target.value)} />
      </Field>
      <Field label={s.base_url}>
        <input className="input" dir="ltr" required placeholder="https://panel.example.com"
          value={form.base_url} onChange={(e) => set('base_url', e.target.value)} />
      </Field>
      <Field label={s.admin_user}>
        <input className="input" dir="ltr" required
          value={form.admin_username} onChange={(e) => set('admin_username', e.target.value)} />
      </Field>
      <Field label={s.admin_pass}>
        <SecretInput
          placeholder={!isNew && panel.admin_password_set ? s.unchanged : ''}
          value={form.admin_password} onChange={(e) => set('admin_password', e.target.value)} />
        <span className="mt-1 block text-xs text-muted">
          {!isNew && panel.admin_password_set ? s.pass_stored : s.pass_none}
        </span>
      </Field>
      <Field label={s.sub_url}>
        <input className="input" dir="ltr"
          value={form.subscription_base_url} onChange={(e) => set('subscription_base_url', e.target.value)} />
      </Field>

      <label className="flex items-center gap-2 self-end text-sm">
        <Toggle checked={form.verify_ssl} onChange={(v) => set('verify_ssl', v)} label={s.verify_ssl} />
        {s.verify_ssl}
      </label>

      {/* ---- this panel's default groups ---- */}
      <div className="sm:col-span-2">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="label mb-0">{s.groups}</span>
          {!isNew && (
            <button type="button" className="btn-ghost text-xs" onClick={fetchGroups} disabled={fetching}>
              {fetching ? s.fetching : `⭳ ${s.fetch_groups}`}
            </button>
          )}
        </div>
        <p className="mb-2 text-xs text-muted">{s.groups_hint}</p>

        {isNew ? (
          <p className="text-xs text-muted">{s.groups_none_fetched.split('.')[0]}.</p>
        ) : !groupRows ? (
          <p className="text-sm">
            {s.groups_none_fetched}{' '}
            <span dir="ltr" className="font-mono">
              {selected.length ? selected.join(', ') : s.groups_empty}
            </span>
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {groupRows.map((g) => (
              <label key={g.id} className="flex items-center gap-2 rounded-xl border px-3 py-2 text-sm"
                style={{ borderColor: 'var(--c-border)' }}>
                <input type="checkbox" checked={selected.includes(g.id)} onChange={() => toggleGroup(g.id)} />
                <span className="truncate">{g.name}</span>
                <span dir="ltr" className="ms-auto shrink-0 text-xs text-muted">#{g.id}</span>
              </label>
            ))}
            {groupRows.length === 0 && <p className="text-sm text-muted">—</p>}
          </div>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <Toggle checked={form.is_active} onChange={(v) => set('is_active', v)} label={s.panel_active} />
        {s.panel_active}
      </label>

      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <button className="btn-primary text-sm" disabled={saving}>{saving ? '…' : s.save}</button>
        {!isNew && (
          <button type="button" className="btn-ghost text-sm" onClick={test} disabled={testing}>
            {testing ? '…' : s.test}
          </button>
        )}
        {isNew && (
          <button type="button" className="btn-ghost text-sm" onClick={onCancel}>{t('cancel')}</button>
        )}
        {!isNew && !inUse && (
          <button type="button" className="btn-ghost ms-auto text-sm inline-flex items-center gap-1.5"
            style={{ color: 'var(--c-danger)' }} onClick={del}><Ico d={ICONS.trash} w={14} /> {s.del_panel}</button>
        )}
      </div>
    </form>
  )
}

function EmailCard({ s }) {
  const [st, setSt] = useState(null)
  const [to, setTo] = useState('')
  const [sending, setSending] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.get('/admin/integrations/email/').then((r) => setSt(r.data)).catch(() => setSt({ error: true }))
  }, [])

  const sendTest = async () => {
    setSending(true); setMsg(null)
    try {
      const r = await api.post('/admin/integrations/email/', { to })
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
    } catch (e) {
      setMsg({ kind: 'danger', text: apiError(e) })
    } finally { setSending(false) }
  }

  if (!st) return <div className="card"><Spinner /></div>
  if (st.error) return null

  const dot = (ok) => (
    <span className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ background: ok ? 'var(--c-success)' : 'var(--c-danger)' }} />
  )

  return (
    <div className="card space-y-3">
      <div className="font-bold">{s.email_title}</div>

      <div className="space-y-1.5 text-sm">
        <div className="flex items-center gap-2">
          {dot(st.external_delivery_ready)}
          <span>{st.external_delivery_ready ? s.email_ready : s.email_not_ready}</span>
        </div>
        <div className="flex items-center gap-2">
          {dot(st.relay_configured)}
          <span className="text-muted">
            {st.relay_configured ? `${s.email_relay_on} — ${st.relay_host}` : s.email_relay_off}
          </span>
        </div>
        <div className="text-xs text-muted">
          {s.email_host}: <span dir="ltr">{st.host || '—'}:{st.port}</span> · {s.email_from}: <span dir="ltr">{st.from_address}</span>
        </div>
        <div className="text-xs text-muted">
          {st.verification_required ? s.email_verif_on : s.email_verif_off}
        </div>
        <p className="text-xs text-muted">{s.email_relay_hint}</p>
      </div>

      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1" style={{ minWidth: '12rem' }}>
          <Field label={s.email_test_to}>
            <input className="input" dir="ltr" type="email" placeholder="you@example.com"
              value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
        <button type="button" className="btn-ghost text-sm" onClick={sendTest} disabled={sending || !to}>
          {sending ? '…' : s.email_send_test}
        </button>
      </div>
    </div>
  )
}

/* ================================================================== *
 *  Telegram Bots  —  /panel/bots                                     *
 * ================================================================== */
export function Bots() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [data, setData] = useState(null)
  const [sales, setSales] = useState(null)
  const [backup, setBackup] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState('')

  const hydrate = (row) => ({
    token: '',
    proxy_url: row.proxy_url || '',
    backup_chat_id: row.backup_chat_id ?? '',
    is_active: row.is_active ?? false,
  })

  const load = () =>
    api.get('/admin/integrations/telegram/').then((r) => {
      setData(r.data)
      setSales(hydrate(r.data.sales))
      setBackup(hydrate(r.data.backup))
    }).catch(() => setData({ error: true }))

  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault()
    setErr(''); setMsg(null)
    const clean = (o, isBackup) => {
      const body = { proxy_url: o.proxy_url || null, is_active: o.is_active }
      if (o.token) body.token = o.token
      if (isBackup) body.backup_chat_id = o.backup_chat_id === '' ? null : Number(o.backup_chat_id)
      return body
    }
    try {
      await api.put('/admin/integrations/telegram/', {
        sales: clean(sales, false),
        backup: clean(backup, true),
      })
      setMsg({ kind: 'success', text: s.bots_saved })
      load()
    } catch (e2) { setErr(apiError(e2)) }
  }

  if (!data) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <style>{INT_CSS}</style>
      <div className="int-head">
        <span className="int-head-ico"><Ico d={ICONS.bot} w={20} /></span>
        <div>
          <h1 className="text-lg font-bold">{t('bots')}</h1>
          <p className="mt-1 text-sm text-muted">{s.bots_intro}</p>
        </div>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <form onSubmit={save} className="space-y-4">
        {sales && <BotCard title={s.sales_bot} icon={ICONS.cart} row={data.sales} value={sales} onChange={setSales} s={s} />}
        {backup && <BotCard title={s.backup_bot} icon={ICONS.backup} row={data.backup} value={backup} onChange={setBackup} s={s} showChatId />}
        <button className="btn-primary text-sm">{s.save}</button>
      </form>

      <RequiredChannels s={s} />
    </div>
  )
}

/* ================================================================== *
 *  Forced-join channels  —  on the Bots page                         *
 * ================================================================== */
function RequiredChannels({ s }) {
  const { lang } = useI18n()
  const blank = { channel_id: '', title: '', invite_link: '', is_active: true }
  const [rows, setRows] = useState(null)
  const [enf, setEnf] = useState({ force_channel_join: false, force_share_phone: false })
  const [edit, setEdit] = useState(null)          // {channel...} | null
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState(null)
  const [testing, setTesting] = useState(null)    // channel id being tested

  const load = () =>
    api.get('/admin/channels/').then((r) => {
      setRows(r.data.results || [])
      setEnf(r.data.enforcement || {})
    }).catch((e) => { setRows([]); setMsg({ kind: 'danger', text: apiError(e) }) })
  useEffect(() => { load() }, [])

  const setToggle = async (k, v) => {
    setEnf((c) => ({ ...c, [k]: v }))
    try { await api.patch('/admin/channels/enforcement/', { [k]: v }) }
    catch (e) { setMsg({ kind: 'danger', text: apiError(e) }); load() }
  }

  const saveChannel = async (e) => {
    e.preventDefault(); setMsg(null)
    const body = { ...edit }
    try {
      if (edit.id) await api.patch(`/admin/channels/${edit.id}/`, body)
      else await api.post('/admin/channels/', body)
      setEdit(null); setAdding(false); load()
    } catch (e2) { setMsg({ kind: 'danger', text: apiError(e2) }) }
  }

  const del = async (id) => {
    if (!confirm(s.ch_confirm_del)) return
    try { await api.delete(`/admin/channels/${id}/`); load() }
    catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
  }

  const test = async (id) => {
    setTesting(id); setMsg(null)
    try {
      const r = await api.post(`/admin/channels/${id}/test/`)
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
      load()
    } catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
    finally { setTesting(null) }
  }

  if (!rows) return <div className="card"><Spinner /></div>

  const Form = ({ value, onChange, onSubmit, onCancel }) => (
    <form onSubmit={onSubmit} className="card grid gap-3 sm:grid-cols-2"
      style={{ background: 'color-mix(in srgb, var(--c-primary) 5%, var(--c-surface))' }}>
      <Field label={s.ch_id}>
        <input className="input" dir="ltr" required placeholder="@mychannel  یا  -1001234567890"
          value={value.channel_id} onChange={(e) => onChange({ ...value, channel_id: e.target.value })} />
      </Field>
      <Field label={s.ch_title}>
        <input className="input" value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })} />
      </Field>
      <div className="sm:col-span-2">
        <Field label={s.ch_invite}>
          <input className="input" dir="ltr" placeholder="https://t.me/+AbC..."
            value={value.invite_link} onChange={(e) => onChange({ ...value, invite_link: e.target.value })} />
        </Field>
        <p className="mt-1 text-xs text-muted">{s.ch_invite_hint}</p>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Toggle checked={value.is_active} onChange={(v) => onChange({ ...value, is_active: v })} label={s.active} />
        {s.active}
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <button className="btn-primary text-sm">{s.save}</button>
        <button type="button" className="btn-ghost text-sm" onClick={onCancel}>{s.ch_cancel}</button>
      </div>
    </form>
  )

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-bold">{s.ch_title_h}</h2>
          <p className="mt-1 text-sm text-muted">{s.ch_intro}</p>
        </div>
        {!adding && !edit && (
          <button className="btn-primary shrink-0 text-sm" onClick={() => { setAdding(true); setEdit({ ...blank }) }}>
            + {s.ch_add}
          </button>
        )}
      </div>

      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      {/* enforcement toggles */}
      <div className="card">
        <div className="toggle-row">
          <span className="text-sm">{s.force_join}</span>
          <Toggle checked={!!enf.force_channel_join}
            onChange={(v) => setToggle('force_channel_join', v)} label={s.force_join} />
        </div>
        <div className="toggle-row">
          <span className="text-sm">{s.force_phone}</span>
          <Toggle checked={!!enf.force_share_phone}
            onChange={(v) => setToggle('force_share_phone', v)} label={s.force_phone} />
        </div>
      </div>

      <div className="rounded-xl p-3 text-xs" style={{ background: 'color-mix(in srgb, var(--c-warning) 12%, transparent)', color: 'var(--c-warning)' }}>
        ⚠️ {s.ch_admin_hint}
      </div>

      {adding && <Form value={edit} onChange={setEdit} onSubmit={saveChannel}
        onCancel={() => { setAdding(false); setEdit(null) }} />}

      {rows.length === 0 && !adding && (
        <div className="card text-center text-sm text-muted">{s.ch_none}</div>
      )}

      {rows.map((c) => (
        edit && edit.id === c.id ? (
          <Form key={c.id} value={edit} onChange={setEdit} onSubmit={saveChannel}
            onCancel={() => setEdit(null)} />
        ) : (
          <div key={c.id} className="card flex flex-wrap items-center gap-3">
            <span className={'shrink-0 rounded-full px-2 py-0.5 text-xs ' + (c.is_active ? '' : 'opacity-60')}
              style={{ background: c.is_active ? 'color-mix(in srgb, var(--c-success) 16%, transparent)' : 'var(--c-border)',
                color: c.is_active ? 'var(--c-success)' : 'var(--c-text-muted)' }}>
              {c.is_active ? s.active : s.inactive}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-bold">{c.title || c.channel_id}</div>
              <div dir="ltr" className="truncate text-xs text-muted">{c.channel_id}</div>
            </div>
            <div className="text-xs text-muted">
              {s.ch_members}: {c.member_count ?? 0}
              {c.last_synced_at ? ` · ${new Date(c.last_synced_at).toLocaleDateString(lang === 'fa' ? 'fa-IR' : 'en-GB')}` : ''}
            </div>
            <div className="flex gap-1">
              <button className="btn-ghost text-xs" onClick={() => test(c.id)} disabled={testing === c.id}>
                {testing === c.id ? '…' : s.ch_test}
              </button>
              <button className="int-icon-btn" title={s.save} onClick={() => { setEdit({ ...c }); setAdding(false) }}><Ico d={ICONS.edit} w={15} /></button>
              <button className="int-icon-btn int-icon-btn--del" onClick={() => del(c.id)}><Ico d={ICONS.trash} w={15} /></button>
            </div>
          </div>
        )
      ))}
    </div>
  )
}

function BotCard({ title, icon, row, value, onChange, s, showChatId }) {
  const set = (k, v) => onChange({ ...value, [k]: v })
  return (
    <div className="card grid gap-4 sm:grid-cols-2">
      <div className="flex items-center justify-between sm:col-span-2">
        <span className="int-card-head font-bold">
          <span className="int-card-ico"><Ico d={icon || ICONS.bot} w={16} /></span>{title}
        </span>
        <label className="flex items-center gap-2 text-sm">
          <Toggle checked={value.is_active} onChange={(v) => set('is_active', v)} label={s.active} />
          {s.active}
        </label>
      </div>

      <Field label={s.bot_token}>
        <SecretInput placeholder={row.token_set ? s.unchanged : '123456:ABC-DEF…'}
          value={value.token} onChange={(e) => set('token', e.target.value)} />
        <span className="mt-1 block text-xs text-muted">
          {row.token_set ? s.token_stored : s.token_none}
        </span>
      </Field>

      <Field label={s.proxy}>
        <input className="input" dir="ltr" placeholder="socks5://user:pass@host:port"
          value={value.proxy_url} onChange={(e) => set('proxy_url', e.target.value)} />
      </Field>

      {showChatId && (
        <Field label={s.chat_id}>
          <input className="input" dir="ltr" inputMode="numeric" placeholder="-1001234567890"
            value={value.backup_chat_id} onChange={(e) => set('backup_chat_id', e.target.value)} />
          <span className="mt-1 block text-xs text-muted">{s.chat_hint}</span>
        </Field>
      )}
    </div>
  )
}
