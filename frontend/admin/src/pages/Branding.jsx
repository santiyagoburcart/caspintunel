import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Spinner } from '../components/ui'

const T = {
  fa: {
    h1: 'برندینگ و هویت سامانه',
    sub: 'مدیریت نام برند، دامنهٔ اصلی، توضیحات سئو و بارگذاری لوگو و نماد سایت',
    card_h: 'برندینگ', card_sub: 'اطلاعاتی که در وب‌سایت و ربات به کاربران نمایش داده می‌شود',
    active_domain: 'دامنهٔ فعال: {d}',
    save: 'ذخیرهٔ تغییرات',
    media_h: 'رسانه و آیکون',
    logo_hint: 'فرمت PNG، SVG یا WebP با پس‌زمینهٔ شفاف',
    favicon_hint: 'آیکون 32×32 یا 64×64 پیکسل برای تب مرورگر (ico یا png)',
    domain_hint: 'آدرس بدون پروتکل http/https',
    meta_hint: 'حداکثر 160 کاراکتر برای نتایج گوگل',
    current: 'فعلی', choose: 'انتخاب فایل جدید',
  },
  en: {
    h1: 'Branding & identity',
    sub: 'Manage the brand name, main domain, SEO description and upload the logo and site icon',
    card_h: 'Branding', card_sub: 'Information shown to users on the website and the bot',
    active_domain: 'Active domain: {d}',
    save: 'Save changes',
    media_h: 'Media & icon',
    logo_hint: 'PNG, SVG or WebP with a transparent background',
    favicon_hint: '32×32 or 64×64 px icon for the browser tab (ico or png)',
    domain_hint: 'address without the http/https protocol',
    meta_hint: 'up to 160 characters for Google results',
    current: 'current', choose: 'choose a new file',
  },
}

const FIELDS = [
  ['site_name_fa', 'site_name_fa', false, false],
  ['site_name_en', 'site_name_en', true, false],
  ['site_domain', 'domain', true, false],
  ['support_telegram', 'support_telegram', true, false],
  ['bot_description_fa', 'bot_desc_fa', false, true],
  ['bot_description_en', 'bot_desc_en', true, true],
  ['meta_description', 'meta_desc', false, true],
]

function Upload({ label, hint, current, onFile, s, accept }) {
  const [preview, setPreview] = useState(null)
  const pick = (file) => {
    onFile(file)
    setPreview(file ? URL.createObjectURL(file) : null)
  }
  const src = preview || current
  return (
    <div className="br-upload">
      <div className="br-upload-thumb">
        {src ? <img src={src} alt={label} onError={(e) => { e.currentTarget.style.display = 'none' }} /> : <span className="br-upload-empty">—</span>}
      </div>
      <div className="min-w-0 flex-1">
        <span className="label">{label}</span>
        <p className="br-hint">{hint}</p>
        <input className="br-file" type="file" accept={accept} aria-label={label} onChange={(e) => pick(e.target.files[0])} />
      </div>
    </div>
  )
}

export default function Branding() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/admin/branding/').then((r) => setF(r.data)).catch(() => { setF({}); setErr(t('load_error')) })
  }, [])

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try {
      const fd = new FormData()
      FIELDS.forEach(([k]) => fd.append(k, f[k] ?? ''))
      if (f._logo) fd.append('logo', f._logo)
      if (f._favicon) fd.append('favicon', f._favicon)
      const { data } = await api.patch('/admin/branding/', fd)
      setF(data); setMsg(t('saved')); setTimeout(() => setMsg(''), 2500)
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  if (!f) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="br space-y-5">
      <style>{CSS}</style>

      <div className="br-head">
        <div>
          <h1 className="text-lg font-bold">{s.h1}</h1>
          <p className="text-sm text-muted mt-1">{s.sub}</p>
        </div>
        <button type="submit" form="branding-form" className="btn-primary text-sm" disabled={busy}>
          {busy ? '…' : s.save}
        </button>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind="success">{msg}</Alert>}

      <form id="branding-form" onSubmit={save} className="card br-card">
        <div className="br-card-head">
          <div>
            <h3 className="font-bold text-sm">{s.card_h}</h3>
            <p className="text-xs text-muted mt-0.5">{s.card_sub}</p>
          </div>
          {f.site_domain && <span className="br-domain-badge">{s.active_domain.replace('{d}', f.site_domain)}</span>}
        </div>

        <div className="br-fields">
          {FIELDS.map(([k, label, ltr, area]) => (
            <label key={k} className={'br-fld' + (area ? ' br-fld--wide' : '')}>
              <span className="br-fld-top">
                <span className="label">{t(label)}</span>
                {k === 'site_domain' && <span className="br-hint">{s.domain_hint}</span>}
                {k === 'meta_description' && <span className="br-hint">{s.meta_hint}</span>}
              </span>
              {area ? (
                <textarea className="input" rows={3} dir={ltr ? 'ltr' : undefined}
                  value={f[k] || ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
              ) : (
                <input className="input" dir={ltr ? 'ltr' : undefined}
                  value={f[k] || ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
              )}
            </label>
          ))}
        </div>

        <div className="br-media">
          <span className="label br-media-h">{s.media_h}</span>
          <Upload label={t('logo')} hint={s.logo_hint} current={f.logo} accept="image/*"
            s={s} onFile={(file) => setF((p) => ({ ...p, _logo: file }))} />
          <Upload label={t('favicon')} hint={s.favicon_hint} current={f.favicon} accept="image/x-icon,image/png,image/svg+xml"
            s={s} onFile={(file) => setF((p) => ({ ...p, _favicon: file }))} />
        </div>

        <div className="br-foot">
          <p className="text-xs text-muted flex items-center gap-1.5">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />
            </svg>{t('domain_note')}
          </p>
          <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : t('save')}</button>
        </div>
      </form>
    </div>
  )
}

const CSS = `
.br-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
@media (max-width: 640px) {
  .br-head { position: sticky; top: var(--preview-h, 0px); z-index: 20; margin: -12px -12px 4px; padding: 12px; background: color-mix(in srgb, var(--c-bg) 92%, transparent); backdrop-filter: blur(8px); }
  .br-head .btn-primary { width: 100%; }
  .br-upload { flex-direction: column; align-items: flex-start; }
  .br-foot { flex-direction: column; align-items: stretch; }
  .br-foot .btn-primary { width: 100%; }
}
.br-card { padding: 0; overflow: hidden; }
.br-card-head { padding: 18px 20px; border-bottom: 1px solid var(--c-border); display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }
.br-domain-badge { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px; white-space: nowrap;
  background: color-mix(in srgb, var(--c-success) 14%, transparent); color: var(--c-success-fg); font-family: 'JetBrains Mono', monospace; }

.br-fields { padding: 20px; display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 640px) { .br-fields { grid-template-columns: 1fr 1fr; } .br-fld--wide { grid-column: 1 / -1; } }
.br-fld { display: flex; flex-direction: column; gap: 6px; }
.br-fld .label { font-size: 12px; }
.br-fld-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.br-hint { font-size: 12px; color: var(--c-text-muted); }

.br-media { padding: 4px 20px 20px; border-top: 1px solid var(--c-border); }
.br-media-h { display: block; margin: 14px 0 12px; }
.br-upload { display: flex; gap: 14px; align-items: flex-start; padding: 12px 0; }
.br-upload + .br-upload { border-top: 1px solid var(--c-border); }
.br-upload-thumb { width: 56px; height: 56px; border-radius: 12px; flex-shrink: 0; display: grid; place-items: center; overflow: hidden;
  border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); }
.br-upload-thumb img { width: 100%; height: 100%; object-fit: contain; }
.br-upload-empty { color: var(--c-text-muted); }
.br-hint { font-size: 12px; color: var(--c-text-muted); }
.br-file { font-size: 12px; margin-top: 8px; color: var(--c-text-muted); }
.br-file::file-selector-button { border: 1px solid var(--c-border); background: transparent; color: var(--c-text);
  padding: 5px 12px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; margin-inline-end: 10px; }

.br-foot { padding: 16px 20px; border-top: 1px solid var(--c-border); display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
`
