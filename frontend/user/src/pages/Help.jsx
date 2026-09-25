import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { Spinner } from '../components/ui'

function usePages(t) {
  const [pages, setPages] = useState(null)
  useEffect(() => {
    api.get('/pages/').then((r) => {
      const list = (r.data.results || r.data).filter((p) => p.slug !== 'rules' && p.is_active !== false)
      setPages(list)
    }).catch(() => setPages([]))
  }, [])
  return pages
}

export default function Help() {
  const { styleKey } = useTheme()
  return styleKey === 'caspian' ? <CaspianHelp /> : <LegacyHelp />
}

/* ================= Legacy (Aurora / Frost) — unchanged ================= */
function LegacyHelp() {
  const { t, lang } = useI18n()
  const pages = usePages(t)
  const [open, setOpen] = useState(null)
  useEffect(() => { if (pages && open == null) setOpen(pages[0]?.slug) }, [pages])
  if (pages === null) return <div className="grid place-items-center py-16"><Spinner /></div>
  const cur = pages.find((p) => p.slug === open)
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('pages')}</h1>
      {pages.length === 0 ? (
        <div className="card text-center text-muted">{t('no_content')}</div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {pages.map((p) => (
              <button key={p.slug} onClick={() => setOpen(p.slug)}
                className={`btn-ghost text-sm ${open === p.slug ? 'text-primary' : ''}`}>
                {(lang === 'fa' ? p.title_fa : p.title_en) || p.title_fa}
              </button>
            ))}
          </div>
          <div className="card whitespace-pre-wrap leading-7">
            {(lang === 'fa' ? cur?.body_fa : cur?.body_en) || cur?.body_fa || t('no_content')}
          </div>
        </>
      )}
    </div>
  )
}

/* ================= Caspian — Stitch redesign port ================= */
const OS = [
  ['android', 'os_android', 'M7 4l1.5 2.5M17 4l-1.5 2.5M4 8h16v9a3 3 0 01-3 3H7a3 3 0 01-3-3V8zM9 8V5M15 8V5', ['v2rayNG', 'NekoBox']],
  ['ios', 'os_ios', 'M12 6c1.5-2 4-2.5 5.5-1M9 9c-2 0-4 2-4 5s2 6 4 6c1 0 1.5-.5 3-.5s2 .5 3 .5c2 0 4-3 4-6M12 9c0-1.5 1-3 3-3', ['Streisand', 'Shadowrocket']],
  ['windows', 'os_windows', 'M3 5l8-1v8H3V5zM13 3.8L21 3v9h-8V3.8zM3 13h8v7l-8-1v-6zM13 13h8v8l-8-1v-7z', ['v2rayN', 'NekoRay']],
  ['mac', 'os_mac', 'M4 6h16v10H4zM2 19h20M9 16v3M15 16v3', ['V2Box', 'Streisand']],
]
const STEPS = [['hstep1', '1'], ['hstep2', '2'], ['hstep3', '3']]
const HI = ({ d, w = 20 }) => (
  <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
  </svg>
)

function CaspianHelp() {
  const { t, lang } = useI18n()
  const { config } = useTheme()
  const pages = usePages(t)
  const [os, setOs] = useState('android')
  const [open, setOpen] = useState(null)
  const tg = config?.support_telegram ? `https://t.me/${String(config.support_telegram).replace(/^@/, '')}` : ''

  const osApps = useMemo(() => OS.find(([k]) => k === os)[3], [os])
  const osLabel = t(OS.find(([k]) => k === os)[1])

  return (
    <div className="csp-help">
      <style>{CSS}</style>

      <header className="csp-help-hero">
        <span className="csp-help-hero-blob" />
        <h1 className="csp-headline">{t('help_h1')}</h1>
        <p>{t('help_lead')}</p>
      </header>

      {/* platform selector */}
      <section className="csp-help-sec">
        <h2 className="csp-headline csp-help-h2">{t('choose_os')}</h2>
        <div className="csp-help-os">
          {OS.map(([k, key, icon]) => (
            <button key={k} type="button" className={'csp-help-os-card' + (os === k ? ' on' : '')} onClick={() => setOs(k)}>
              <span className="csp-help-os-ico"><HI d={icon} w={24} /></span>
              <span>{t(key)}</span>
            </button>
          ))}
        </div>

        <div className="csp-help-apps">
          <h3 className="csp-help-h3">{t('recommended_apps', { os: osLabel })}</h3>
          <div className="csp-help-apps-row">
            {osApps.map((app) => (
              <div key={app} className="csp-help-app">
                <span className="csp-help-app-badge mono-num">{app.slice(0, 2)}</span>
                <div className="csp-help-app-txt">
                  <b>{app}</b>
                  <a href={tg || '#'} target={tg ? '_blank' : undefined} rel="noreferrer" className="csp-help-app-link">
                    <HI d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" w={13} />{t('get_app')}
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3-step guide */}
      <section className="csp-help-sec">
        <h2 className="csp-headline csp-help-h2">{t('activation_steps')}</h2>
        <div className="csp-help-steps">
          {STEPS.map(([key, n]) => (
            <div key={n} className="csp-help-step">
              <span className="csp-help-step-n mono-num">{n}</span>
              <div>
                <div className="csp-help-step-t">{t(key + '_t')}</div>
                <div className="csp-help-step-d">{t(key + '_d')}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CMS pages (tutorial / faq / ...) as accordion */}
      {pages === null ? (
        <div className="grid place-items-center py-10"><Spinner /></div>
      ) : pages.length > 0 && (
        <section className="csp-help-sec">
          <div className="csp-help-acc">
            {pages.map((p) => {
              const title = (lang === 'fa' ? p.title_fa : p.title_en) || p.title_fa
              const body = (lang === 'fa' ? p.body_fa : p.body_en) || p.body_fa
              const isOpen = open === p.slug
              return (
                <div key={p.slug} className={'csp-help-acc-item' + (isOpen ? ' on' : '')}>
                  <button type="button" className="csp-help-acc-q" onClick={() => setOpen(isOpen ? null : p.slug)}>
                    <span>{title}</span>
                    <HI d={isOpen ? 'M18 15l-6-6-6 6' : 'M6 9l6 6 6-6'} w={16} />
                  </button>
                  {isOpen && <div className="csp-help-acc-a">{body || t('no_content')}</div>}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* support banner */}
      <div className="csp-help-support">
        <div className="csp-help-support-txt">
          <div className="csp-help-support-t">{t('help_support_t')}</div>
          <div className="csp-help-support-d">{t('help_support_d')}</div>
        </div>
        {tg && (
          <a href={tg} target="_blank" rel="noreferrer" className="csp-help-support-btn">
            <HI d="M22 3L2 10l7 3 3 7 4-7 6-10z" w={16} />{t('contact_telegram')}
          </a>
        )}
      </div>
    </div>
  )
}

const CSS = `
.csp-help { display: flex; flex-direction: column; gap: 20px; }
.csp-help-hero {
  position: relative; overflow: hidden; border-radius: 22px; padding: clamp(20px, 3vw, 30px); color: #fff;
  background: linear-gradient(135deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 55%, #1a1350));
}
.csp-help-hero-blob { position: absolute; width: 260px; height: 260px; border-radius: 50%; top: -120px; inset-inline-end: -70px; background: rgba(255,255,255,.12); filter: blur(60px); }
.csp-help-hero h1 { position: relative; font-size: clamp(20px, 3.5vw, 28px); font-weight: 800; }
.csp-help-hero p { position: relative; font-size: 12.5px; opacity: .9; margin-top: 8px; line-height: 1.8; max-width: 520px; }

.csp-help-sec { display: flex; flex-direction: column; gap: 14px; }
.csp-help-h2 { font-size: 16px; font-weight: 800; }
.csp-help-h3 { font-size: 13px; font-weight: 700; }

.csp-help-os { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
@media (max-width: 640px) { .csp-help-os { grid-template-columns: repeat(2, 1fr); } }
.csp-help-os-card {
  display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 16px 10px; cursor: pointer;
  border-radius: 16px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text);
  font-size: 12px; font-weight: 600; transition: .15s;
}
:root:not(.dark) .csp-help-os-card { background: #fff; }
.csp-help-os-card:hover { border-color: color-mix(in srgb, var(--c-primary) 40%, var(--c-border)); }
.csp-help-os-card.on { border-color: var(--c-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c-primary) 16%, transparent); }
.csp-help-os-ico { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 12px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.csp-help-os-card.on .csp-help-os-ico { background: var(--c-primary); color: #fff; }

.csp-help-apps { padding: 16px; border-radius: 16px; background: var(--c-surface); border: 1px solid var(--c-border); display: flex; flex-direction: column; gap: 12px; }
:root:not(.dark) .csp-help-apps { background: #fff; }
.csp-help-apps-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 520px) { .csp-help-apps-row { grid-template-columns: 1fr; } }
.csp-help-app { display: flex; align-items: center; gap: 11px; padding: 11px; border-radius: 13px; background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); }
.csp-help-app-badge { width: 38px; height: 38px; flex-shrink: 0; display: grid; place-items: center; border-radius: 11px; background: var(--c-primary); color: #fff; font-size: 12px; font-weight: 800; }
.csp-help-app-txt { display: flex; flex-direction: column; gap: 2px; }
.csp-help-app-txt b { font-size: 13px; font-weight: 700; }
.csp-help-app-link { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 700; color: var(--c-primary); }
.csp-help-app-link:hover { text-decoration: underline; }

.csp-help-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
@media (max-width: 720px) { .csp-help-steps { grid-template-columns: 1fr; } }
.csp-help-step { display: flex; gap: 11px; padding: 15px; border-radius: 16px; background: var(--c-surface); border: 1px solid var(--c-border); }
:root:not(.dark) .csp-help-step { background: #fff; }
.csp-help-step-n { width: 30px; height: 30px; flex-shrink: 0; display: grid; place-items: center; border-radius: 10px; background: color-mix(in srgb, var(--c-primary) 14%, transparent); color: var(--c-primary); font-size: 13px; font-weight: 800; }
.csp-help-step-t { font-size: 13px; font-weight: 700; }
.csp-help-step-d { font-size: 11px; color: var(--c-text-muted); margin-top: 3px; line-height: 1.7; }

.csp-help-acc { display: flex; flex-direction: column; gap: 8px; }
.csp-help-acc-item { border-radius: 14px; border: 1px solid var(--c-border); background: var(--c-surface); overflow: hidden; }
:root:not(.dark) .csp-help-acc-item { background: #fff; }
.csp-help-acc-item.on { border-color: color-mix(in srgb, var(--c-primary) 35%, var(--c-border)); }
.csp-help-acc-q { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px; cursor: pointer; border: 0; background: transparent; color: var(--c-text); font-size: 13px; font-weight: 700; text-align: start; }
.csp-help-acc-a { padding: 0 16px 16px; font-size: 12.5px; color: var(--c-text-muted); line-height: 1.9; white-space: pre-wrap; }

.csp-help-support {
  display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 18px; border-radius: 18px;
  background: color-mix(in srgb, var(--c-success) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-success) 24%, transparent);
}
.csp-help-support-t { font-size: 13.5px; font-weight: 800; }
.csp-help-support-d { font-size: 11.5px; color: var(--c-text-muted); margin-top: 3px; }
.csp-help-support-btn {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; padding: 11px 18px; border-radius: 13px;
  font-size: 12.5px; font-weight: 700; color: #fff; background: var(--c-success);
  box-shadow: 0 6px 16px -6px color-mix(in srgb, var(--c-success) 55%, transparent);
}
.csp-help-support-btn:hover { filter: brightness(1.05); }
`
