import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { SESSION_EXPIRED_KEY } from '../lib/api'
import { Alert, Field, PasswordField, Spinner } from '../components/ui'
import { CaspianBrand, CaspianAuthShell } from '../components/caspian'

/* Shared auth wrapper — used by Register / ResetPassword / VerifyEmail too.
   Caspian gets its own shell; Aurora + Royal Frost keep the original. */
function AuthShell({ title, children, hideAdminLink = false }) {
  const { styleKey } = useTheme()
  const { lang, setLang } = useI18n()
  if (styleKey === 'caspian') {
    return <CaspianAuthShell title={title} hideAdminLink={hideAdminLink}>{children}</CaspianAuthShell>
  }
  return (
    <div className="min-h-full aurora grid place-items-center p-4">
      <div className="card w-full max-w-sm">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-bold">{title}</h1>
          <button type="button" className="btn-ghost text-xs"
            onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export { AuthShell }

/* ------------------------------------------------------------------ */

export default function Login() {
  const { styleKey } = useTheme()
  return styleKey === 'caspian' ? <CaspianLogin /> : <LegacyLogin />
}

// never show the backend's raw error text (e.g. a SimpleJWT "token not valid"
// message) on the login form — map the known cases to a friendly string only
function loginErrorText(e, t) {
  const code = e?.response?.data?.code
  if (code === 'invalid_credentials') return t('err_wrong_credentials')
  if (code === 'account_disabled') return t('err_account_disabled')
  return t('login_failed')
}

function useLoginForm() {
  const { t } = useI18n()
  const { login } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ username: '', password: '' })
  const [err, setErr] = useState('')
  const [info, setInfo] = useState(() => {
    try {
      if (sessionStorage.getItem(SESSION_EXPIRED_KEY)) {
        sessionStorage.removeItem(SESSION_EXPIRED_KEY)
        return true
      }
    } catch { /* private browsing / storage blocked */ }
    return false
  })
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(''); setInfo(false)
    try { await login(f.username, f.password); nav('/') }
    catch (e2) { setErr(loginErrorText(e2, t)) }
    finally { setBusy(false) }
  }
  return { f, setF, err, info, busy, submit }
}

function LegacyLogin() {
  const { t } = useI18n()
  const { f, setF, err, info, busy, submit } = useLoginForm()
  return (
    <AuthShell title={t('login')}>
      <form onSubmit={submit} className="space-y-3">
        {info && <Alert kind="warning">{t('session_expired_msg')}</Alert>}
        <Alert>{err}</Alert>
        <Field label={t('username')}>
          <input className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoFocus />
        </Field>
        <PasswordField label={t('password')} value={f.password} autoComplete="current-password"
          onChange={(e) => setF({ ...f, password: e.target.value })} />
        <button className="btn-primary w-full" disabled={busy}>{busy ? <Spinner /> : t('login')}</button>
        <div className="flex justify-between text-sm text-muted">
          <Link to="/register" className="hover:text-primary">{t('register')}</Link>
          <Link to="/reset" className="hover:text-primary">{t('forgot')}</Link>
        </div>
      </form>
    </AuthShell>
  )
}

/* ---- Caspian: split-card login (port of the Stitch redesign screens) ---- */
function CaspianLogin() {
  const { t, lang, setLang } = useI18n()
  const { config } = useTheme()
  const { f, setF, err, info, busy, submit } = useLoginForm()
  const brandFa = config?.site_name_fa || 'کسپین تانل'
  const brandEn = config?.site_name_en || 'caspintunel'
  const brand = lang === 'fa' ? brandFa : brandEn

  const features = [
    ['feat_ramonly_t', 'feat_ramonly_d', ICONS.server],
    ['feat_platforms_t', 'feat_platforms_d', ICONS.devices],
    ['feat_support_t', 'feat_support_d', ICONS.support],
  ]

  return (
    <div className="csp-auth">
      <style>{CSS}</style>

      <header className="csp-auth-top">
        <div className="csp-auth-brand">
          <CaspianBrand logo={config?.logo} size={38} />
          <div>
            <div className="csp-auth-brand-name csp-headline">{brand}</div>
            <div className="csp-auth-brand-sub">{lang === 'fa' ? 'پورتال کاربران' : 'User portal'}</div>
          </div>
        </div>
        <div className="csp-auth-top-actions">
          <button type="button" className="csp-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
          <Link to="/help" className="csp-auth-help">{t('pages')}</Link>
        </div>
      </header>

      <main className="csp-auth-main">
        <div className="csp-auth-card">
          {/* form side */}
          <section className="csp-auth-form">
            <div className="csp-auth-form-head">
              <div>
                <h1 className="csp-headline csp-auth-h1">{t('login_welcome')}</h1>
                <p className="csp-auth-lead">{t('login_sub')}</p>
              </div>
              <span className="csp-auth-badge">
                <span className="csp-ping" />{t('login_secure_badge')}
              </span>
            </div>

            <form onSubmit={submit} className="csp-auth-fields">
              {info && <Alert kind="warning">{t('session_expired_msg')}</Alert>}
              <Alert>{err}</Alert>

              <label className="csp-fld">
                <span className="csp-fld-label">{t('username_field_label')}</span>
                <span className="csp-fld-wrap">
                  <Ico d={ICONS.user} />
                  <input className="csp-fld-input" dir="ltr" autoFocus value={f.username}
                    onChange={(e) => setF({ ...f, username: e.target.value })} />
                </span>
              </label>

              <label className="csp-fld">
                <span className="csp-fld-label csp-fld-label-row">
                  {t('password')}
                  <Link to="/reset" className="csp-link">{t('forgot')}</Link>
                </span>
                <Pw value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} t={t} />
              </label>

              <button type="submit" className="csp-auth-submit" disabled={busy}>
                {busy ? <Spinner /> : <>{t('login_cta')} <Ico d={ICONS.arrow} /></>}
              </button>
            </form>

            <div className="csp-auth-foot">
              <span>{t('need_account')}</span>
              <Link to="/register" className="csp-link csp-link-strong">
                {t('buy_plan_cta')} <Ico d={ICONS.chevron} w={12} />
              </Link>
            </div>
          </section>

          {/* showcase side */}
          <aside className="csp-auth-show">
            <span className="csp-auth-show-blob csp-auth-show-blob-1" />
            <span className="csp-auth-show-blob csp-auth-show-blob-2" />
            <div className="csp-auth-show-inner">
              <h2 className="csp-headline csp-auth-show-h">{t('show_headline')}</h2>
              <p className="csp-auth-show-body">{t('show_body')}</p>
              <div className="csp-auth-feats">
                {features.map(([tk, dk, icon]) => (
                  <div key={tk} className="csp-auth-feat">
                    <span className="csp-auth-feat-ico"><Ico d={icon} /></span>
                    <div>
                      <div className="csp-auth-feat-t">{t(tk)}</div>
                      <div className="csp-auth-feat-d">{t(dk)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </main>

      <footer className="csp-auth-footer">
        <Link to="/rules" className="csp-auth-footer-l">{t('rules')}</Link>
        <span>·</span>
        <Link to="/help" className="csp-auth-footer-l">{t('pages')}</Link>
        <span>·</span>
        <a href="/panel/" className="csp-auth-footer-l">{t('foot_admin')}</a>
      </footer>
    </div>
  )
}

/* password field with the shared show/hide eye */
function Pw({ value, onChange, t }) {
  const [show, setShow] = useState(false)
  return (
    <span className="csp-fld-wrap">
      <Ico d={ICONS.lock} />
      <input className="csp-fld-input csp-fld-input-pw" type={show ? 'text' : 'password'}
        value={value} onChange={onChange} autoComplete="current-password"
        placeholder={t('password')} />
      <button type="button" tabIndex={-1} className="csp-fld-eye"
        onClick={() => setShow((v) => !v)}
        aria-label={show ? t('hide_password') : t('show_password')}>
        <EyeIco off={show} />
      </button>
    </span>
  )
}

function Ico({ d, w = 15 }) {
  return (
    <svg className="csp-ico" width={w} height={w} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}
function EyeIco({ off }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {off ? (<>
        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
        <path d="M6.61 6.61A18.5 18.5 0 0 0 1 12s4 8 11 8a9.26 9.26 0 0 0 5.39-1.61" />
        <line x1="1" y1="1" x2="23" y2="23" />
      </>) : (<>
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" /><circle cx="12" cy="12" r="3" />
      </>)}
    </svg>
  )
}

const ICONS = {
  user: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z',
  lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 018 0v4'],
  arrow: 'M19 12H5m7 7l-7-7 7-7',
  chevron: 'M15 18l-6-6 6-6',
  server: ['M4 4h16v6H4z', 'M4 14h16v6H4z', 'M8 7h.01M8 17h.01'],
  devices: ['M4 5h12v10H4z', 'M16 9h4v9h-6v-3', 'M2 19h12'],
  support: 'M18.36 6.64a9 9 0 11-12.73 0M12 2v10',
}

const CSS = `
.csp-auth {
  min-height: 100%; display: flex; flex-direction: column;
  background: var(--c-bg); color: var(--c-text);
  font-family: 'Vazirmatn', var(--csp-font-ui, ui-sans-serif), system-ui, sans-serif;
}
.csp-auth [dir="rtl"] .csp-ico, [dir="rtl"] .csp-auth .csp-ico { }

/* ---- top bar ---- */
.csp-auth-top {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px clamp(16px, 4vw, 40px);
  border-bottom: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-surface) 80%, transparent);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
  position: sticky; top: 0; z-index: 10;
}
.csp-auth-brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.csp-auth-brand-name { font-size: 15px; font-weight: 800; letter-spacing: -.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.csp-auth-brand-sub { font-size: 11px; color: var(--c-text-muted); margin-top: 1px; }
.csp-auth-top-actions { display: flex; align-items: center; gap: 8px; }
.csp-lang {
  font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 10px;
  border: 1px solid var(--c-border); color: var(--c-text); background: var(--c-surface);
}
.csp-auth-help {
  font-size: 12px; font-weight: 700; padding: 7px 14px; border-radius: 10px;
  color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-primary) 22%, transparent);
}

/* ---- main split card ---- */
.csp-auth-main {
  flex: 1; display: grid; place-items: center; padding: clamp(20px, 5vw, 48px) 16px;
}
.csp-auth-card {
  width: 100%; max-width: 940px; display: grid; grid-template-columns: 7fr 5fr;
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 26px; overflow: hidden;
  box-shadow: 0 24px 60px -18px rgba(15, 23, 42, .22);
}
:root:not(.dark) .csp-auth-card { background: #fff; }
@media (max-width: 860px) { .csp-auth-card { grid-template-columns: 1fr; max-width: 420px; } }

.csp-auth-form { padding: clamp(24px, 4vw, 44px); display: flex; flex-direction: column; }
.csp-auth-form-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 22px; }
.csp-auth-h1 { font-size: clamp(19px, 3vw, 23px); font-weight: 800; line-height: 1.35; }
.csp-auth-lead { font-size: 12px; color: var(--c-text-muted); margin-top: 6px; line-height: 1.7; }
.csp-auth-badge {
  flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
  padding: 5px 11px; border-radius: 999px; font-size: 11px; font-weight: 600;
  color: var(--c-success); background: color-mix(in srgb, var(--c-success) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-success) 26%, transparent);
}
.csp-ping { width: 7px; height: 7px; border-radius: 50%; background: var(--c-success); animation: csp-pp 1.8s ease-in-out infinite; }
@keyframes csp-pp { 50% { opacity: .35; } }

.csp-auth-fields { display: flex; flex-direction: column; gap: 15px; }
.csp-fld { display: flex; flex-direction: column; gap: 7px; }
.csp-fld-label { font-size: 12px; font-weight: 700; color: var(--csp-text-2, var(--c-text)); }
.csp-fld-label-row { display: flex; align-items: center; justify-content: space-between; }
.csp-fld-wrap { position: relative; display: flex; align-items: center; }
.csp-fld-wrap > .csp-ico {
  position: absolute; inset-inline-start: 14px; color: var(--c-text-muted); pointer-events: none;
}
.csp-fld-input {
  width: 100%; padding: 12px 14px; padding-inline-start: 40px; border-radius: 14px;
  border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 6%, transparent);
  color: var(--c-text); font: inherit; font-size: 13px; transition: border-color .15s, box-shadow .15s, background .15s;
}
.csp-fld-input-pw { padding-inline-end: 42px; }
.csp-fld-input::placeholder { color: var(--c-text-muted); }
.csp-fld-input:focus {
  outline: none; border-color: var(--c-primary);
  background: var(--c-surface);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--c-primary) 14%, transparent);
}
.csp-fld-eye {
  position: absolute; inset-inline-end: 6px; display: flex; align-items: center;
  padding: 8px; color: var(--c-text-muted);
}
.csp-fld-eye:hover { color: var(--c-text); }

.csp-auth-submit {
  margin-top: 6px; width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 13px 18px; border-radius: 15px; font-weight: 700; font-size: 13px; color: #fff; border: 0; cursor: pointer;
  background: linear-gradient(135deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 62%, #3f2bd0));
  box-shadow: 0 10px 26px -8px color-mix(in srgb, var(--c-primary) 55%, transparent);
  transition: filter .15s, transform .05s;
}
.csp-auth-submit:hover:not(:disabled) { filter: brightness(1.06); }
.csp-auth-submit:active:not(:disabled) { transform: scale(.99); }
.csp-auth-submit:disabled { opacity: .7; cursor: default; }
[dir="rtl"] .csp-auth-submit .csp-ico { transform: scaleX(-1); }

.csp-link { font-size: 11.5px; font-weight: 600; color: var(--c-primary); }
.csp-link:hover { text-decoration: underline; }
.csp-link-strong { font-weight: 700; display: inline-flex; align-items: center; gap: 3px; }
[dir="rtl"] .csp-link-strong .csp-ico { transform: scaleX(-1); }

.csp-auth-foot {
  margin-top: auto; padding-top: 20px; border-top: 1px solid var(--c-border);
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  font-size: 12px; color: var(--c-text-muted);
}

/* ---- showcase side ---- */
.csp-auth-show {
  position: relative; overflow: hidden; color: #fff; padding: clamp(28px, 4vw, 44px);
  display: flex; flex-direction: column; justify-content: center;
  background: linear-gradient(150deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 55%, #1a1350));
}
@media (max-width: 860px) { .csp-auth-show { display: none; } }
.csp-auth-show-blob { position: absolute; border-radius: 50%; filter: blur(60px); pointer-events: none; }
.csp-auth-show-blob-1 { width: 260px; height: 260px; background: rgba(255,255,255,.14); top: -90px; inset-inline-end: -80px; }
.csp-auth-show-blob-2 { width: 300px; height: 300px; background: color-mix(in srgb, var(--c-secondary) 40%, transparent); bottom: -110px; inset-inline-start: -90px; }
.csp-auth-show-inner { position: relative; z-index: 1; }
.csp-auth-show-h { font-size: 20px; font-weight: 800; line-height: 1.5; letter-spacing: -.01em; }
.csp-auth-show-body { font-size: 12px; line-height: 1.9; opacity: .9; margin: 12px 0 22px; }
.csp-auth-feats { display: flex; flex-direction: column; gap: 12px; }
.csp-auth-feat {
  display: flex; align-items: flex-start; gap: 11px; padding: 12px;
  border-radius: 16px; background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.12);
}
.csp-auth-feat-ico {
  flex-shrink: 0; width: 32px; height: 32px; display: grid; place-items: center; border-radius: 10px;
  background: rgba(255,255,255,.18);
}
.csp-auth-feat-t { font-size: 12px; font-weight: 700; }
.csp-auth-feat-d { font-size: 10.5px; opacity: .82; margin-top: 3px; line-height: 1.6; }

/* ---- footer ---- */
.csp-auth-footer {
  display: flex; align-items: center; justify-content: center; gap: 10px; flex-wrap: wrap;
  padding: 16px; border-top: 1px solid var(--c-border);
  font-size: 11px; color: var(--c-text-muted);
}
.csp-auth-footer-l:hover { color: var(--c-primary); }
`
