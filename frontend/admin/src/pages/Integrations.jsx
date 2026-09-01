import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Field, Spinner } from '../components/ui'

/* ------------------------------------------------------------------ *
 *  Pasargad Panel  —  /panel/#/panel-link                            *
 * ------------------------------------------------------------------ */
export function PanelConnection() {
  const { t, lang } = useI18n()
  const [cfg, setCfg] = useState(null)
  const [form, setForm] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState('')
  const [testing, setTesting] = useState(false)

  const load = () =>
    api.get('/admin/integrations/panel/').then((r) => {
      setCfg(r.data)
      setForm({
        base_url: r.data.base_url || '',
        admin_username: r.data.admin_username || '',
        admin_password: '',
        subscription_base_url: r.data.subscription_base_url || '',
        verify_ssl: r.data.verify_ssl ?? true,
        default_group_ids: (r.data.default_group_ids || []).join(', '),
        is_active: r.data.is_active ?? true,
      })
    }).catch(() => setCfg({ error: true }))

  useEffect(() => { load() }, [])

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async (e) => {
    e.preventDefault()
    setErr(''); setMsg(null)
    const body = {
      ...form,
      default_group_ids: form.default_group_ids
        .split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !Number.isNaN(n)),
    }
    if (!body.admin_password) delete body.admin_password
    try {
      await api.put('/admin/integrations/panel/', body)
      setMsg({ kind: 'success', text: 'ذخیره شد.' })
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
        <p className="mt-1 text-sm text-muted">
          {lang === 'fa'
            ? 'اطلاعات ورود پنل پاسارگارد را اینجا وارد کنید. رمز عبور رمزنگاری‌شده ذخیره می‌شود و دیگر نمایش داده نمی‌شود.'
            : 'Enter the Pasargad panel admin login here. The password is stored encrypted and never shown again.'}
        </p>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <form onSubmit={save} className="card grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label={lang === 'fa' ? 'آدرس پایه پنل (Base URL)' : 'Panel Base URL'}>
            <input className="input" dir="ltr" placeholder="https://panel.example.com" required
              value={form.base_url} onChange={(e) => set('base_url', e.target.value)} />
          </Field>
        </div>
        <Field label={lang === 'fa' ? 'نام کاربری ادمین پنل' : 'Panel admin username'}>
          <input className="input" dir="ltr" required
            value={form.admin_username} onChange={(e) => set('admin_username', e.target.value)} />
        </Field>
        <Field label={lang === 'fa' ? 'رمز عبور ادمین پنل' : 'Panel admin password'}>
          <input className="input" dir="ltr" type="password" autoComplete="new-password"
            placeholder={cfg.admin_password_set ? '•••••••• (بدون تغییر)' : ''}
            value={form.admin_password} onChange={(e) => set('admin_password', e.target.value)} />
          <span className="mt-1 block text-xs text-muted">
            {cfg.admin_password_set
              ? (lang === 'fa' ? 'رمزی ذخیره شده است؛ برای تغییر، رمز جدید را وارد کنید.'
                               : 'A password is stored; type a new one only to change it.')
              : (lang === 'fa' ? 'هنوز رمزی ذخیره نشده است.' : 'No password stored yet.')}
          </span>
        </Field>
        <Field label={lang === 'fa' ? 'آدرس پایهٔ اشتراک (اختیاری)' : 'Subscription base URL (optional)'}>
          <input className="input" dir="ltr"
            value={form.subscription_base_url} onChange={(e) => set('subscription_base_url', e.target.value)} />
        </Field>
        <Field label={lang === 'fa' ? 'گروه‌های پیش‌فرض پنل (با کاما)' : 'Default panel group ids (comma-separated)'}>
          <input className="input" dir="ltr" placeholder="5, 6, 8, 10"
            value={form.default_group_ids} onChange={(e) => set('default_group_ids', e.target.value)} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.verify_ssl}
            onChange={(e) => set('verify_ssl', e.target.checked)} />
          {lang === 'fa' ? 'بررسی گواهی SSL پنل' : 'Verify panel SSL certificate'}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.is_active}
            onChange={(e) => set('is_active', e.target.checked)} />
          {lang === 'fa' ? 'این پنل فعال است' : 'Panel is active'}
        </label>

        <div className="flex gap-2 sm:col-span-2">
          <button className="btn-primary text-sm">{t('save')}</button>
          <button type="button" className="btn-ghost text-sm" onClick={test} disabled={testing}>
            {testing ? '…' : t('test_connection')}
          </button>
        </div>
      </form>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 *  Telegram Bots  —  /panel/#/bots                                   *
 * ------------------------------------------------------------------ */
export function Bots() {
  const { t, lang } = useI18n()
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
      setMsg({ kind: 'success', text: lang === 'fa'
        ? 'ذخیره شد. برای اعمال توکن جدید، کانتینر ربات ظرف یک دقیقه به‌روز می‌شود (در صورت نیاز ری‌استارت کنید).'
        : 'Saved. The bot container picks up a new token within a minute (restart it if needed).' })
      load()
    } catch (e2) { setErr(apiError(e2)) }
  }

  if (!data) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">{t('bots')}</h1>
        <p className="mt-1 text-sm text-muted">
          {lang === 'fa'
            ? 'هر ربات توکن جداگانه دارد. توکن‌ها رمزنگاری‌شده ذخیره می‌شوند و نمایش داده نمی‌شوند.'
            : 'Each bot has its own token. Tokens are stored encrypted and never shown.'}
        </p>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <form onSubmit={save} className="space-y-4">
        {sales && (
          <BotCard
            title={lang === 'fa' ? 'ربات فروش' : 'Sales bot'}
            row={data.sales} value={sales} onChange={setSales} lang={lang}
          />
        )}
        {backup && (
          <BotCard
            title={lang === 'fa' ? 'ربات بک‌آپ' : 'Backup bot'}
            row={data.backup} value={backup} onChange={setBackup} lang={lang} showChatId
          />
        )}
        <button className="btn-primary text-sm">{t('save')}</button>
      </form>
    </div>
  )
}

function BotCard({ title, row, value, onChange, lang, showChatId }) {
  const set = (k, v) => onChange({ ...value, [k]: v })
  return (
    <div className="card grid gap-4 sm:grid-cols-2">
      <div className="flex items-center justify-between sm:col-span-2">
        <span className="font-bold">{title}</span>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={value.is_active}
            onChange={(e) => set('is_active', e.target.checked)} />
          {lang === 'fa' ? 'فعال' : 'Active'}
        </label>
      </div>

      <Field label={lang === 'fa' ? 'توکن ربات (BotFather)' : 'Bot token (BotFather)'}>
        <input className="input" dir="ltr" type="password" autoComplete="new-password"
          placeholder={row.token_set ? '•••••••• (بدون تغییر)' : '123456:ABC-DEF…'}
          value={value.token} onChange={(e) => set('token', e.target.value)} />
        <span className="mt-1 block text-xs text-muted">
          {row.token_set
            ? (lang === 'fa' ? 'توکنی ذخیره شده است؛ برای تغییر، توکن جدید را وارد کنید.'
                             : 'A token is stored; type a new one only to change it.')
            : (lang === 'fa' ? 'هنوز توکنی ذخیره نشده است.' : 'No token stored yet.')}
        </span>
      </Field>

      <Field label={lang === 'fa' ? 'پروکسی (اختیاری)' : 'Proxy (optional)'}>
        <input className="input" dir="ltr" placeholder="socks5://user:pass@host:port"
          value={value.proxy_url} onChange={(e) => set('proxy_url', e.target.value)} />
      </Field>

      {showChatId && (
        <Field label={lang === 'fa' ? 'شناسهٔ چت بک‌آپ (chat_id)' : 'Backup chat_id'}>
          <input className="input" dir="ltr" inputMode="numeric" placeholder="-1001234567890"
            value={value.backup_chat_id} onChange={(e) => set('backup_chat_id', e.target.value)} />
          <span className="mt-1 block text-xs text-muted">
            {lang === 'fa'
              ? 'فایل‌های پشتیبان به این چت ارسال می‌شوند. برای گرفتن شناسه، در آن چت به ربات بک‌آپ /id بفرستید.'
              : 'Backups are sent to this chat. Send /id to the backup bot there to get the id.'}
          </span>
        </Field>
      )}
    </div>
  )
}
