import { useState } from 'react'
import { api, apiError, tokens } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { Alert, Copyable, Field, PasswordField, PhoneInput, Spinner, Toggle, usePhoneRule } from '../components/ui'
import { localizeError } from '../lib/phone'
import { useToast } from '../components/Toast'
import { copyToClipboard } from '../lib/clipboard'

export default function Profile() {
  const { styleKey } = useTheme()
  return styleKey === 'caspian' ? <CaspianProfile /> : <LegacyProfile />
}

/** Copy + toast only once the copy really happened (the helper itself opens a
 * manual-copy sheet when every automatic method fails). */
async function copyInvite(text, t, toast, key = 'invite_copied') {
  if (await copyToClipboard(text)) toast.success(t(key))
}

/* ================= Legacy (Aurora / Frost) ================= */
function LegacyProfile() {
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked } = useTheme()
  const { user, refreshMe } = useAuth()
  const toast = useToast()

  const [f, setF] = useState({ name: user?.name || '', phone: user?.phone || '', email: user?.email || '' })
  const [infoBusy, setInfoBusy] = useState(false)
  const [infoMsg, setInfoMsg] = useState(''); const [infoErr, setInfoErr] = useState('')
  const dirty = f.name !== (user?.name || '') || f.phone !== (user?.phone || '') || f.email !== (user?.email || '')

  const [pw, setPw] = useState({ current_password: '', new_password: '', confirm: '' })
  const [msg, setMsg] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)

  const inviteLink = user?.referral_code ? `${window.location.origin}/register?ref=${user.referral_code}` : ''
  const st = strength(pw.new_password)
  const stLabel = [t('pw_weak'), t('pw_weak'), t('pw_fair'), t('pw_strong')][st]

  const phoneRule = usePhoneRule()
  const saveInfo = async (e) => {
    e.preventDefault(); setInfoErr(''); setInfoMsg('')
    const phoneErr = phoneRule.error(f.phone)
    if (phoneErr) { setInfoErr(phoneErr); return }
    setInfoBusy(true)
    try {
      await api.patch('/auth/me/', { name: f.name, phone: f.phone, email: f.email || null })
      await refreshMe()
      setInfoMsg(t('saved_ok'))
    } catch (e2) { setInfoErr(localizeError(apiError(e2), lang)) } finally { setInfoBusy(false) }
  }
  const changePw = async (e) => {
    e.preventDefault(); setErr(''); setMsg('')
    if (pw.new_password !== pw.confirm) { setErr(t('pw_mismatch')); return }
    setBusy(true)
    try {
      const { data: pwRes } = await api.post('/auth/password/change/', { current_password: pw.current_password, new_password: pw.new_password })
      // the new password revokes all old tokens — keep this session on the fresh pair
      if (pwRes?.access) tokens.set(pwRes)
      setMsg(t('pw_changed')); setPw({ current_password: '', new_password: '', confirm: '' })
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  const resend = async () => {
    try { await api.post('/auth/email/verify/resend/'); setInfoMsg(t('verify_sent')) }
    catch (e2) { setInfoErr(apiError(e2)) }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('profile')}</h1>

      <form onSubmit={saveInfo} className="card space-y-3">
        <h2 className="font-bold">{t('account_info')}</h2>
        <Alert>{infoErr}</Alert>
        <Alert kind="success">{infoMsg}</Alert>
        <div className="flex items-center justify-between">
          <span className="text-muted">{t('username')}</span>
          <span className="flex items-center gap-2"><code dir="ltr">{user?.username}</code><Copyable text={user?.username || ''} /></span>
        </div>
        <Field label={t('name')}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" /></Field>
        <Field label={t('phone') + (phoneRule.required ? ' *' : '')}>
          <PhoneInput value={f.phone} onChange={(v) => setF({ ...f, phone: v })} />
        </Field>
        <Field label={t('email')}>
          <input className="input" type="email" dir="ltr" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" inputMode="email" autoCapitalize="none" spellCheck={false} />
          {user?.email && !user?.email_verified && <button type="button" className="btn-ghost text-xs mt-1" onClick={resend}>{t('verify_email')}</button>}
        </Field>
        <button className="btn-primary" disabled={infoBusy || !dirty}>{infoBusy ? <Spinner /> : t('save_changes')}</button>
      </form>

      <div className="card space-y-2">
        <h2 className="font-bold">{t('referral')}</h2>
        <div className="flex items-center justify-between">
          <span className="text-muted">{t('referral')}</span>
          <span className="flex items-center gap-2"><code>{user?.referral_code}</code><Copyable text={user?.referral_code || ''} /></span>
        </div>
        <div className="flex justify-between"><span className="text-muted">{t('referral_count')}</span><span>{user?.referral_count}</span></div>
        {inviteLink && (
          <button type="button" className="btn-ghost w-full text-sm" onClick={() => copyInvite(inviteLink, t, toast)}>
            {t('copy_invite')}
          </button>
        )}
      </div>

      <div className="card">
        {!locked && (
          <div className="toggle-row hidden md:flex">
            <span>{t('theme')}: {mode === 'dark' ? t('dark') : t('light')}</span>
            <Toggle checked={mode === 'dark'} onChange={toggle} label={t('theme')} />
          </div>
        )}
        <div className="toggle-row">
          <span>{t('language')}: {lang === 'fa' ? 'فارسی' : 'English'}</span>
          <Toggle checked={lang === 'en'} onChange={(v) => setLang(v ? 'en' : 'fa')} label={t('language')} />
        </div>
      </div>

      <form onSubmit={changePw} className="card space-y-3">
        <h2 className="font-bold">{t('change_password')}</h2>
        <Alert>{err}</Alert>
        <Alert kind="success">{msg}</Alert>
        <PasswordField label={t('current_password')} value={pw.current_password} autoComplete="current-password"
          onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
        <div>
          <PasswordField label={t('new_password')} value={pw.new_password} autoComplete="new-password"
            onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
          {pw.new_password && <p className="text-xs text-muted mt-1">{t('pw_strength')}: {stLabel}</p>}
        </div>
        <PasswordField label={t('confirm_password')} value={pw.confirm} autoComplete="new-password"
          onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
        <button className="btn-primary" disabled={busy}>{busy ? <Spinner /> : t('save')}</button>
      </form>
    </div>
  )
}

/* ================= Caspian — Stitch redesign port ================= */
const P = {
  gear: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.2.6.74 1.05 1.36 1.15H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z',
  user: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z',
  lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 018 0v4'],
  check: 'M5 13l4 4L19 7',
  verified: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'M9 12l2 2 4-4'],
  sun: ['M12 3v2M12 19v2M5 5l1.5 1.5M17.5 17.5L19 19M3 12h2M19 12h2M5 19l1.5-1.5M17.5 6.5L19 5', 'M12 8a4 4 0 100 8 4 4 0 000-8z'],
  moon: 'M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z',
  globe: ['M12 3a9 9 0 100 18 9 9 0 000-18z', 'M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18'],
  copy: ['M8 8h10v12H8z', 'M6 16H4V4h12v2'],
  gift: ['M4 11h16v10H4z', 'M2 7h20v4H2z', 'M12 7v14', 'M12 7a3 3 0 10-3-3M12 7a3 3 0 013-3'],
  share: 'M8.6 13.5l6.8 4M15.4 6.5l-6.8 4M18 8a3 3 0 100-6 3 3 0 000 6zM6 15a3 3 0 100-6 3 3 0 000 6zM18 22a3 3 0 100-6 3 3 0 000 6z',
  mail: ['M4 5h16v14H4z', 'M4 6l8 7 8-7'],
  support: 'M18.4 6.6a9 9 0 11-12.8 0M12 2v8',
}
function PI({ d, w = 18 }) {
  return (
    <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}
// numbers are always shown with Latin digits (both languages)
// eslint-disable-next-line no-unused-vars
const fnum = (n, lang) => String(n)

function EyeInput({ label, value, onChange, placeholder, autoComplete }) {
  const [show, setShow] = useState(false)
  const { t } = useI18n()
  return (
    <label className="csp-pf-fld">
      <span className="csp-pf-fld-label">{label}</span>
      <span className="csp-pf-fld-wrap">
        <input className="csp-pf-input" type={show ? 'text' : 'password'} value={value} onChange={onChange}
          placeholder={placeholder} autoComplete={autoComplete} />
        <button type="button" tabIndex={-1} className="csp-pf-eye" onClick={() => setShow((v) => !v)}
          aria-label={show ? t('hide_password') : t('show_password')}>
          <EyeGlyph off={show} />
        </button>
      </span>
    </label>
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

function strength(pw) {
  let s = 0
  if (pw.length >= 6) s++
  if (pw.length >= 10 && /\d/.test(pw)) s++
  if (s >= 2 && /[^A-Za-z0-9]/.test(pw)) s++
  return s
}

function CaspianProfile() {
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const { user, refreshMe } = useAuth()
  const toast = useToast()
  const inviteLink = user?.referral_code
    ? `${window.location.origin}/register?ref=${user.referral_code}`
    : ''

  const [f, setF] = useState({ name: user?.name || '', phone: user?.phone || '', email: user?.email || '' })
  const [savedBusy, setSavedBusy] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [savedErr, setSavedErr] = useState('')

  const [pw, setPw] = useState({ current_password: '', new_password: '', confirm: '' })
  const [pwBusy, setPwBusy] = useState(false)
  const [pwMsg, setPwMsg] = useState('')
  const [pwErr, setPwErr] = useState('')

  const dirty = f.name !== (user?.name || '') || f.phone !== (user?.phone || '') || f.email !== (user?.email || '')

  const phoneRule = usePhoneRule()
  const saveInfo = async (e) => {
    e.preventDefault(); setSavedErr(''); setSavedMsg('')
    const phoneErr = phoneRule.error(f.phone)
    if (phoneErr) { setSavedErr(phoneErr); return }
    setSavedBusy(true)
    try {
      await api.patch('/auth/me/', { name: f.name, phone: f.phone, email: f.email || null })
      await refreshMe()
      setSavedMsg(t('saved_ok'))
    } catch (e2) { setSavedErr(localizeError(apiError(e2), lang)) } finally { setSavedBusy(false) }
  }
  const resend = async () => {
    setSavedErr(''); setSavedMsg('')
    try { await api.post('/auth/email/verify/resend/'); setSavedMsg(t('verify_sent')) }
    catch (e2) { setSavedErr(apiError(e2)) }
  }
  const changePw = async (e) => {
    e.preventDefault(); setPwErr(''); setPwMsg('')
    if (pw.new_password !== pw.confirm) { setPwErr(t('pw_mismatch')); return }
    setPwBusy(true)
    try {
      const { data: pwRes } = await api.post('/auth/password/change/', { current_password: pw.current_password, new_password: pw.new_password })
      // the new password revokes all old tokens — keep this session on the fresh pair
      if (pwRes?.access) tokens.set(pwRes)
      setPwMsg(t('pw_changed')); setPw({ current_password: '', new_password: '', confirm: '' })
    } catch (e2) { setPwErr(apiError(e2)) } finally { setPwBusy(false) }
  }

  const verified = !user?.email || user?.email_verified
  const st = strength(pw.new_password)
  const stLabel = [t('pw_weak'), t('pw_weak'), t('pw_fair'), t('pw_strong')][st]
  const avatarTxt = (user?.name || user?.username || '?').slice(0, 2).toUpperCase()

  return (
    <div className="csp-pf">
      <style>{CSS}</style>

      <header className="csp-pf-head">
        <div>
          <div className="csp-pf-title">
            <span className="csp-pf-title-ico"><PI d={P.user} w={20} /></span>
            <h1 className="csp-headline">{t('prof_h1')}</h1>
            <span className="csp-pf-uid mono-num">UID-{user?.id}</span>
          </div>
          <p className="csp-pf-lead">{t('prof_lead')}</p>
        </div>
        <div className="csp-pf-head-r">
          <span className={'csp-pf-status' + (verified ? '' : ' warn')}>
            <i />{verified ? t('account_verified') : t('account_unverified')}
          </span>
          {config?.support_telegram && (
            <a href={`https://t.me/${String(config.support_telegram).replace(/^@/, '')}`} target="_blank" rel="noreferrer"
              className="csp-pf-support"><PI d={P.support} w={15} />{t('online_support') || t('pages')}</a>
          )}
        </div>
      </header>

      <div className="csp-pf-grid">
        <div className="csp-pf-col">
          {/* account info */}
          <form onSubmit={saveInfo} className="csp-pf-card">
            <div className="csp-pf-account-top">
              <span className="csp-pf-avatar">{avatarTxt}</span>
              <div className="csp-pf-account-id">
                <div className="csp-pf-account-name">
                  <b dir="ltr">{user?.username}</b>
                  <Copyable text={user?.username || ''} />
                  {user?.telegram_username && <span className="csp-pf-tg">{t('tg_account')}</span>}
                </div>
                <span className="csp-pf-account-sub">{t('account_info')}</span>
              </div>
              {verified && (
                <span className="csp-pf-verified"><PI d={P.verified} w={13} />{t('identity_verified')}</span>
              )}
            </div>

            <div className="csp-pf-fields">
              <label className="csp-pf-fld">
                <span className="csp-pf-fld-label">{t('name')}</span>
                <input className="csp-pf-input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" />
              </label>
              <label className="csp-pf-fld">
                <span className="csp-pf-fld-label">{t('phone') + (phoneRule.required ? ' *' : '')}</span>
                <PhoneInput className="csp-pf-input mono-num" hintClassName="csp-pf-fld-hint"
                  value={f.phone} onChange={(v) => setF({ ...f, phone: v })} />
              </label>
              <label className="csp-pf-fld">
                <span className="csp-pf-fld-label">
                  {t('email')}
                  {user?.email && !user?.email_verified && (
                    <button type="button" className="csp-pf-link" onClick={resend}>{t('verify_email')}</button>
                  )}
                </span>
                <span className="csp-pf-fld-wrap">
                  <PI d={P.mail} w={15} />
                  <input className="csp-pf-input csp-pf-input--icon" type="email" dir="ltr" value={f.email} autoComplete="email" inputMode="email" autoCapitalize="none" spellCheck={false}
                    onChange={(e) => setF({ ...f, email: e.target.value })} placeholder={t('add_email')} aria-label={t('email')} />
                </span>
              </label>

              <div className="csp-pf-kv">
                <div>
                  <span className="csp-pf-kv-k">{t('referral')}</span>
                  <span className="csp-pf-kv-note">{t('ref_gift_note')}</span>
                </div>
                <button type="button" className="csp-pf-refcode" onClick={() => copyInvite(user?.referral_code, t, toast, 'copied')}>
                  <PI d={P.copy} w={15} /><span className="mono-num">{user?.referral_code || '—'}</span>
                </button>
              </div>
              <div className="csp-pf-kv">
                <div>
                  <span className="csp-pf-kv-k">{t('referral_count')}</span>
                  <span className="csp-pf-kv-note">{t('ref_count_note')}</span>
                </div>
                <span className="csp-pf-refcount"><b className="mono-num">{fnum(user?.referral_count ?? 0, lang)}</b> {t('people')}</span>
              </div>
            </div>

            <Alert>{savedErr}</Alert>
            <Alert kind="success">{savedMsg}</Alert>
            <div className="csp-pf-actions">
              <button type="submit" className="csp-pf-save" disabled={savedBusy || !dirty}>
                <PI d={P.check} w={15} />{savedBusy ? '…' : t('save_changes')}
              </button>
            </div>
          </form>

          {/* security */}
          <form onSubmit={changePw} className="csp-pf-card">
            <div className="csp-pf-card-h"><span className="csp-pf-card-h-ico"><PI d={P.lock} w={18} /></span><h2 className="csp-headline">{t('change_password')}</h2></div>
            <Alert>{pwErr}</Alert>
            <Alert kind="success">{pwMsg}</Alert>
            <div className="csp-pf-fields">
              <EyeInput label={t('current_password')} value={pw.current_password} autoComplete="current-password"
                onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
              <div>
                <EyeInput label={t('new_password')} value={pw.new_password} autoComplete="new-password"
                  onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
                {pw.new_password && (
                  <div className="csp-pf-strength">
                    <div className="csp-pf-strength-bars">
                      {[0, 1, 2].map((i) => (
                        <span key={i} className={i < st ? 'on s' + st : ''} />
                      ))}
                    </div>
                    <span className="csp-pf-strength-l">{t('pw_strength')}: {stLabel}</span>
                  </div>
                )}
              </div>
              <EyeInput label={t('confirm_password')} value={pw.confirm} autoComplete="new-password"
                onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
            </div>
            <div className="csp-pf-actions">
              <button type="submit" className="csp-pf-save" disabled={pwBusy}>
                <PI d={P.check} w={15} />{pwBusy ? '…' : t('save')}
              </button>
            </div>
          </form>
        </div>

        <div className="csp-pf-col">
          {/* preferences */}
          <div className="csp-pf-card">
            <div className="csp-pf-card-h"><span className="csp-pf-card-h-ico"><PI d={P.gear} w={18} /></span><h2 className="csp-headline">{t('preferences')}</h2></div>
            <div className="csp-pf-prefs">
              {!locked && (
                <div className="csp-pf-pref csp-pf-pref--theme">
                  <span className="csp-pf-pref-ico"><PI d={mode === 'dark' ? P.moon : P.sun} w={17} /></span>
                  <div className="csp-pf-pref-txt">
                    <span>{t('theme')}</span>
                    <small>{mode === 'dark' ? t('dark') : t('light')}</small>
                  </div>
                  <Toggle checked={mode === 'dark'} onChange={toggle} label={t('theme')} />
                </div>
              )}
              <div className="csp-pf-pref">
                <span className="csp-pf-pref-ico"><PI d={P.globe} w={17} /></span>
                <div className="csp-pf-pref-txt">
                  <span>{t('language')}</span>
                  <small>{lang === 'fa' ? 'فارسی' : 'English'}</small>
                </div>
                <Toggle checked={lang === 'en'} onChange={(v) => setLang(v ? 'en' : 'fa')} label={t('language')} />
              </div>
            </div>
          </div>

          {/* referral banner */}
          <div className="csp-pf-refbanner">
            <div className="csp-pf-refbanner-h"><PI d={P.gift} w={18} />{t('ref_program_t')}</div>
            <p>{t('ref_program_d')}</p>
            <div className="csp-pf-refbanner-code">
              <span className="mono-num">{user?.referral_code || '—'}</span>
              <Copyable text={user?.referral_code || ''} />
            </div>
            {inviteLink && (
              <button type="button" className="csp-pf-refbanner-btn"
                onClick={() => copyInvite(inviteLink, t, toast)}>
                <PI d={P.share} w={15} />{t('copy_invite')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

const CSS = `
.csp-pf { display: flex; flex-direction: column; gap: 20px; }
.csp-pf-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.csp-pf-title { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.csp-pf-title-ico { width: 32px; height: 32px; flex-shrink: 0; display: grid; place-items: center; border-radius: 10px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary-fg); }
.csp-pf-title h1 { font-size: clamp(18px, 3vw, 24px); font-weight: 800; }
.csp-pf-uid { padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.csp-pf-lead { font-size: 12.5px; color: var(--c-text-muted); margin-top: 6px; line-height: 1.7; }
.csp-pf-head-r { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.csp-pf-status { display: inline-flex; align-items: center; gap: 6px; padding: 8px 13px; border-radius: 12px; font-size: 12px; font-weight: 700; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 12%, transparent); }
.csp-pf-status.warn { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); }
.csp-pf-status i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.csp-pf-support { display: inline-flex; align-items: center; gap: 6px; padding: 8px 13px; border-radius: 12px; font-size: 12px; font-weight: 700; color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }

.csp-pf-grid { display: grid; grid-template-columns: 7fr 5fr; gap: 16px; align-items: start; }
@media (max-width: 900px) { .csp-pf-grid { grid-template-columns: 1fr; } }
.csp-pf-col { display: flex; flex-direction: column; gap: 16px; }

.csp-pf-card {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 18px; padding: 18px;
  display: flex; flex-direction: column; gap: 14px;
}
:root:not(.dark) .csp-pf-card { background: #fff; }
[data-theme-style="caspian"].dark .csp-pf-card { box-shadow: -6px -6px 14px rgba(255,255,255,.02), 6px 6px 18px rgba(0,0,0,.5); }
.csp-pf-card-h { display: flex; align-items: center; gap: 8px; }
.csp-pf-card-h-ico { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 9px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary-fg); }
.csp-pf-card-h h2 { font-size: 14px; font-weight: 800; }

.csp-pf-account-top { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.csp-pf-avatar {
  width: 52px; height: 52px; flex-shrink: 0; display: grid; place-items: center; border-radius: 16px; font-size: 16px; font-weight: 800; color: #fff;
  background: linear-gradient(135deg, var(--c-primary), #0B1B36);
}
.csp-pf-account-id { min-width: 0; }
.csp-pf-account-name { display: flex; align-items: center; gap: 6px; }
.csp-pf-account-name b { font-size: 14px; font-weight: 800; }
.csp-pf-tg { padding: 1px 7px; border-radius: 6px; font-size: 12px; font-weight: 700; background: color-mix(in srgb, var(--c-secondary) 20%, transparent); color: var(--c-secondary-fg); }
.csp-pf-account-sub { font-size: 12px; color: var(--c-text-muted); }
.csp-pf-verified { margin-inline-start: auto; display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 12%, transparent); }

.csp-pf-fields { display: flex; flex-direction: column; gap: 12px; }
.csp-pf-fld { display: flex; flex-direction: column; gap: 6px; }
.csp-pf-fld-label { font-size: 12px; font-weight: 700; color: var(--csp-text-2, var(--c-text)); display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.csp-pf-fld-hint { font-size: 12px; line-height: 1.7; color: var(--c-text-muted); margin-top: -2px; }
.csp-pf-fld-wrap { position: relative; display: flex; align-items: center; }
.csp-pf-fld-wrap > svg { position: absolute; inset-inline-start: 12px; color: var(--c-text-muted); pointer-events: none; }
.csp-pf-input {
  width: 100%; padding: 11px 13px; border-radius: 12px; border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); color: var(--c-text); font: inherit; font-size: 13px;
  transition: border-color .15s, box-shadow .15s;
}
.csp-pf-input--icon { padding-inline-start: 38px; }
.csp-pf-input:focus { outline: none; border-color: var(--c-primary); box-shadow: 0 0 0 4px color-mix(in srgb, var(--c-primary) 14%, transparent); background: var(--c-surface); }
.csp-pf-eye { position: absolute; inset-inline-end: 6px; display: flex; align-items: center; padding: 8px; color: var(--c-text-muted); }
.csp-pf-link { font-size: 12px; font-weight: 700; color: var(--c-primary-fg); }
.csp-pf-link:hover { text-decoration: underline; }

.csp-pf-kv { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-top: 12px; border-top: 1px solid var(--c-border); }
.csp-pf-kv-k { display: block; font-size: 12.5px; font-weight: 600; }
.csp-pf-kv-note { display: block; font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }
.csp-pf-refcode { display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border-radius: 12px; cursor: pointer; border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); color: var(--c-primary-fg); font-weight: 800; letter-spacing: .08em; }
.csp-pf-refcode:hover { border-color: var(--c-primary); }
.csp-pf-refcount b { font-size: 18px; font-weight: 800; }
.csp-pf-refcount { font-size: 12px; color: var(--c-text-muted); }

.csp-pf-strength { display: flex; align-items: center; gap: 8px; margin-top: 7px; }
.csp-pf-strength-bars { display: flex; gap: 3px; flex: 1; }
.csp-pf-strength-bars span { flex: 1; height: 5px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
.csp-pf-strength-bars span.on.s1 { background: var(--c-danger); }
.csp-pf-strength-bars span.on.s2 { background: var(--c-warning); }
.csp-pf-strength-bars span.on.s3 { background: var(--c-success); }
.csp-pf-strength-l { font-size: 12px; color: var(--c-text-muted); white-space: nowrap; }

.csp-pf-actions { display: flex; justify-content: flex-end; }
.csp-pf-save {
  display: inline-flex; align-items: center; gap: 6px; padding: 10px 20px; border-radius: 12px; border: 0; cursor: pointer;
  font-size: 12.5px; font-weight: 700; color: #fff; background: var(--c-primary);
  box-shadow: 0 6px 16px -6px color-mix(in srgb, var(--c-primary) 55%, transparent); transition: filter .15s;
}
.csp-pf-save:hover:not(:disabled) { filter: brightness(1.06); }
.csp-pf-save:disabled { opacity: .5; cursor: default; }

.csp-pf-prefs { display: flex; flex-direction: column; }
.csp-pf-pref { display: flex; align-items: center; gap: 11px; padding: 12px 0; border-bottom: 1px solid var(--c-border); }
.csp-pf-pref:last-child { border-bottom: 0; }
@media (max-width: 767px) { .csp-pf-pref--theme { display: none; } }
.csp-pf-pref-ico { width: 32px; height: 32px; flex-shrink: 0; display: grid; place-items: center; border-radius: 9px; background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); color: var(--c-text); }
.csp-pf-pref-txt { flex: 1; display: flex; flex-direction: column; }
.csp-pf-pref-txt span { font-size: 13px; font-weight: 600; }
.csp-pf-pref-txt small { font-size: 12px; color: var(--c-text-muted); }

.csp-pf-refbanner {
  padding: 16px; border-radius: 18px; display: flex; flex-direction: column; gap: 10px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--c-primary) 14%, transparent), color-mix(in srgb, var(--c-secondary) 8%, transparent));
  border: 1px solid color-mix(in srgb, var(--c-primary) 20%, transparent);
}
.csp-pf-refbanner-h { display: flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 800; color: var(--c-primary-fg); }
.csp-pf-refbanner p { font-size: 12px; color: var(--c-text-muted); line-height: 1.8; }
.csp-pf-refbanner-code { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 12px; background: var(--c-surface); font-weight: 800; letter-spacing: .1em; color: var(--c-primary-fg); }
:root:not(.dark) .csp-pf-refbanner-code { background: #fff; }
.csp-pf-refbanner-btn {
  display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; padding: 9px 15px; border-radius: 12px; border: 0; cursor: pointer;
  font-size: 12px; font-weight: 700; color: #fff; background: var(--c-primary);
}
.csp-pf-refbanner-btn:hover { filter: brightness(1.06); }
`
