import { useEffect, useRef, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'

// /settings/paths — admin-panel and reseller-portal paths (docs/paths.md).
// The server only records the request; the host watcher applies it within a
// minute (nginx -t, reload, verify, automatic rollback).

const T = {
  fa: {
    title: 'مسیرها', sub: 'آدرس پنل مدیریت و پرتال نماینده‌ها روی همین دامنه',
    admin: 'مسیر پنل مدیریت', portal: 'مسیر پرتال نماینده‌ها', now: 'فعلی', save: 'اعمال مسیرها',
    rules: 'فقط حروف کوچک انگلیسی، عدد، - و _ ؛ ۲ تا ۴۰ نویسه بعد از /. مسیرهای سایت (مثل /api، /login) مجاز نیستند.',
    pending: 'در صف اعمال — تا یک دقیقه دیگر انجام می‌شود…', ok: 'اعمال شد', failed: 'اعمال نشد', at: 'زمان',
    confirm_t: 'جابه‌جایی مسیرها', confirm_m: 'پس از اعمال، مسیر قبلی پنل کار نمی‌کند (404) و به مسیر جدید هدایت نمی‌شود. مسیر جدید را ذخیره کنید. اگر فراموش شد، روی سرور: ./scripts/paths.sh show یا reset',
    go: 'رفتن به آدرس جدید', only_super: 'فقط مدیر کل می‌تواند مسیرها را تغییر دهد.',
    cli: 'بازیابی از سرور: ./scripts/paths.sh show | reset | set-admin /x | set-portal /y',
  },
  en: {
    title: 'Paths', sub: 'Where the admin panel and the reseller portal live on this domain',
    admin: 'Admin panel path', portal: 'Reseller portal path', now: 'current', save: 'Apply paths',
    rules: 'Lowercase a–z, 0–9, - and _ only; 2–40 characters after /. Site paths (like /api, /login) are not allowed.',
    pending: 'Queued — applied within a minute…', ok: 'Applied', failed: 'Not applied', at: 'at',
    confirm_t: 'Move the paths', confirm_m: 'Once applied, the old panel path stops working (404) and does not redirect. Save the new address. If you forget it, on the server: ./scripts/paths.sh show or reset',
    go: 'Open the new address', only_super: 'Only a super admin can change the paths.',
    cli: 'Recovery on the server: ./scripts/paths.sh show | reset | set-admin /x | set-portal /y',
  },
}

export default function PathsSettings() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const { staff } = useAuth()
  const confirm = useConfirm()
  const [st, setSt] = useState(null)
  const [f, setF] = useState({ admin: '', portal: '' })
  const [err, setErr] = useState('')
  const [fieldErr, setFieldErr] = useState({})
  const timer = useRef(null)
  const superadmin = !!staff?.is_superadmin

  const load = () => api.get('/admin/paths/').then((r) => {
    setSt(r.data)
    setF((cur) => (cur.admin ? cur : { admin: r.data.admin, portal: r.data.portal }))
    if (r.data.pending) timer.current = setTimeout(load, 5000)
  }).catch((e) => setErr(apiError(e)))
  useEffect(() => { load(); return () => clearTimeout(timer.current) }, [])

  const submit = async (e) => {
    e.preventDefault(); setErr(''); setFieldErr({})
    await confirm({
      tone: 'danger', title: s.confirm_t, message: s.confirm_m, confirmLabel: s.save,
      details: [[s.admin, `${f.admin}/`], [s.portal, `${f.portal}/`]],
      action: async () => {
        try {
          const r = await api.post('/admin/paths/', f)
          setSt(r.data); clearTimeout(timer.current); timer.current = setTimeout(load, 5000)
        } catch (e2) {
          if (e2?.response?.status === 400) { setFieldErr(e2.response.data); throw new Error(Object.values(e2.response.data).join(' · ')) }
          throw e2
        }
      },
    })
  }

  if (!st) return <div className="grid place-items-center py-16">{err ? <Alert>{err}</Alert> : <Spinner />}</div>
  const moved = st.last?.ok && st.last.admin && window.location.pathname.startsWith(st.last.admin + '/') === false
  return (
    <div className="space-y-4 pth">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.title}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      <Alert>{err}</Alert>
      {st.pending && <Alert kind="warning">{s.pending}</Alert>}
      {!st.pending && st.last && (
        <Alert kind={st.last.ok ? 'success' : 'danger'}>
          {st.last.ok ? s.ok : s.failed} — <bdi dir="ltr">{st.last.message}</bdi> · {s.at} {jalali(st.last.at, true, lang)}
          {moved && <> · <a href={`${st.last.admin}/`} className="pth-go">{s.go}: <bdi dir="ltr">{st.last.admin}/</bdi></a></>}
        </Alert>
      )}
      <form className="card pth-card" onSubmit={submit}>
        {[['admin', s.admin], ['portal', s.portal]].map(([k, label]) => (
          <label key={k} className="pth-row">
            <span className="label">{label} <small>({s.now}: <bdi dir="ltr">{st[k]}/</bdi>)</small></span>
            <span className="pth-input">
              <bdi dir="ltr" className="pth-host">{window.location.host}</bdi>
              <input className="input" dir="ltr" value={f[k]} disabled={!superadmin || !!st.pending} aria-label={label}
                onChange={(e) => setF({ ...f, [k]: e.target.value.trim().toLowerCase() })} />
            </span>
            {fieldErr[k] && <span className="pth-err">{fieldErr[k]}</span>}
          </label>
        ))}
        <p className="pth-hint">{s.rules}</p>
        {!superadmin && <p className="pth-err">{s.only_super}</p>}
        <button className="btn-primary text-sm" disabled={!superadmin || !!st.pending}>{s.save}</button>
        <p className="pth-hint"><bdi dir="ltr">{s.cli}</bdi></p>
      </form>
    </div>
  )
}

const CSS = `
.pth-card { display: flex; flex-direction: column; gap: 14px; }
.pth-row { display: flex; flex-direction: column; gap: 6px; }
.pth-row small { font-weight: 500; color: var(--c-muted-fg); }
.pth-input { display: flex; align-items: center; gap: 0; border-radius: 12px; overflow: hidden; }
.pth-host { font-family: 'JetBrains Mono', monospace; font-size: 13px; padding: 0 10px; color: var(--c-muted-fg); white-space: nowrap; }
.pth-input .input { font-family: 'JetBrains Mono', monospace; }
.pth-hint { font-size: 12px; color: var(--c-muted-fg); line-height: 1.7; }
.pth-err { font-size: 12.5px; font-weight: 700; color: var(--c-danger-fg); }
.pth-go { font-weight: 800; text-decoration: underline; }
@media (max-width: 767px) { .pth-input { flex-direction: column; align-items: stretch; } .pth-host { padding: 0 2px 4px; } .pth-input .input { font-size: 16px; height: 44px; } }
`
