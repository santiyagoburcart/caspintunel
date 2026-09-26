import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { SESSION_EXPIRED_KEY } from '../lib/api'
import { USER_URL } from '../lib/site'
import { Alert, Field, Spinner } from '../components/ui'

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

function useLogin() {
  const { t } = useI18n()
  const { login } = useAuth()
  const go = useNavigate()
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
    e.preventDefault(); setBusy(true); setErr(''); setInfo(false)
    try { await login(f.username, f.password); go('/') }
    catch (e2) { setErr(loginErrorText(e2, t)) } finally { setBusy(false) }
  }
  return { f, setF, err, info, busy, submit }
}

/* ================= Legacy (Aurora / Frost) — unchanged ================= */
function LegacyLogin() {
  const { t, lang, setLang } = useI18n()
  const { f, setF, err, info, busy, submit } = useLogin()
  return (
    <div className="min-h-full aurora grid place-items-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-3">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">{t('admin_panel')}</h1>
          <button type="button" className="btn-ghost text-xs" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
        </div>
        {info && <Alert kind="warning">{t('session_expired_msg')}</Alert>}
        <Alert>{err}</Alert>
        <Field label={t('username')}>
          <input className="input" dir="ltr" autoFocus value={f.username} autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false}
            onChange={(e) => setF({ ...f, username: e.target.value })} />
        </Field>
        <Field label={t('password')}>
          <input className="input" dir="ltr" type="password" autoComplete="current-password" value={f.password}
            onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        <button className="btn-primary w-full" disabled={busy}>{busy ? <Spinner /> : t('login')}</button>
      </form>
    </div>
  )
}

/* ================= Caspian — Stitch admin-login port ================= */
const I = {
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 018 0v4'],
  user: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z',
  warn: 'M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  finger: 'M12 11c0 3-1 5.5-3 7M8.5 7A5 5 0 0117 9c0 4-1 6-1 9M6 12a6 6 0 0110-4.5M12 17v.5M12 14c0 2-.5 3.5-1.5 5',
  back: 'M15 19l-7-7 7-7',
}
function LI({ d, w = 15 }) {
  return (
    <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}
function EyeGlyph({ off }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {off ? (<>
        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
        <path d="M6.61 6.61A18.5 18.5 0 0 0 1 12s4 8 11 8a9.26 9.26 0 0 0 5.39-1.61" /><line x1="1" y1="1" x2="23" y2="23" />
      </>) : (<><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" /><circle cx="12" cy="12" r="3" /></>)}
    </svg>
  )
}

function CaspianLogin() {
  const { t, lang, setLang } = useI18n()
  const { config } = useTheme()
  const { f, setF, err, info, busy, submit } = useLogin()
  const [show, setShow] = useState(false)
  const brand = lang === 'fa' ? (config?.site_name_fa || 'کسپین تانل') : (config?.site_name_en || 'caspintunel')

  return (
    <div className="al">
      <style>{CSS}</style>
      <span className="al-glow al-glow-1" />
      <span className="al-glow al-glow-2" />

      <header className="al-top">
        <div className="al-brand">
          <span className="al-brand-ico"><LI d={I.lock} w={16} /></span>
          <div>
            <div className="al-brand-name">
              {brand}<span className="al-badge">{t('admin_panel')}</span>
            </div>
            <div className="al-brand-sub">{t('restricted_area')}</div>
          </div>
        </div>
        <div className="al-top-r">
          <button type="button" className="al-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
          <a href={USER_URL} className="al-portal">{t('back_to_user_portal')}</a>
        </div>
      </header>

      <main className="al-main">
        <div className="al-head">
          <span className="al-shield"><LI d={I.shield} w={26} /></span>
          <h1 className="csp-headline">{t('admin_login_h1')}</h1>
          <p>{t('admin_login_sub')}</p>
        </div>

        <div className="al-card">
          <span className="al-card-line" />
          <div className="al-warn">
            <LI d={I.warn} w={16} />
            <span>{t('admin_sec_warn')}</span>
          </div>

          <form onSubmit={submit} className="al-form">
            {info && <Alert kind="warning">{t('session_expired_msg')}</Alert>}
            <Alert>{err}</Alert>

            <label className="al-fld">
              <span className="al-fld-label">{t('admin_id')}</span>
              <span className="al-fld-wrap">
                <LI d={I.user} />
                <input className="al-input mono" dir="ltr" autoFocus value={f.username} autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false}
                  onChange={(e) => setF({ ...f, username: e.target.value })} placeholder="root_admin" />
              </span>
            </label>

            <label className="al-fld">
              <span className="al-fld-label">{t('password')}</span>
              <span className="al-fld-wrap">
                <LI d={I.lock} />
                <input className="al-input al-input-pw" dir="ltr" type={show ? 'text' : 'password'} value={f.password}
                  onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="current-password" />
                <button type="button" tabIndex={-1} className="al-eye" onClick={() => setShow((v) => !v)}
                  aria-label={show ? t('hide_password') : t('show_password')}>
                  <EyeGlyph off={show} />
                </button>
              </span>
            </label>

            <button type="submit" className="al-cta" disabled={busy}>
              {busy ? <Spinner /> : <><LI d={I.finger} w={16} />{t('admin_login_cta')}</>}
            </button>
          </form>

          <div className="al-foot">
            <span><LI d={I.shield} w={13} />{t('ddos_protected')}</span>
            <span className="mono">TLS 1.3 / AES-256</span>
          </div>
        </div>
      </main>
    </div>
  )
}

const CSS = `
.al {
  min-height: 100%; display: flex; flex-direction: column; position: relative; overflow: hidden;
  background: var(--c-bg); color: var(--c-text);
  font-family: 'Vazirmatn', var(--csp-font-ui, ui-sans-serif), system-ui, sans-serif;
}
.al .mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.al-glow { position: fixed; border-radius: 50%; filter: blur(80px); pointer-events: none; }
.al-glow-1 { width: 700px; height: 360px; top: -160px; left: 50%; transform: translateX(-50%); background: color-mix(in srgb, var(--c-primary) 16%, transparent); }
.al-glow-2 { width: 380px; height: 280px; bottom: -120px; inset-inline-start: 12%; background: color-mix(in srgb, var(--c-danger) 12%, transparent); }

.al-top {
  position: sticky; top: var(--preview-h, 0px); z-index: 10; display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 13px clamp(16px, 4vw, 40px); border-bottom: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-surface) 78%, transparent);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
}
.al-brand { display: flex; align-items: center; gap: 11px; min-width: 0; }
.al-brand-ico {
  width: 34px; height: 34px; flex-shrink: 0; display: grid; place-items: center; border-radius: 10px;
  background: color-mix(in srgb, var(--c-danger) 14%, transparent); color: var(--c-danger-fg);
  border: 1px solid color-mix(in srgb, var(--c-danger) 26%, transparent);
}
.al-brand-name { display: flex; align-items: center; gap: 7px; font-size: 14px; font-weight: 800; }
.al-badge {
  padding: 1px 7px; border-radius: 6px; font-size: 12px; font-weight: 700;
  color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-danger) 26%, transparent);
}
.al-brand-sub { font-size: 12px; color: var(--c-text-muted); margin-top: 1px; }
.al-top-r { display: flex; align-items: center; gap: 8px; }
.al-lang { font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 10px; cursor: pointer; border: 1px solid var(--c-border); color: var(--c-text); background: var(--c-surface); }
.al-portal { font-size: 12px; font-weight: 600; padding: 7px 13px; border-radius: 10px; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.al-portal:hover { color: var(--c-text); }

.al-main { flex: 1; display: grid; place-items: center; padding: clamp(24px, 6vw, 60px) 16px; position: relative; z-index: 1; width: 100%; }
.al-head { text-align: center; margin-bottom: 20px; max-width: 380px; }
.al-shield {
  display: inline-grid; place-items: center; width: 60px; height: 60px; border-radius: 18px; margin-bottom: 12px;
  color: var(--c-danger-fg); background: var(--c-surface); border: 1px solid var(--c-border);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--c-danger) 8%, transparent);
}
.al-head h1 { font-size: 22px; font-weight: 800; }
.al-head p { font-size: 12px; color: var(--c-text-muted); margin-top: 6px; line-height: 1.7; }

.al-card {
  position: relative; width: 100%; max-width: 400px; padding: 24px; border-radius: 24px; overflow: hidden;
  background: var(--c-surface); border: 1px solid var(--c-border);
  box-shadow: 0 30px 70px -16px rgba(0,0,0,.4);
}
:root:not(.dark) .al-card { background: #fff; }
.al-card-line { position: absolute; top: 0; inset-inline: 0; height: 3px; background: linear-gradient(90deg, var(--c-primary), var(--c-secondary), var(--c-danger)); }

.al-warn {
  display: flex; align-items: flex-start; gap: 9px; padding: 11px 13px; border-radius: 14px; margin: 6px 0 16px;
  font-size: 12px; line-height: 1.7;
  color: var(--c-danger-fg);
  background: color-mix(in srgb, var(--c-danger) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-danger) 22%, transparent);
}
.al-warn svg { flex-shrink: 0; margin-top: 1px; }

.al-form { display: flex; flex-direction: column; gap: 13px; }
.al-fld { display: flex; flex-direction: column; gap: 6px; }
.al-fld-label { font-size: 12px; font-weight: 700; color: var(--csp-text-2, var(--c-text)); }
.al-fld-wrap { position: relative; display: flex; align-items: center; }
.al-fld-wrap > svg { position: absolute; inset-inline-start: 13px; color: var(--c-text-muted); pointer-events: none; }
.al-input {
  width: 100%; padding: 12px 14px; padding-inline-start: 40px; border-radius: 14px;
  border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 7%, transparent);
  color: var(--c-text); font: inherit; font-size: 12.5px; transition: border-color .15s, box-shadow .15s, background .15s;
}
.al-input.mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.al-input-pw { padding-inline-end: 42px; }
.al-input::placeholder { color: var(--c-text-muted); }
.al-input:focus {
  outline: none; border-color: var(--c-primary); background: var(--c-surface);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--c-primary) 14%, transparent);
}
.al-eye { position: absolute; inset-inline-end: 6px; display: flex; align-items: center; padding: 8px; color: var(--c-text-muted); }
.al-eye:hover { color: var(--c-text); }

.al-cta {
  margin-top: 4px; width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 13px 18px; border-radius: 15px; border: 0; cursor: pointer; font-weight: 700; font-size: 12.5px; color: #fff;
  background: linear-gradient(135deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 55%, var(--c-danger)));
  box-shadow: 0 12px 28px -10px color-mix(in srgb, var(--c-primary) 55%, transparent);
  transition: filter .15s, transform .05s;
}
.al-cta:hover:not(:disabled) { filter: brightness(1.07); }
.al-cta:active:not(:disabled) { transform: scale(.99); }
.al-cta:disabled { opacity: .7; cursor: default; }

.al-foot {
  margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--c-border);
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  font-size: 12px; color: var(--c-text-muted);
}
.al-foot span { display: inline-flex; align-items: center; gap: 5px; }
.al-foot span:first-child svg { color: var(--c-success-fg); }
`
