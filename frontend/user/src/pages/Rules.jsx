import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { jalali } from '../lib/format'
import { Spinner } from '../components/ui'

function useRulesPage() {
  const [page, setPage] = useState(undefined)
  useEffect(() => {
    api.get('/pages/rules/').then((r) => setPage(r.data)).catch(() => setPage(null))
  }, [])
  return page
}

export default function Rules() {
  const { styleKey } = useTheme()
  return styleKey === 'caspian' ? <CaspianRules /> : <LegacyRules />
}

/* ================= Legacy (Aurora / Frost) — unchanged ================= */
function LegacyRules() {
  const { t, lang } = useI18n()
  const page = useRulesPage()
  if (page === undefined) return <div className="grid place-items-center py-16"><Spinner /></div>
  const title = page && ((lang === 'fa' ? page.title_fa : page.title_en) || page.title_fa)
  const body = page && ((lang === 'fa' ? page.body_fa : page.body_en) || page.body_fa)
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{title || t('rules')}</h1>
      <div className="card whitespace-pre-wrap leading-7">{body || t('no_content')}</div>
    </div>
  )
}

/* ================= Caspian — Stitch redesign port ================= */
const RI = ({ d, w = 18 }) => (
  <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
  </svg>
)

function CaspianRules() {
  const { t, lang } = useI18n()
  const { config } = useTheme()
  const page = useRulesPage()
  const tg = config?.support_telegram ? `https://t.me/${String(config.support_telegram).replace(/^@/, '')}` : ''

  if (page === undefined) return <div className="csp-rules"><div className="grid place-items-center py-24"><Spinner /></div></div>

  const title = page && ((lang === 'fa' ? page.title_fa : page.title_en) || page.title_fa)
  const body = page && ((lang === 'fa' ? page.body_fa : page.body_en) || page.body_fa)

  return (
    <div className="csp-rules">
      <style>{CSS}</style>

      <header className="csp-rules-hero">
        <span className="csp-rules-hero-blob" />
        <div className="csp-rules-hero-in">
          <span className="csp-rules-hero-ico"><RI d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" w={22} /></span>
          <div>
            <h1 className="csp-headline">{title || t('rules')}</h1>
            {page?.updated_at && (
              <span className="csp-rules-updated">{t('rules_updated')}: {jalali(page.updated_at, false, lang)}</span>
            )}
          </div>
        </div>
      </header>

      <div className="csp-rules-warn">
        <span className="csp-rules-warn-ico"><RI d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" w={18} /></span>
        <div>
          <div className="csp-rules-warn-t">{t('rules_warn_t')}</div>
          <div className="csp-rules-warn-d">{t('rules_warn_d')}</div>
        </div>
      </div>

      <div className="csp-rules-body-wrap">
        <div className="csp-rules-badges">
          <span><RI d="M5 11h14v10H5zM8 11V7a4 4 0 018 0v4" w={14} />{t('trust_e2e')}</span>
          <span><RI d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" w={14} />{t('trust_nolog')}</span>
        </div>
        <article className="csp-rules-body">{body || t('no_content')}</article>
      </div>

      <div className="csp-rules-cta">
        <div>
          <div className="csp-rules-cta-t">{t('rules_q_t')}</div>
          <div className="csp-rules-cta-d">{t('rules_q_d')}</div>
        </div>
        {tg && (
          <a href={tg} target="_blank" rel="noreferrer" className="csp-rules-cta-btn">
            <RI d="M22 3L2 10l7 3 3 7 4-7 6-10z" w={15} />{t('contact_telegram')}
          </a>
        )}
      </div>
    </div>
  )
}

const CSS = `
.csp-rules { display: flex; flex-direction: column; gap: 18px; max-width: 820px; margin: 0 auto; }
.csp-rules-hero {
  position: relative; overflow: hidden; border-radius: 22px; padding: clamp(18px, 3vw, 26px); color: #fff;
  background: linear-gradient(135deg, var(--c-primary), #0B1B36);
}
.csp-rules-hero-blob { position: absolute; width: 240px; height: 240px; border-radius: 50%; top: -110px; inset-inline-end: -60px; background: rgba(255,255,255,.12); filter: blur(55px); }
.csp-rules-hero-in { position: relative; display: flex; align-items: center; gap: 12px; }
.csp-rules-hero-ico { width: 40px; height: 40px; flex-shrink: 0; display: grid; place-items: center; border-radius: 12px; background: rgba(255,255,255,.18); }
.csp-rules-hero-in h1 { font-size: clamp(18px, 3vw, 24px); font-weight: 800; }
.csp-rules-updated { font-size: 12px; opacity: .85; }

.csp-rules-warn {
  display: flex; align-items: flex-start; gap: 11px; padding: 14px 16px; border-radius: 16px;
  background: color-mix(in srgb, var(--c-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-warning) 30%, transparent);
}
.csp-rules-warn-ico { flex-shrink: 0; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px; background: color-mix(in srgb, var(--c-warning) 18%, transparent); color: var(--c-warning-fg); }
.csp-rules-warn-t { font-size: 12.5px; font-weight: 800; color: var(--c-warning-fg); }
.csp-rules-warn-d { font-size: 12px; color: var(--c-text-muted); margin-top: 3px; line-height: 1.7; }

.csp-rules-body-wrap {
  border-radius: 18px; border: 1px solid var(--c-border); background: var(--c-surface); overflow: hidden;
}
:root:not(.dark) .csp-rules-body-wrap { background: #fff; }
[data-theme-style="caspian"].dark .csp-rules-body-wrap { box-shadow: -6px -6px 14px rgba(255,255,255,.02), 6px 6px 18px rgba(0,0,0,.5); }
.csp-rules-badges { display: flex; flex-wrap: wrap; gap: 8px; padding: 14px 18px; border-bottom: 1px solid var(--c-border); }
.csp-rules-badges span { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700; color: var(--c-primary-fg); padding: 5px 11px; border-radius: 999px; background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.csp-rules-body { padding: 20px; font-size: 13px; line-height: 2.1; color: var(--csp-text-2, var(--c-text)); white-space: pre-wrap; }

.csp-rules-cta {
  display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 16px 18px; border-radius: 18px; background: var(--c-surface); border: 1px solid var(--c-border);
}
:root:not(.dark) .csp-rules-cta { background: #fff; }
.csp-rules-cta-t { font-size: 13px; font-weight: 800; }
.csp-rules-cta-d { font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }
.csp-rules-cta-btn {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; padding: 10px 16px; border-radius: 12px;
  font-size: 12px; font-weight: 700; color: #fff; background: var(--c-primary);
  box-shadow: 0 6px 16px -6px color-mix(in srgb, var(--c-primary) 55%, transparent);
}
.csp-rules-cta-btn:hover { filter: brightness(1.06); }
`
