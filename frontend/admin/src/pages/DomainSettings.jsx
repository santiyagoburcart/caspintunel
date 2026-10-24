import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali } from '../lib/format'
import { Alert, Spinner, Toggle, Copyable } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'
import { Why, yn } from '../components/DomainWhy'
import AccessMode from './DomainAccess'
import { useToast } from '../components/Toast'

// /settings/domain — Cloudflare token + the domain-change wizard (docs/domain.md).
// Django does DNS (Cloudflare API or manual) and the DNS check; certificate,
// nginx, .env and containers are switched by the host watcher
// (scripts/domain.sh, within a minute) with automatic rollback.

const T = {
  fa: {
    ax_mode: 'حالت دسترسی', ax_modes: { direct: 'مستقیم', cloudflare: 'پروکسی Cloudflare', tunnel: 'تونل ایران' },
    title: 'دامنه و Cloudflare', sub: 'توکن Cloudflare و تغییر امن دامنهٔ سایت، مرحله به مرحله',
    current: 'دامنهٔ فعلی', ip: 'IP این سرور', only_super: 'فقط مدیر کل به این صفحه دسترسی دارد.',
    cf: 'توکن API کلادفلر', cf_hint: 'رمزنگاری‌شده در پایگاه‌داده ذخیره می‌شود و دیگر نمایش داده نمی‌شود. اگر خالی باشد، مقدار .env استفاده می‌شود.',
    src_panel: 'ذخیره‌شده در پنل', src_env: 'از فایل .env', src_none: 'تنظیم نشده', new_token: 'توکن جدید',
    save: 'ذخیره', test: 'آزمایش', remove: 'حذف توکن', by: 'توسط', zones: 'زون‌ها', perms: 'دسترسی‌ها',
    dns_edit: 'ویرایش DNS', no_edit: 'بدون ویرایش DNS', unknown: 'نامشخص', token_ok: 'توکن معتبر است',
    trans: 'مدت نگه‌داری دامنهٔ قبلی', trans_hint: 'دامنهٔ قبلی این تعداد روز با ریدایرکت 301 به دامنهٔ جدید کار می‌کند و سپس حذف می‌شود (۰ = بلافاصله).', days: 'روز',
    wizard: 'تغییر دامنه', new_domain: 'دامنهٔ جدید', www: 'www هم فعال باشد', dns_mode: 'مدیریت DNS',
    manual: 'دستی (پنل DNS دیگر)', pick_zone: 'زون Cloudflare', zone_auto: 'خودکار از روی دامنه', start: 'شروع',
    test_first: 'برای انتخاب زون، اول توکن را آزمایش کنید (یا DNS دستی را انتخاب کنید).',
    steps: { domain: 'دامنهٔ جدید', dns: 'رکوردهای DNS', tls: 'گواهی TLS و کلید DKIM', mail: 'ایمیل (MX، SPF، DKIM، DMARC)', apply: 'اعمال روی سرور', links: 'لینک‌ها و ربات', transition: 'دورهٔ گذار', rollback: 'بازگشت' },
    st: { ok: 'انجام شد', running: 'در حال انجام…', waiting: 'در انتظار', failed: 'ناموفق', pending: 'مانده', skipped: 'رد شد' },
    status: { draft: 'در حال آماده‌سازی', applying: 'در حال اعمال', transition: 'دورهٔ گذار', done: 'تمام', failed: 'ناموفق', rolled_back: 'برگشت داده شد', cancelled: 'لغو شد' },
    create_records: 'ساخت رکوردها در Cloudflare', check_dns: 'بررسی DNS', request_cert: 'درخواست گواهی',
    apply: 'انتقال به دامنهٔ جدید', retire: 'حذف دامنهٔ قبلی همین حالا', cancel: 'لغو',
    mail_recs: 'رکوردهای ایمیل', mail_hint: 'ایمیل همراه دامنه منتقل می‌شود: سرور ایمیل با نام mail.<دامنهٔ جدید>، گواهی و کلید DKIM خودش. این رکوردها را در پنل DNS بسازید (TXTهای دیگر را دست نزنید)، سپس «بررسی DNS ایمیل».',
    publish_mail: 'ثبت رکوردهای ایمیل در Cloudflare', check_mail: 'بررسی DNS ایمیل', prio: 'اولویت',
    records: 'رکوردهای لازم', manual_hint: 'این رکوردها را در پنل DNS دامنه بسازید (بدون پروکسی)، سپس «بررسی DNS» را بزنید.',
    rec_type: 'نوع', rec_name: 'نام', rec_value: 'مقدار', optional: 'اختیاری (ایمیل)', resolves: 'پاسخ DNS عمومی',
    queued: 'در صف سرور — حداکثر تا یک دقیقه انجام می‌شود…', host_last: 'آخرین نتیجهٔ سرور',
    apply_t: 'انتقال سایت به دامنهٔ جدید', apply_m: 'nginx، ALLOWED_HOSTS، CSRF، آدرس سایت، لینک‌ها، سرور ایمیل (mail.<دامنهٔ جدید> و فرستنده) و دکمهٔ مینی‌اپ ربات به دامنهٔ جدید منتقل می‌شوند. سرویس‌های برنامه بدون قطعی بازنشانی می‌شوند. در صورت هر خطا همه‌چیز خودکار برمی‌گردد.',
    old_redirects: 'دامنهٔ قبلی با 301 به دامنهٔ جدید هدایت می‌شود تا', retire_t: 'حذف دامنهٔ قبلی', retire_m: 'دامنهٔ قبلی دیگر سرو نمی‌شود و ریدایرکت آن حذف می‌شود.',
    rollback: 'بازگشت به دامنهٔ قبلی', rollback_t: 'بازگشت دامنه', rollback_m: 'سایت دوباره روی دامنهٔ قبلی می‌رود و دامنهٔ فعلی دیگر سرو نمی‌شود. گواهی دامنهٔ قبلی باید معتبر باشد.',
    checklist: 'کارهای دستی بعد از انتقال', history: 'سابقه', cli: 'بازیابی روی سرور: ./scripts/domain.sh show | rollback',
    cancel_t: 'لغو تغییر دامنه', cancel_m: 'رکوردهای DNS ساخته‌شده باقی می‌مانند؛ چیزی روی سرور تغییر نکرده است.',
    from_to: 'از', to: 'به', open_new: 'باز کردن دامنهٔ جدید',
    details: 'جزئیات', zone: 'دامنه (زون)', can_read: 'خواندن', can_edit: 'ویرایش DNS', yes: 'بله', no: 'خیر', na: 'نامشخص',
    zone_ck: 'بررسی دسترسی زون', leftover: 'رکورد آزمایشی حذف نشد؛ آن را در Cloudflare دستی پاک کنید:',
    test_how: 'برای هر زون یک رکورد TXT موقت ساخته و بلافاصله حذف می‌شود تا اجازهٔ ویرایش واقعاً آزموده شود.',
    ck: {
      shortcut: ['آدرس سرور در میان‌بر آیفون', 'میان‌بر را از صفحهٔ «اپ‌ها» دوباره دریافت و نصب کنید (آدرس جدید داخل آن است).', '/apps'],
      sms_app: ['آدرس سرور در اپ پیامک اندروید', 'در اپ SMS Bridge آدرس سرور را به دامنهٔ جدید تغییر دهید.', '/apps'],
      botfather: ['تنظیمات BotFather', 'اگر دامنهٔ ورود (/setdomain) یا لینک مینی‌اپ را در BotFather ثبت کرده‌اید، به دامنهٔ جدید تغییر دهید. دکمهٔ منوی مینی‌اپ خودکار به‌روز شد.', null],
      ptr: ['Reverse DNS (PTR) در کنسول Hetzner', 'در Hetzner Console → سرور → Networking، reverse DNS آی‌پی {ip} را روی mail.{domain} بگذارید. بقیهٔ کارهای ایمیل (MX، SPF، DKIM، DMARC، گواهی، فرستنده) خودکار انجام شد.', null],
      notify: ['اطلاع به نماینده‌ها و مشتری‌ها', 'آدرس جدید را از طریق اعلان‌ها و ربات اطلاع دهید.', '/notifications'],
    },
  },
  en: {
    ax_mode: 'Access mode', ax_modes: { direct: 'Direct', cloudflare: 'Cloudflare proxy', tunnel: 'Iran tunnel' },
    title: 'Domain & Cloudflare', sub: 'Cloudflare token and a safe, step-by-step change of the site domain',
    current: 'Current domain', ip: 'This server', only_super: 'Only a super admin can open this page.',
    cf: 'Cloudflare API token', cf_hint: 'Stored encrypted in the database and never shown again. When empty, the .env value is used.',
    src_panel: 'saved in the panel', src_env: 'from .env', src_none: 'not set', new_token: 'New token',
    save: 'Save', test: 'Test', remove: 'Remove token', by: 'by', zones: 'Zones', perms: 'Permissions',
    dns_edit: 'DNS edit', no_edit: 'no DNS edit', unknown: 'unknown', token_ok: 'Token is valid',
    trans: 'Keep the old domain for', trans_hint: 'The old domain keeps working with a 301 redirect to the new one for this many days, then it is removed (0 = right away).', days: 'days',
    wizard: 'Change the domain', new_domain: 'New domain', www: 'Also serve www', dns_mode: 'DNS',
    manual: 'Manual (another DNS provider)', pick_zone: 'Cloudflare zone', zone_auto: 'automatic from the domain', start: 'Start',
    test_first: 'Test the token first to pick a zone (or choose manual DNS).',
    steps: { domain: 'New domain', dns: 'DNS records', tls: 'TLS certificate + DKIM key', mail: 'Mail (MX, SPF, DKIM, DMARC)', apply: 'Apply on the server', links: 'Links & bot', transition: 'Transition', rollback: 'Rollback' },
    st: { ok: 'done', running: 'running…', waiting: 'waiting', failed: 'failed', pending: 'to do', skipped: 'skipped' },
    status: { draft: 'preparing', applying: 'applying', transition: 'transition', done: 'done', failed: 'failed', rolled_back: 'rolled back', cancelled: 'cancelled' },
    create_records: 'Create records in Cloudflare', check_dns: 'Check DNS', request_cert: 'Request certificate',
    apply: 'Switch to the new domain', retire: 'Remove the old domain now', cancel: 'Cancel',
    mail_recs: 'Mail records', mail_hint: 'Mail moves with the domain: the mail server becomes mail.<new domain> with its certificate and its own DKIM key. Create these records at your DNS provider (leave other TXT records alone), then “Check mail DNS”.',
    publish_mail: 'Publish mail records in Cloudflare', check_mail: 'Check mail DNS', prio: 'priority',
    records: 'Records needed', manual_hint: 'Create these records at your DNS provider (no proxy), then press “Check DNS”.',
    rec_type: 'Type', rec_name: 'Name', rec_value: 'Value', optional: 'optional (mail)', resolves: 'Public DNS answer',
    queued: 'Queued on the server — done within a minute…', host_last: 'Last server result',
    apply_t: 'Move the site to the new domain', apply_m: 'nginx, ALLOWED_HOSTS, CSRF, the site URL, links, the mail server (mail.<new domain> and the sender) and the bot’s Mini App button move to the new domain. App services restart without downtime. On any error everything is restored automatically.',
    old_redirects: 'The old domain redirects (301) to the new one until', retire_t: 'Remove the old domain', retire_m: 'The old domain is no longer served and its redirect is removed.',
    rollback: 'Roll back to the previous domain', rollback_t: 'Roll back the domain', rollback_m: 'The site goes back to the previous domain and the current one is no longer served. The previous domain’s certificate must still be valid.',
    checklist: 'Manual steps after the move', history: 'History', cli: 'Recovery on the server: ./scripts/domain.sh show | rollback',
    cancel_t: 'Cancel the domain change', cancel_m: 'DNS records already created stay; nothing has changed on the server.',
    from_to: 'from', to: 'to', open_new: 'Open the new domain',
    details: 'details', zone: 'Zone', can_read: 'Can read', can_edit: 'Can edit DNS', yes: 'yes', no: 'no', na: 'unknown',
    zone_ck: 'Zone access check', leftover: 'The test record could not be deleted; remove it in Cloudflare by hand:',
    test_how: 'For every zone a temporary TXT record is created and deleted right away, so edit access is really tested.',
    ck: {
      shortcut: ['iPhone Shortcut server URL', 'Download and install the Shortcut again from Apps (it carries the new address).', '/apps'],
      sms_app: ['Android SMS app URL', 'In the SMS Bridge app, change the server address to the new domain.', '/apps'],
      botfather: ['BotFather settings', 'If you registered a login domain (/setdomain) or a Mini App link in BotFather, change it. The Mini App menu button was updated automatically.', null],
      ptr: ['Reverse DNS (PTR) in the Hetzner console', 'In Hetzner Console → server → Networking, set the reverse DNS of {ip} to mail.{domain}. Everything else for mail (MX, SPF, DKIM, DMARC, certificate, sender) was done automatically.', null],
      notify: ['Tell resellers and customers', 'Announce the new address through Notifications and the bot.', '/notifications'],
    },
  },
}

const ORDER = ['domain', 'dns', 'tls', 'mail', 'apply', 'links', 'transition']
const TONE = { ok: 'ok', running: 'run', waiting: 'wait', failed: 'bad', pending: 'idle', skipped: 'idle' }

function StepIcon({ state }) {
  if (state === 'ok') return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5L20 7" /></svg>
  if (state === 'failed') return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
  if (state === 'running') return <span className="dm-spin" />
  return <span className="dm-dot" />
}

export default function DomainSettings() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const { staff } = useAuth()
  const confirm = useConfirm()
  const toast = useToast()
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  const [token, setToken] = useState('')
  const [test, setTest] = useState(null)
  const [busy, setBusy] = useState('')
  const [actErr, setActErr] = useState(null)
  const [days, setDays] = useState('')
  const [f, setF] = useState({ domain: '', include_www: true, mode: 'cloudflare', zone_id: '' })
  const timer = useRef(null)
  const lastAt = useRef(undefined)
  const superadmin = !!staff?.is_superadmin

  const take = (data) => {
    setSt(data)
    setDays((d) => (d === '' ? String(data.transition_days) : d))
    const at = data.last?.at || null
    if (lastAt.current !== undefined && at && at !== lastAt.current) {
      if (data.last.ok) toast.success(data.last.message); else toast.error(data.last.message)
    }
    lastAt.current = at
    const ax = data.access || {}
    const busyNow = data.pending || data.change?.status === 'applying'
      || Object.values(data.change?.steps || {}).some((x) => x.state === 'running')
      || ax.switch?.status === 'running' || ax.switch?.nginx?.state === 'running' || ax.dns01?.state === 'running'
    clearTimeout(timer.current)
    if (busyNow) timer.current = setTimeout(load, 5000)
  }
  const load = () => api.get('/admin/domain/').then((r) => take(r.data)).catch((e) => setErr(apiError(e)))
  useEffect(() => { if (superadmin) load(); return () => clearTimeout(timer.current) }, [superadmin])

  const act = async (key, url, body = {}) => {
    setBusy(key)
    try {
      const r = await api.post(url, body)
      take(r.data)
      setActErr(null)
      return r.data
    } catch (e) {
      if (e?.response?.data?.current) take(e.response.data)
      setActErr(e?.response?.data?.error || null)
      return null
    } finally { setBusy('') }
  }

  if (!superadmin) return <Alert>{s.only_super}</Alert>
  if (!st) return <div className="grid place-items-center py-16">{err ? <Alert>{err}</Alert> : <Spinner />}</div>

  const cf = st.cloudflare
  const shownTest = test || cf.last_test
  const zones = (shownTest?.zones || []).filter((z) => z.dns_edit !== false)
  const c = st.change && ['draft', 'applying', 'transition'].includes(st.change.status) ? st.change : null
  const step = (k) => c?.steps?.[k] || { state: 'pending' }
  const dnsOk = step('dns').state === 'ok'
  const tlsOk = step('tls').state === 'ok'
  const mailOk = step('mail').state === 'ok'
  const hostBusy = !!st.pending
  // reasons already shown on a step are not repeated under the actions / in "last server result"
  const shownRaw = new Set(Object.values(c?.steps || {}).flatMap((x) => [x.detail?.error?.raw, ...(x.detail?.hosts || []).map((h) => h.why?.raw)]).filter(Boolean))
  const lastWhy = st.last && !st.last.ok && st.last.explain && !shownRaw.has(st.last.explain.raw) ? st.last.explain : null

  const runTest = async () => {
    setBusy('test')
    try { const r = await api.post('/admin/domain/token/test/', token ? { token } : {}); setTest(r.data) } catch { /* toast shown */ } finally { setBusy('') }
  }

  return (
    <div className="space-y-4 dm">
      <style>{CSS}</style>
      <div className="dm-head">
        <div>
          <h1 className="text-lg font-bold">{s.title}</h1>
          <p className="text-sm text-muted mt-1">{s.sub}</p>
        </div>
        <div className="dm-now">
          <span>{s.current}</span><bdi dir="ltr" className="dm-mono">{st.current.domain}</bdi>
          <span>{s.ip}</span><bdi dir="ltr" className="dm-mono">{st.current.server_ip || '—'}</bdi>
          <span>{s.ax_mode}</span><span className={`dm-pill dm-mode-${st.access?.mode || 'direct'}`}>{s.ax_modes[st.access?.mode || 'direct']}</span>
        </div>
      </div>
      <Alert>{err}</Alert>

      <AccessMode st={st} lang={lang} take={take} load={load} />

      {/* ---------------- Cloudflare token */}
      <section className="card dm-card">
        <div className="dm-row-h">
          <h2>{s.cf}</h2>
          <span className={`dm-pill ${cf.source ? 'ok' : 'idle'}`}>{cf.source === 'panel' ? s.src_panel : cf.source === 'env' ? s.src_env : s.src_none}</span>
        </div>
        <p className="dm-hint">{s.cf_hint}{cf.updated_at && <> · {jalali(cf.updated_at, true, lang)} {cf.updated_by && `${s.by} ${cf.updated_by}`}</>}</p>
        <div className="dm-token">
          <input className="input" type="password" dir="ltr" autoComplete="off" placeholder={s.new_token} aria-label={s.new_token}
            value={token} onChange={(e) => setToken(e.target.value.trim())} />
          <div className="dm-btns">
            <button className="btn-primary text-sm" disabled={!token || !!busy}
              onClick={async () => { if (await act('save', '/admin/domain/token/', { token })) { setToken(''); setTest(null) } }}>{s.save}</button>
            <button className="btn-ghost text-sm" disabled={!!busy || (!token && !cf.source)} onClick={runTest}>{busy === 'test' ? <span className="dm-spin" /> : s.test}</button>
            {cf.token_set && <button className="btn-ghost text-sm dm-danger" disabled={!!busy}
              onClick={() => confirm({ tone: 'danger', title: s.remove, message: s.cf_hint, confirmLabel: s.remove,
                action: async () => { await api.post('/admin/domain/token/', { token: '' }).then((r) => { take(r.data); setTest(null) }) } })}>{s.remove}</button>}
          </div>
        </div>
        {shownTest && (
          <div className={`dm-test ${shownTest.ok ? 'ok' : 'bad'}`}>
            <div>
              <b>{shownTest.ok ? s.token_ok : null}</b>
              {!shownTest.ok && (shownTest.explain ? <Why info={shownTest.explain} lang={lang} s={s} /> : <b>{shownTest.error}</b>)}
              {shownTest.note && <span className="dm-hint"> · {shownTest.note}</span>}
              <span className="dm-hint"> · {jalali(shownTest.at, true, lang)}</span>
            </div>
            {!!shownTest.zones?.length && (
              <div className="dm-ztable" role="table" aria-label={s.zones}>
                <div className="dm-zr dm-zh" role="row"><span role="columnheader">{s.zone}</span><span role="columnheader">{s.can_read}</span><span role="columnheader">{s.can_edit}</span></div>
                {shownTest.zones.map((z) => (
                  <div key={z.id} className={`dm-zr ${z.dns_edit === false ? 'bad' : z.dns_edit ? 'ok' : ''}`} role="row">
                    <bdi dir="ltr" className="dm-mono" role="cell">{z.name}</bdi>
                    <span role="cell">{yn(z.read, s)}</span>
                    <span role="cell">{yn(z.dns_edit, s)}</span>
                    {z.error && !z.dns_edit && <div className="dm-zerr"><Why info={z.error} lang={lang} s={s} small /></div>}
                    {z.leftover && <div className="dm-zerr dm-hint">{s.leftover} <bdi dir="ltr" className="dm-mono">{z.leftover}</bdi></div>}
                  </div>
                ))}
              </div>
            )}
            {!!shownTest.zones?.length && <p className="dm-hint">{s.test_how}</p>}
            {!!shownTest.permissions?.length && (
              <div className="dm-zones"><span className="dm-k">{s.perms}</span>
                {shownTest.permissions.map((p) => <code key={p} dir="ltr" className="dm-perm">{p}</code>)}</div>
            )}
          </div>
        )}
      </section>

      {/* ---------------- transition period */}
      <section className="card dm-card">
        <div className="dm-row-h"><h2>{s.trans}</h2></div>
        <div className="dm-days">
          <input className="input" type="number" min="0" max="90" dir="ltr" aria-label={s.trans} value={days} onChange={(e) => setDays(e.target.value)} />
          <span>{s.days}</span>
          <button className="btn-ghost text-sm" disabled={!!busy || String(st.transition_days) === days}
            onClick={() => act('days', '/admin/domain/settings/', { transition_days: days })}>{s.save}</button>
        </div>
        <p className="dm-hint">{s.trans_hint}</p>
      </section>

      {/* ---------------- wizard */}
      <section className="card dm-card">
        <div className="dm-row-h">
          <h2>{s.wizard}</h2>
          {c && <span className={`dm-pill ${c.status === 'transition' ? 'ok' : 'run'}`}>{s.status[c.status]}</span>}
        </div>

        {!c && (
          <form className="dm-form" onSubmit={(e) => { e.preventDefault(); act('start', '/admin/domain/start/', f) }}>
            <label className="dm-field"><span className="label">{s.new_domain}</span>
              <input className="input dm-mono" dir="ltr" placeholder="example.com" value={f.domain} required
                onChange={(e) => setF({ ...f, domain: e.target.value.trim().toLowerCase() })} /></label>
            <div className="dm-www"><Toggle checked={f.include_www} onChange={(v) => setF({ ...f, include_www: v })} label={s.www} /><span>{s.www}</span></div>
            <label className="dm-field"><span className="label">{s.dns_mode}</span>
              <select className="input" value={f.mode === 'manual' ? 'manual' : f.zone_id || 'auto'}
                onChange={(e) => { const v = e.target.value; setF({ ...f, mode: v === 'manual' ? 'manual' : 'cloudflare', zone_id: ['manual', 'auto'].includes(v) ? '' : v }) }}>
                {cf.source && <option value="auto">{s.pick_zone}: {s.zone_auto}</option>}
                {zones.map((z) => <option key={z.id} value={z.id}>{s.pick_zone}: {z.name}</option>)}
                <option value="manual">{s.manual}</option>
              </select></label>
            {f.mode !== 'manual' && !zones.length && <p className="dm-hint">{s.test_first}</p>}
            <button className="btn-primary text-sm dm-go" disabled={!!busy || !f.domain}>{busy === 'start' ? <span className="dm-spin" /> : s.start}</button>
          </form>
        )}

        {c && (
          <>
            <div className="dm-route"><bdi dir="ltr" className="dm-mono">{c.old_domain}</bdi><span aria-hidden>{lang === 'fa' ? '←' : '→'}</span><bdi dir="ltr" className="dm-mono dm-new">{c.new_domain}</bdi>
              <span className="dm-hint">· {c.mode === 'manual' ? s.manual : `Cloudflare ${c.zone_name}`}</span></div>
            <ol className="dm-steps">
              {ORDER.map((k, i) => {
                const x = step(k)
                return (
                  <li key={k} className={`dm-step ${TONE[x.state] || 'idle'}`}>
                    <span className="dm-ico"><StepIcon state={x.state} /></span>
                    <div className="dm-step-b">
                      <div className="dm-step-t"><b>{i + 1}. {s.steps[k]}</b><span className="dm-st">{s.st[x.state] || x.state}</span></div>
                      {x.message && !(x.detail?.error && !x.detail?.hosts && x.state !== 'ok') && <bdi className="dm-msg">{x.message}</bdi>}
                      {x.detail?.error && !x.detail?.hosts && x.state !== 'ok' && <Why info={x.detail.error} lang={lang} s={s} />}
                      {k === 'dns' && x.detail?.zone_check && (
                        <span className="dm-ck">{s.zone_ck} <bdi dir="ltr">{c.zone_name}</bdi>: {s.can_read} {yn(x.detail.zone_check.read, s)} · {s.can_edit} {yn(x.detail.zone_check.dns_edit, s)}</span>
                      )}
                      {k === 'mail' && x.detail?.hosts && (
                        <ul className="dm-res">{x.detail.hosts.map((h) => (
                          <li key={h.type + h.name} className={h.ok ? 'ok' : 'bad'}>
                            {h.type} <bdi dir="ltr" className="dm-mono">{h.name}</bdi>{h.ok ? ' ✓' : ''}
                            {!h.ok && x.state !== 'ok' && <Why info={h.why} lang={lang} s={s} small />}
                          </li>))}</ul>
                      )}
                      {k === 'dns' && x.detail?.hosts && (
                        <ul className="dm-res">{x.detail.hosts.map((h) => (
                          <li key={h.name} className={h.ok ? 'ok' : h.required ? 'bad' : 'idle'}>
                            <bdi dir="ltr" className="dm-mono">{h.name}</bdi> → <bdi dir="ltr" className="dm-mono">{h.seen.join(', ') || '—'}</bdi>{!h.required && <small> ({s.optional})</small>}
                            {!h.ok && x.state !== 'ok' && <Why info={h.why} lang={lang} s={s} small />}
                          </li>))}</ul>
                      )}
                    </div>
                  </li>
                )
              })}
            </ol>

            {hostBusy && <Alert kind="warning">{s.queued}</Alert>}
            {actErr && !(actErr.raw && shownRaw.has(actErr.raw)) && <Why info={actErr} lang={lang} s={s} />}

            {c.status === 'draft' && step('dns').state !== 'ok' && (
              <div className="dm-records">
                <b>{s.records}</b>
                {c.mode === 'manual' && <p className="dm-hint">{s.manual_hint}</p>}
                <div className="dm-table" role="table">
                  <div className="dm-tr dm-th" role="row"><span>{s.rec_type}</span><span>{s.rec_name}</span><span>{s.rec_value}</span></div>
                  {c.records.map((r) => (
                    <div key={r.name} className="dm-tr" role="row">
                      <span>A</span><span className="dm-cp"><bdi dir="ltr" className="dm-mono">{r.name}</bdi><Copyable text={r.name} /></span>
                      <span className="dm-cp"><bdi dir="ltr" className="dm-mono">{r.content}</bdi><Copyable text={r.content} />{!r.required && <small>{s.optional}</small>}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {c.status === 'draft' && tlsOk && !mailOk && (
              <div className="dm-records">
                <b>{s.mail_recs}</b>
                <p className="dm-hint">{s.mail_hint}</p>
                <div className="dm-table" role="table">
                  <div className="dm-tr dm-th" role="row"><span>{s.rec_type}</span><span>{s.rec_name}</span><span>{s.rec_value}</span></div>
                  {c.mail_records.map((r) => (
                    <div key={r.type + r.name} className="dm-tr" role="row">
                      <span>{r.type}</span><span className="dm-cp"><bdi dir="ltr" className="dm-mono">{r.name}</bdi><Copyable text={r.name} /></span>
                      <span className="dm-cp"><bdi dir="ltr" className="dm-mono dm-long">{r.content}</bdi><Copyable text={r.content} />{r.priority != null && <small>{s.prio} {r.priority}</small>}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="dm-actions">
              {c.status === 'draft' && !dnsOk && c.mode === 'cloudflare' && (
                <button className="btn-primary text-sm" disabled={!!busy} onClick={() => act('dns', `/admin/domain/${c.id}/dns/`)}>{busy === 'dns' ? <span className="dm-spin" /> : s.create_records}</button>)}
              {c.status === 'draft' && !dnsOk && (
                <button className={`${c.mode === 'manual' || step('dns').state !== 'pending' ? 'btn-primary' : 'btn-ghost'} text-sm`} disabled={!!busy}
                  onClick={() => act('check', `/admin/domain/${c.id}/dns-check/`)}>{busy === 'check' ? <span className="dm-spin" /> : s.check_dns}</button>)}
              {c.status === 'draft' && dnsOk && !tlsOk && (
                <button className="btn-primary text-sm" disabled={!!busy || hostBusy || step('tls').state === 'running'} onClick={() => act('tls', `/admin/domain/${c.id}/tls/`)}>{s.request_cert}</button>)}
              {c.status === 'draft' && tlsOk && !mailOk && c.mode === 'cloudflare' && (
                <button className="btn-primary text-sm" disabled={!!busy} onClick={() => act('mail', `/admin/domain/${c.id}/mail/`)}>{busy === 'mail' ? <span className="dm-spin" /> : s.publish_mail}</button>)}
              {c.status === 'draft' && tlsOk && !mailOk && (
                <button className={`${c.mode === 'manual' ? 'btn-primary' : 'btn-ghost'} text-sm`} disabled={!!busy} onClick={() => act('mcheck', `/admin/domain/${c.id}/mail-check/`)}>{busy === 'mcheck' ? <span className="dm-spin" /> : s.check_mail}</button>)}
              {c.status === 'draft' && tlsOk && mailOk && (
                <button className="btn-primary text-sm" disabled={!!busy || hostBusy}
                  onClick={() => confirm({ tone: 'danger', title: s.apply_t, message: s.apply_m, confirmLabel: s.apply,
                    details: [[s.from_to, c.old_domain], [s.to, c.new_domain], [s.trans, `${c.transition_days} ${s.days}`]],
                    action: async () => { const r = await api.post(`/admin/domain/${c.id}/apply/`); take(r.data) } })}>{s.apply}</button>)}
              {c.status === 'transition' && (
                <button className="btn-ghost text-sm dm-danger" disabled={!!busy || hostBusy || step('transition').state === 'running'}
                  onClick={() => confirm({ tone: 'danger', title: s.retire_t, message: s.retire_m, confirmLabel: s.retire, details: [[s.from_to, c.old_domain]],
                    action: async () => { const r = await api.post(`/admin/domain/${c.id}/retire/`); take(r.data) } })}>{s.retire}</button>)}
              {c.status === 'draft' && (
                <button className="btn-ghost text-sm" disabled={!!busy || hostBusy}
                  onClick={() => confirm({ tone: 'danger', title: s.cancel_t, message: s.cancel_m, confirmLabel: s.cancel,
                    action: async () => { const r = await api.post(`/admin/domain/${c.id}/cancel/`); take(r.data) } })}>{s.cancel}</button>)}
            </div>
            {c.status === 'transition' && c.old_until && (
              <p className="dm-hint">{s.old_redirects} {jalali(c.old_until, true, lang)} · <a className="dm-link" href={`https://${c.new_domain}/`} target="_blank" rel="noreferrer">{s.open_new}</a></p>)}
          </>
        )}
        {st.last && !hostBusy && (st.last.ok || !st.last.explain) && (
          <p className={`dm-last ${st.last.ok ? 'ok' : 'bad'}`}>{s.host_last}: <bdi dir="ltr">{st.last.message}</bdi> · {jalali(st.last.at, true, lang)}</p>
        )}
        {lastWhy && !hostBusy && (
          <div className="dm-lastwhy"><span className="dm-k">{s.host_last} · {jalali(st.last.at, true, lang)}</span><Why info={lastWhy} lang={lang} s={s} /></div>
        )}
      </section>

      {/* ---------------- checklist (after a move) */}
      {st.change && ['transition', 'done'].includes(st.change.status) && (
        <section className="card dm-card">
          <div className="dm-row-h"><h2>{s.checklist}</h2>
            <span className="dm-pill idle">{Object.values(st.change.checklist).filter(Boolean).length}/{st.checklist_keys.length}</span></div>
          <ul className="dm-check">
            {st.checklist_keys.map((k) => {
              const [t, d0, to] = s.ck[k]
              const d = d0.replace('{ip}', st.change.server_ip || st.current.server_ip).replace('{domain}', st.change.new_domain)
              const done = !!st.change.checklist[k]
              return (
                <li key={k} className={done ? 'done' : ''}>
                  <label>
                    <input type="checkbox" checked={done} disabled={!!busy}
                      onChange={(e) => act(`ck-${k}`, `/admin/domain/${st.change.id}/checklist/`, { key: k, done: e.target.checked })} />
                    <span><b>{t}</b><small>{d}</small></span>
                  </label>
                  {to && <Link className="dm-link" to={to}>{lang === 'fa' ? '←' : '→'}</Link>}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {/* ---------------- rollback */}
      {st.rollback && (
        <section className="card dm-card">
          <div className="dm-row-h"><h2>{s.rollback}</h2></div>
          <div className="dm-actions">
            <button className="btn-ghost text-sm dm-danger" disabled={!!busy || hostBusy}
              onClick={() => confirm({ tone: 'danger', title: s.rollback_t, message: s.rollback_m, confirmLabel: s.rollback,
                details: [[s.from_to, st.rollback.from], [s.to, st.rollback.to]],
                action: async () => { const r = await api.post('/admin/domain/rollback/'); take(r.data) } })}>
              {s.rollback}: <bdi dir="ltr">{st.rollback.to}</bdi>
            </button>
          </div>
          <p className="dm-hint"><bdi dir="ltr">{s.cli}</bdi></p>
        </section>
      )}

      {/* ---------------- history */}
      {!!st.history.length && (
        <section className="card dm-card">
          <div className="dm-row-h"><h2>{s.history}</h2></div>
          <ul className="dm-hist">
            {st.history.map((h) => (
              <li key={h.id}>
                <bdi dir="ltr" className="dm-mono">{h.old_domain} → {h.new_domain}</bdi>
                <span className={`dm-pill ${h.status === 'done' || h.status === 'transition' ? 'ok' : h.status === 'cancelled' ? 'idle' : h.status === 'rolled_back' ? 'wait' : 'run'}`}>{s.status[h.status]}</span>
                <small>{jalali(h.created_at, true, lang)} · {h.created_by}</small>
              </li>
            ))}
          </ul>
          {!st.rollback && <p className="dm-hint"><bdi dir="ltr">{s.cli}</bdi></p>}
        </section>
      )}
    </div>
  )
}

const CSS = `
.dm-head { display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: flex-start; }
.dm-now { display: grid; grid-template-columns: auto auto; gap: 2px 10px; font-size: 12.5px; color: var(--c-muted-fg); align-items: center; }
.dm-mono { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--c-text); overflow-wrap: anywhere; }
.dm-card { display: flex; flex-direction: column; gap: 12px; }
.dm-row-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.dm-row-h h2 { font-size: 15px; font-weight: 800; }
.dm-hint { font-size: 12px; color: var(--c-muted-fg); line-height: 1.8; }
.dm-pill { font-size: 11.5px; font-weight: 800; padding: 3px 10px; border-radius: 999px; white-space: nowrap; border: 1px solid transparent; }
.dm-pill.ok { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.dm-pill.run, .dm-pill.wait { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.dm-pill.bad { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.dm-mode-direct { color: var(--c-text); border-color: var(--c-border); }
.dm-mode-cloudflare { color: #fff; background: #f38020; }
.dm-mode-tunnel { color: #fff; background: var(--c-primary); }
.dm-pill.idle { color: var(--c-muted-fg); border-color: var(--c-border); }
.dm-token { display: flex; gap: 8px; flex-wrap: wrap; }
.dm-token .input { flex: 1 1 260px; font-family: 'JetBrains Mono', monospace; }
.dm-btns, .dm-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.dm-danger { color: var(--c-danger-fg); }
.dm-test { border-radius: 12px; padding: 10px 12px; font-size: 13px; border: 1px solid var(--c-border); display: flex; flex-direction: column; gap: 6px; }
.dm-test.ok > b { color: var(--c-success-fg); } .dm-test.bad > b { color: var(--c-danger-fg); }
.dm-zones { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.dm-k { font-size: 12px; font-weight: 700; color: var(--c-muted-fg); }
.dm-zone { font-size: 12px; padding: 2px 8px; border-radius: 8px; border: 1px solid var(--c-border); }
.dm-zone.ok { color: var(--c-success-fg); } .dm-zone.bad { color: var(--c-danger-fg); }
.dm-why { border-radius: 10px; padding: 8px 10px; background: color-mix(in srgb, var(--c-danger) 8%, transparent); border: 1px solid color-mix(in srgb, var(--c-danger) 30%, transparent); display: flex; flex-direction: column; gap: 4px; }
.dm-why p { margin: 0; font-size: 13px; line-height: 1.8; color: var(--c-danger-fg); font-weight: 600; overflow-wrap: anywhere; }
.dm-why.sm { padding: 6px 8px; margin-top: 4px; } .dm-why.sm p { font-size: 12px; font-weight: 500; }
.dm-raw { font-size: 11px; color: var(--c-muted-fg); overflow-wrap: anywhere; line-height: 1.6; }
.dm-raw bdi { font-family: 'JetBrains Mono', monospace; }
.dm-lastwhy { display: flex; flex-direction: column; gap: 4px; }
.dm-ztable { border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; }
.dm-zr { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr); gap: 8px; padding: 7px 12px; align-items: center; border-top: 1px solid var(--c-border); font-size: 12.5px; }
.dm-zr.dm-zh { border-top: 0; font-size: 12px; font-weight: 700; color: var(--c-muted-fg); }
.dm-zerr { grid-column: 1 / -1; }
.dm-y { color: var(--c-success-fg); font-weight: 700; white-space: nowrap; } .dm-n { color: var(--c-danger-fg); font-weight: 700; white-space: nowrap; } .dm-u { color: var(--c-muted-fg); white-space: nowrap; }
.dm-ck { font-size: 12px; color: var(--c-muted-fg); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.dm-perm { font-size: 11px; padding: 1px 6px; border-radius: 6px; background: color-mix(in srgb, var(--c-text) 7%, transparent); }
.dm-days { display: flex; align-items: center; gap: 8px; }
.dm-days .input { width: 96px; }
.dm-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: end; }
.dm-field { display: flex; flex-direction: column; }
.dm-go { justify-self: start; }
.dm-route { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.dm-new { font-weight: 800; color: var(--c-primary); }
.dm-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.dm-step { display: flex; gap: 10px; position: relative; padding-bottom: 14px; }
.dm-step:not(:last-child)::before { content: ''; position: absolute; inset-inline-start: 13px; top: 28px; bottom: 2px; width: 2px; background: var(--c-border); }
.dm-step.ok:not(:last-child)::before { background: var(--c-success); }
.dm-ico { flex: none; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; border: 2px solid var(--c-border); color: var(--c-muted-fg); background: var(--c-surface, transparent); }
.dm-step.ok .dm-ico { background: var(--c-success); border-color: var(--c-success); color: #fff; }
.dm-step.bad .dm-ico { background: var(--c-danger); border-color: var(--c-danger); color: #fff; }
.dm-step.run .dm-ico, .dm-step.wait .dm-ico { border-color: var(--c-warning); color: var(--c-warning-fg); }
.dm-step-b { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 3px; padding-top: 3px; }
.dm-step-t { display: flex; justify-content: space-between; gap: 8px; font-size: 13.5px; }
.dm-st { font-size: 11.5px; font-weight: 700; color: var(--c-muted-fg); white-space: nowrap; }
.dm-step.ok .dm-st { color: var(--c-success-fg); } .dm-step.bad .dm-st, .dm-step.bad .dm-msg { color: var(--c-danger-fg); }
.dm-step.run .dm-st, .dm-step.wait .dm-st { color: var(--c-warning-fg); }
.dm-msg { font-size: 12.5px; color: var(--c-muted-fg); overflow-wrap: anywhere; line-height: 1.7; }
.dm-res { list-style: none; padding: 0; margin: 2px 0 0; display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.dm-res li.ok { color: var(--c-success-fg); } .dm-res li.bad { color: var(--c-danger-fg); } .dm-res li.idle { color: var(--c-muted-fg); }
.dm-res .dm-mono { font-size: 12px; color: inherit; }
.dm-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; opacity: .5; }
.dm-spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid currentColor; border-inline-end-color: transparent; display: inline-block; animation: dmspin .8s linear infinite; }
@keyframes dmspin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .dm-spin { animation: none; } }
.dm-records { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.dm-table { border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; }
.dm-tr { display: grid; grid-template-columns: 52px minmax(0, 1.3fr) minmax(0, 1fr); gap: 8px; padding: 8px 12px; align-items: center; border-top: 1px solid var(--c-border); }
.dm-th { border-top: 0; font-size: 12px; font-weight: 700; color: var(--c-muted-fg); }
.dm-tr small { color: var(--c-muted-fg); font-size: 11.5px; }
.dm-long { word-break: break-all; font-size: 11.5px; max-height: 4.6em; overflow: hidden; }
.dm-cp { display: flex; align-items: center; gap: 6px; min-width: 0; flex-wrap: wrap; }
.dm-www { display: flex; align-items: center; gap: 10px; font-size: 13.5px; min-height: 44px; }
.dm-last { font-size: 12.5px; overflow-wrap: anywhere; } .dm-last.ok { color: var(--c-success-fg); } .dm-last.bad { color: var(--c-danger-fg); }
.dm-link { font-weight: 800; color: var(--c-primary); text-decoration: underline; }
.dm-check { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
.dm-check li { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 8px 0; border-top: 1px solid var(--c-border); }
.dm-check li:first-child { border-top: 0; }
.dm-check label { display: flex; gap: 10px; align-items: flex-start; cursor: pointer; min-width: 0; }
.dm-check input { margin-top: 4px; width: 18px; height: 18px; accent-color: var(--c-primary); flex: none; }
.dm-check span { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.dm-check small { color: var(--c-muted-fg); line-height: 1.7; }
.dm-check li.done b { text-decoration: line-through; color: var(--c-muted-fg); }
.dm-hist { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.dm-hist li { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12.5px; }
.dm-hist small { color: var(--c-muted-fg); }
@media (max-width: 767px) {
  .dm-form { grid-template-columns: 1fr; }
  .dm-token .input, .dm-form .input, .dm-days .input { font-size: 16px; height: 44px; }
  .dm-tr { grid-template-columns: 36px minmax(0, 1fr); }
  .dm-tr > :nth-child(3) { grid-column: 2; }
  .dm-th > :nth-child(3) { display: none; }
}
`
