import { useEffect, useMemo, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Field, Spinner } from '../components/ui'

const T = {
  fa: {
    panel_intro: 'اطلاعات ورود پنل پاسارگارد را اینجا وارد کنید. رمز عبور رمزنگاری‌شده ذخیره می‌شود و دیگر نمایش داده نمی‌شود.',
    base_url: 'آدرس پایه پنل (Base URL)', admin_user: 'نام کاربری ادمین پنل',
    admin_pass: 'رمز عبور ادمین پنل', sub_url: 'آدرس پایهٔ اشتراک (اختیاری)',
    verify_ssl: 'بررسی گواهی SSL پنل', panel_active: 'این پنل فعال است',
    unchanged: '•••••••• (بدون تغییر)',
    pass_stored: 'رمزی ذخیره شده است؛ برای تغییر، رمز جدید را وارد کنید.',
    pass_none: 'هنوز رمزی ذخیره نشده است.',
    saved: 'ذخیره شد.', save: 'ذخیره', test: 'تست اتصال',
    groups: 'گروه‌های پیش‌فرض پنل', fetch_groups: 'دریافت گروه‌ها از پنل',
    fetching: 'در حال دریافت…',
    groups_hint: 'وقتی یک پلن گروهی تعیین نکند، این گروه‌ها استفاده می‌شوند.',
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
  },
  en: {
    panel_intro: 'Enter the Pasargad panel admin login here. The password is stored encrypted and never shown again.',
    base_url: 'Panel Base URL', admin_user: 'Panel admin username',
    admin_pass: 'Panel admin password', sub_url: 'Subscription base URL (optional)',
    verify_ssl: 'Verify panel SSL certificate', panel_active: 'Panel is active',
    unchanged: '•••••••• (unchanged)',
    pass_stored: 'A password is stored; type a new one only to change it.',
    pass_none: 'No password stored yet.',
    saved: 'Saved.', save: 'Save', test: 'Test connection',
    groups: 'Default panel groups', fetch_groups: 'Fetch groups from panel',
    fetching: 'Fetching…',
    groups_hint: 'Used whenever a plan does not set its own groups.',
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
  },
}

/* ================================================================== *
 *  Pasargad Panel  —  /panel/panel-link                              *
 * ================================================================== */
export function PanelConnection() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [cfg, setCfg] = useState(null)
  const [form, setForm] = useState(null)
  const [selected, setSelected] = useState([])       // chosen group ids
  const [groups, setGroups] = useState(null)         // [{id,name}] once fetched
  const [fetching, setFetching] = useState(false)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState('')
  const [testing, setTesting] = useState(false)

  const load = () =>
    api.get('/admin/integrations/panel/').then((r) => {
      setCfg(r.data)
      setSelected(r.data.default_group_ids || [])
      setForm({
        base_url: r.data.base_url || '',
        admin_username: r.data.admin_username || '',
        admin_password: '',
        subscription_base_url: r.data.subscription_base_url || '',
        verify_ssl: r.data.verify_ssl ?? true,
        is_active: r.data.is_active ?? true,
      })
    }).catch(() => setCfg({ error: true }))

  useEffect(() => { load() }, [])

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const toggleGroup = (id) =>
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))

  // union of fetched groups + any saved id the panel didn't return
  const groupRows = useMemo(() => {
    if (!groups) return null
    const byId = new Map(groups.map((g) => [g.id, g.name]))
    selected.forEach((id) => { if (!byId.has(id)) byId.set(id, `${s.group_word} ${id}`) })
    return [...byId.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.id - b.id)
  }, [groups, selected, s.group_word])

  const fetchGroups = async () => {
    setFetching(true); setErr(''); setMsg(null)
    try {
      const r = await api.get('/admin/integrations/panel/groups/')
      setGroups(r.data.groups || [])
    } catch (e2) {
      setMsg({ kind: 'danger', text: apiError(e2) })
    } finally { setFetching(false) }
  }

  const save = async (e) => {
    e.preventDefault()
    setErr(''); setMsg(null)
    const body = { ...form, default_group_ids: selected }
    if (!body.admin_password) delete body.admin_password
    try {
      await api.put('/admin/integrations/panel/', body)
      setMsg({ kind: 'success', text: s.saved })
      load()
    } catch (e2) { setErr(apiError(e2)) }
  }

  const test = async () => {
    setTesting(true); setErr(''); setMsg(null)
    try {
      const r = await api.post('/admin/integrations/panel/test/')
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
    } catch (e2) {
      setMsg({ kind: 'danger', text: apiError(e2) })
    } finally { setTesting(false) }
  }

  if (!cfg) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">{t('panel_link')}</h1>
        <p className="mt-1 text-sm text-muted">{s.panel_intro}</p>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <form onSubmit={save} className="card grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label={s.base_url}>
            <input className="input" dir="ltr" placeholder="https://panel.example.com" required
              value={form.base_url} onChange={(e) => set('base_url', e.target.value)} />
          </Field>
        </div>
        <Field label={s.admin_user}>
          <input className="input" dir="ltr" required
            value={form.admin_username} onChange={(e) => set('admin_username', e.target.value)} />
        </Field>
        <Field label={s.admin_pass}>
          <input className="input" dir="ltr" type="password" autoComplete="new-password"
            placeholder={cfg.admin_password_set ? s.unchanged : ''}
            value={form.admin_password} onChange={(e) => set('admin_password', e.target.value)} />
          <span className="mt-1 block text-xs text-muted">
            {cfg.admin_password_set ? s.pass_stored : s.pass_none}
          </span>
        </Field>
        <Field label={s.sub_url}>
          <input className="input" dir="ltr"
            value={form.subscription_base_url} onChange={(e) => set('subscription_base_url', e.target.value)} />
        </Field>

        {/* ---- panel groups: fetch-and-pick ---- */}
        <div className="sm:col-span-2">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="label mb-0">{s.groups}</span>
            <button type="button" className="btn-ghost text-xs" onClick={fetchGroups} disabled={fetching}>
              {fetching ? s.fetching : `⭳ ${s.fetch_groups}`}
            </button>
          </div>
          <p className="mb-2 text-xs text-muted">{s.groups_hint}</p>

          {!groupRows && (
            <p className="text-sm">
              {s.groups_none_fetched}{' '}
              <span dir="ltr" className="font-mono">
                {selected.length ? selected.join(', ') : s.groups_empty}
              </span>
            </p>
          )}

          {groupRows && (
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

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.verify_ssl}
            onChange={(e) => set('verify_ssl', e.target.checked)} />
          {s.verify_ssl}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.is_active}
            onChange={(e) => set('is_active', e.target.checked)} />
          {s.panel_active}
        </label>

        <div className="flex flex-wrap gap-2 sm:col-span-2">
          <button className="btn-primary text-sm">{s.save}</button>
          <button type="button" className="btn-ghost text-sm" onClick={test} disabled={testing}>
            {testing ? '…' : s.test}
          </button>
        </div>
      </form>

      <EmailCard s={s} />
    </div>
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
      <div>
        <h1 className="text-lg font-bold">{t('bots')}</h1>
        <p className="mt-1 text-sm text-muted">{s.bots_intro}</p>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <form onSubmit={save} className="space-y-4">
        {sales && <BotCard title={s.sales_bot} row={data.sales} value={sales} onChange={setSales} s={s} />}
        {backup && <BotCard title={s.backup_bot} row={data.backup} value={backup} onChange={setBackup} s={s} showChatId />}
        <button className="btn-primary text-sm">{s.save}</button>
      </form>
    </div>
  )
}

function BotCard({ title, row, value, onChange, s, showChatId }) {
  const set = (k, v) => onChange({ ...value, [k]: v })
  return (
    <div className="card grid gap-4 sm:grid-cols-2">
      <div className="flex items-center justify-between sm:col-span-2">
        <span className="font-bold">{title}</span>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={value.is_active}
            onChange={(e) => set('is_active', e.target.checked)} />
          {s.active}
        </label>
      </div>

      <Field label={s.bot_token}>
        <input className="input" dir="ltr" type="password" autoComplete="new-password"
          placeholder={row.token_set ? s.unchanged : '123456:ABC-DEF…'}
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
