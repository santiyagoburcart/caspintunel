import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { toman, tomanParts, gb as gbOf } from '../lib/format'
import { Alert, Spinner } from '../components/ui'

/** price: Latin number in a mono span, currency word in a normal run */
function Money({ n, lang, per }) {
  const { num, unit } = tomanParts(n, lang)
  return <><b className="mono-num">{num}</b> <span>{unit}{per ? ' / GB' : ''}</span></>
}

const GB = 1024 ** 3

// language-aware category: label shown + a stable key for grouping
function category(plan, lang) {
  const fa = (plan.category_fa || '').trim()
  const en = (plan.category_en || '').trim()
  const label = lang === 'fa' ? (fa || en) : (en || fa)
  const key = `${fa.toLowerCase()}|${en.toLowerCase()}`
  return { label, key: label ? key : '' }   // '' key == no category == "Other"
}

export default function Store() {
  const { styleKey } = useTheme()
  return styleKey === 'caspian' ? <CaspianStore /> : <LegacyStore />
}

/* ================= Legacy (Aurora / Frost) — unchanged ================= */
function LegacyStore() {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const [plans, setPlans] = useState(null)
  const [mode, setMode] = useState('grouped')
  const [selected, setSelected] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/plans/').then((r) => setPlans(r.data.results || [])).catch(() => setPlans([]))
    api.get('/config/').then((r) => {
      if (r.data?.product_display_mode) setMode(r.data.product_display_mode)
    }).catch(() => {})
  }, [])

  const groups = useMemo(() => {
    if (!plans) return []
    const byKey = new Map()
    for (const p of plans) {
      const { label, key } = category(p, lang)
      if (!byKey.has(key)) byKey.set(key, { key, label: label || t('other_group'), plans: [] })
      byKey.get(key).plans.push(p)
    }
    const list = [...byKey.values()]
    list.sort((a, b) => (a.key === '' ? 1 : b.key === '' ? -1 : 0))
    return list
  }, [plans, lang, t])

  const continueToCheckout = () => {
    if (!selected) { setErr(t('choose_plan_first')); return }
    nav(`/checkout?plan=${selected}`)
  }

  if (plans === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold">{t('store')}</h1>
      {plans.length === 0 && <div className="card text-center text-muted">{t('no_plans')}</div>}
      {mode === 'grouped' ? (
        groups.map((g) => (
          <section key={g.key || '_other'} className="space-y-3">
            <div className="flex items-center gap-3">
              <h2 className="text-base font-bold">{g.label}</h2>
              <span className="h-px flex-1" style={{ background: 'var(--c-border)' }} />
              <span className="text-xs text-muted">{g.plans.length}</span>
            </div>
            <LegacyGrid plans={g.plans} lang={lang} t={t} selected={selected} onSelect={setSelected} />
          </section>
        ))
      ) : (
        <LegacyGrid plans={plans} lang={lang} t={t} selected={selected} onSelect={setSelected} showBadge />
      )}
      {plans.length > 0 && (
        <div className="space-y-2">
          <Alert>{err}</Alert>
          <button className="btn-primary w-full" disabled={!selected} onClick={continueToCheckout}>
            {t('continue_checkout')}
          </button>
        </div>
      )}
    </div>
  )
}

function LegacyGrid({ plans, lang, t, selected, onSelect, showBadge }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {plans.map((p) => {
        const { label: cat } = category(p, lang)
        const isSel = selected === p.id
        return (
          <div key={p.id} role="radio" aria-checked={isSel} tabIndex={0}
            className="card flex cursor-pointer flex-col gap-2 outline-none transition"
            style={{
              borderWidth: 2, borderStyle: 'solid',
              borderColor: isSel ? 'var(--c-primary)' : 'var(--c-border)',
              background: isSel ? 'color-mix(in srgb, var(--c-primary) 7%, var(--c-surface))' : undefined,
            }}
            onClick={() => onSelect(p.id)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(p.id) } }}>
            <div className="flex items-center justify-between gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white transition"
                style={{ background: isSel ? 'var(--c-primary)' : 'transparent', border: `2px solid ${isSel ? 'var(--c-primary)' : 'var(--c-border)'}` }}
                aria-hidden="true">{isSel ? '✓' : ''}</span>
              {showBadge && cat && (
                <span className="shrink-0 rounded-full px-2 py-0.5 text-xs"
                  style={{ background: 'color-mix(in srgb, var(--c-primary) 14%, transparent)', color: 'var(--c-primary)' }}>{cat}</span>
              )}
            </div>
            {!showBadge && cat && <div className="text-xs font-bold" style={{ color: 'var(--c-secondary)' }}>{cat}</div>}
            <div className="font-bold" style={{ color: 'var(--c-ink)' }}>{(lang === 'fa' ? p.name_fa : p.name_en) || p.name_fa}</div>
            <div className="whitespace-pre-line text-sm text-muted">{(lang === 'fa' ? p.desc_fa : p.desc_en) || p.desc_fa}</div>
            <ul className="mt-1 space-y-1 text-sm">
              <li>{t('volume')}: {p.type === 'custom_volume' ? t('selectable') : p.data_limit ? `${p.data_limit / GB} GB` : t('unlimited')}</li>
              <li>{t('duration')}: {p.duration_days ? `${p.duration_days} ${t('days')}` : t('no_expiry')}</li>
              {p.discount_percent > 0 && <li className="text-success">{t('discount')} {p.discount_percent}%</li>}
            </ul>
            <div className="mt-auto pt-2">
              <span className="font-bold" style={{ color: 'var(--c-primary)' }}>
                {p.type === 'custom_volume' ? `${toman(p.price_per_gb, lang)} / GB` : toman(p.final_price, lang)}
              </span>
              {isSel && (
                <span className="ms-2 rounded-full px-2 py-0.5 text-xs"
                  style={{ background: 'color-mix(in srgb, var(--c-success) 16%, transparent)', color: 'var(--c-success)' }}>{t('selected')}</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ================= Caspian — Stitch redesign port ================= */
const ICO = {
  bag: 'M6 7V6a4 4 0 018 0v1M4 7h16l-1 13H5L4 7z',
  infinite: 'M18.4 8.6a4 4 0 100 6.8L12 12l-6.4 3.4a4 4 0 110-6.8L12 12z',
  rocket: 'M5 13l-2 6 6-2M14 6l4 4M13 3l8 8-6 6-2-4-4-2 4-8z',
  tune: 'M4 6h10M4 12h6M4 18h13M18 4v4M13 10v4M20 16v4',
  check: 'M5 13l4 4L19 7',
  shield: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'M9 12l2 2 4-4'],
  arrow: 'M19 12H5m7 7l-7-7 7-7',
}
function SI({ d, w = 20 }) {
  return (
    <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}
const faNum = (n, lang) => (lang === 'fa' ? String(n).replace(/\d/g, (x) => '۰۱۲۳۴۵۶۷۸۹'[x]) : String(n))

function CaspianStore() {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const [plans, setPlans] = useState(null)
  const [selected, setSelected] = useState(null)
  const [tab, setTab] = useState('all')
  const [gb, setGb] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/plans/').then((r) => {
      const list = r.data.results || []
      setPlans(list)
      const rec = list.find((p) => p.discount_percent > 0) || list[0]
      if (rec) setSelected(rec.id)
    }).catch(() => setPlans([]))
  }, [])

  const cats = useMemo(() => {
    if (!plans) return []
    const seen = new Map()
    for (const p of plans) {
      if (p.type === 'custom_volume') continue
      const { label, key } = category(p, lang)
      if (label && !seen.has(key)) seen.set(key, label)
    }
    return [...seen.entries()].map(([key, label]) => ({ key, label }))
  }, [plans, lang])

  const hasCustom = (plans || []).some((p) => p.type === 'custom_volume')

  const shown = useMemo(() => {
    if (!plans) return []
    if (tab === 'all') return plans
    if (tab === 'custom') return plans.filter((p) => p.type === 'custom_volume')
    return plans.filter((p) => p.type !== 'custom_volume' && category(p, lang).key === tab)
  }, [plans, tab, lang])

  const sel = useMemo(() => (plans || []).find((p) => p.id === selected), [plans, selected])
  const isCustom = sel?.type === 'custom_volume'

  useEffect(() => {
    if (isCustom && gb == null) setGb(sel.min_gb || 60)
  }, [isCustom, sel, gb])

  const customPrice = isCustom
    ? Math.round(
        (Number(sel.price || 0) + Number(sel.price_per_gb || 0) * (gb || 0)) *
        (1 - Number(sel.discount_percent || 0) / 100),
      )
    : 0

  const go = () => {
    if (!selected) { setErr(t('choose_plan_first')); return }
    nav(`/checkout?plan=${selected}${isCustom && gb ? `&gb=${gb}` : ''}`)
  }

  if (plans === null) return <div className="csp-store"><div className="grid place-items-center py-24"><Spinner /></div></div>

  return (
    <div className="csp-store">
      <style>{CSS}</style>

      <header className="csp-store-hero">
        <div className="csp-store-eyebrow"><SI d={ICO.bag} w={16} />{t('store_eyebrow')}</div>
        <h1 className="csp-headline csp-store-h1">{t('store_h1')}</h1>
        <p className="csp-store-lead">{t('store_lead')}</p>
      </header>

      {plans.length === 0 ? (
        <div className="csp-card csp-store-empty">{t('no_plans')}</div>
      ) : (
        <>
          <div className="csp-store-tabs">
            <Tab id="all" tab={tab} set={setTab}>{t('all_plans')}</Tab>
            {cats.map((c) => <Tab key={c.key} id={c.key} tab={tab} set={setTab}>{c.label}</Tab>)}
            {hasCustom && <Tab id="custom" tab={tab} set={setTab}>{t('custom_vol_tab')}</Tab>}
          </div>

          <div className="csp-store-grid">
            {shown.map((p) => (
              <PlanCard key={p.id} p={p} lang={lang} t={t} sel={selected === p.id} onSelect={() => setSelected(p.id)} />
            ))}
          </div>

          {isCustom && (
            <VolumeCard sel={sel} gb={gb || sel.min_gb || 20} setGb={setGb} price={customPrice} t={t} lang={lang} />
          )}

          <div className="csp-store-note">
            <span className="csp-store-note-ico"><SI d={ICO.shield} /></span>
            <div>
              <div className="csp-store-note-t">{t('quality_note_t')}</div>
              <div className="csp-store-note-d">{t('quality_note_d')}</div>
            </div>
          </div>

          <Alert>{err}</Alert>
          <button className="csp-store-cta" onClick={go} disabled={!selected}>
            {t('continue_checkout')} <SI d={ICO.arrow} w={18} />
          </button>
        </>
      )}
    </div>
  )
}

function Tab({ id, tab, set, children }) {
  return (
    <button type="button" className={'csp-store-tab' + (tab === id ? ' on' : '')} onClick={() => set(id)}>
      {children}
    </button>
  )
}

function PlanCard({ p, lang, t, sel, onSelect }) {
  const name = (lang === 'fa' ? p.name_fa : p.name_en) || p.name_fa
  const desc = (lang === 'fa' ? p.desc_fa : p.desc_en) || p.desc_fa
  const custom = p.type === 'custom_volume'
  const volNum = p.data_limit ? `${faNum(gbOf(p.data_limit), lang)} GB` : null
  const dur = p.duration_days ? `${faNum(p.duration_days, lang)} ${t('days')}` : t('no_expiry')
  const icon = custom ? ICO.tune : p.data_limit ? ICO.rocket : ICO.infinite

  return (
    <div role="radio" aria-checked={sel} tabIndex={0}
      className={'csp-plan' + (sel ? ' on' : '')}
      onClick={onSelect}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } }}>
      {p.discount_percent > 0 && (
        <span className="csp-plan-badge">{t('discount')} {faNum(p.discount_percent, lang)}%</span>
      )}
      <div className="csp-plan-top">
        <span className="csp-plan-icon"><SI d={icon} /></span>
        <span className="csp-plan-radio">{sel && <SI d={ICO.check} w={14} />}</span>
      </div>
      <h3 className="csp-plan-name csp-headline">{name}</h3>
      {desc && <p className="csp-plan-desc">{desc}</p>}
      <dl className="csp-plan-specs">
        <div><dt>{t('volume')}</dt><dd>{custom ? t('selectable') : volNum ? <span className="mono-num">{volNum}</span> : t('fair_use')}</dd></div>
        <div><dt>{t('duration')}</dt><dd>{p.duration_days ? <span className="mono-num">{dur}</span> : t('no_expiry')}</dd></div>
        {p.device_limit ? (
          <div><dt>{t('devices')}</dt><dd>{t('n_devices', { n: faNum(p.device_limit, lang) })}</dd></div>
        ) : null}
      </dl>
      <div className="csp-plan-foot">
        <div>
          <span className="csp-plan-payable">{custom ? t('calc_next') : t('payable')}</span>
          <div className="csp-plan-price"><Money n={custom ? p.price_per_gb : p.final_price} lang={lang} per={custom} /></div>
        </div>
        <span className={'csp-plan-select' + (sel ? ' on' : '')}>{sel ? t('selected') : t('select_plan')}</span>
      </div>
    </div>
  )
}

function VolumeCard({ sel, gb, setGb, price, t, lang }) {
  const min = sel.min_gb || 1
  const max = sel.max_gb || 800
  const pct = Math.max(0, Math.min(100, ((gb - min) / ((max - min) || 1)) * 100))
  const clamp = (v) => setGb(Math.max(min, Math.min(max, Math.round(Number(v) || min))))
  const chips = [...new Set([min, Math.round((min + max) / 4 / 5) * 5, Math.round((min + max) / 2 / 5) * 5,
    Math.round((min + max) * 3 / 4 / 5) * 5, max].filter((v) => v >= min && v <= max))]

  return (
    <div className="csp-card csp-vol">
      <div className="csp-vol-head">
        <div>
          <div className="csp-vol-title csp-headline">{t('custom_volume_label')}</div>
          <div className="csp-vol-sub">{t('drag_slider')}</div>
        </div>
        <div className="csp-vol-counter">
          <b className="mono-num">{faNum(gb, lang)}</b>
          <span>{t('gigabytes')}</span>
        </div>
      </div>

      <input type="range" dir="ltr" min={min} max={max} step={5} value={gb}
        style={{ '--pct': `${pct}%` }}
        onChange={(e) => clamp(e.target.value)} className="csp-vol-range" />
      <div className="csp-vol-scale mono-num" dir="ltr">
        <span>{min} GB</span><span>{max} GB</span>
      </div>

      <div className="csp-vol-chips">
        <span className="csp-vol-chips-l">{t('quick_select')}</span>
        {chips.map((c) => (
          <button key={c} type="button" className={'csp-vol-chip mono-num' + (c === gb ? ' on' : '')}
            onClick={() => setGb(c)}>{faNum(c, lang)} GB</button>
        ))}
      </div>

      <div className="csp-vol-price">
        <span>{t('calculated_amount')}</span>
        <span className="csp-vol-price-v"><Money n={price} lang={lang} /></span>
      </div>
    </div>
  )
}

const CSS = `
.csp-store { display: flex; flex-direction: column; gap: 20px; }
.csp-store-hero { display: flex; flex-direction: column; gap: 6px; }
.csp-store-eyebrow {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700;
  color: var(--c-primary); letter-spacing: .01em;
}
.csp-store-h1 { font-size: clamp(20px, 3.5vw, 28px); font-weight: 800; line-height: 1.4; }
.csp-store-lead { font-size: 13px; color: var(--c-text-muted); line-height: 1.8; max-width: 640px; }

.csp-store-tabs {
  display: inline-flex; flex-wrap: wrap; gap: 3px; padding: 4px; border-radius: 999px; align-self: flex-start;
  background: color-mix(in srgb, var(--c-text-muted) 10%, transparent);
}
.csp-store-tab {
  border: 0; cursor: pointer; padding: 7px 15px; border-radius: 999px;
  font-size: 12.5px; font-weight: 600; color: var(--c-text-muted); white-space: nowrap; transition: .15s;
}
.csp-store-tab.on { background: var(--c-surface); color: var(--c-primary); box-shadow: 0 1px 3px rgba(15,23,42,.12); }
:root:not(.dark) .csp-store-tab.on { background: #fff; }

.csp-store-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.csp-card, .csp-plan {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 18px;
}
:root:not(.dark) .csp-card, :root:not(.dark) .csp-plan { background: #fff; }
[data-theme-style="caspian"].dark .csp-card, [data-theme-style="caspian"].dark .csp-plan {
  box-shadow: -6px -6px 14px rgba(255,255,255,.02), 6px 6px 18px rgba(0,0,0,.55);
}

.csp-plan {
  position: relative; padding: 18px; display: flex; flex-direction: column; gap: 10px;
  cursor: pointer; outline: none; transition: border-color .15s, box-shadow .15s, transform .05s;
}
.csp-plan:hover { border-color: color-mix(in srgb, var(--c-primary) 40%, var(--c-border)); }
.csp-plan.on { border-color: var(--c-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c-primary) 16%, transparent); }
.csp-plan-badge {
  position: absolute; top: -10px; inset-inline-start: 18px; padding: 3px 10px; border-radius: 999px;
  font-size: 10.5px; font-weight: 700; color: #fff; background: var(--c-success);
}
.csp-plan-top { display: flex; align-items: flex-start; justify-content: space-between; }
.csp-plan-icon {
  width: 40px; height: 40px; display: grid; place-items: center; border-radius: 12px;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary);
}
.csp-plan-radio {
  width: 24px; height: 24px; display: grid; place-items: center; border-radius: 50%;
  border: 2px solid var(--c-border); color: #fff;
}
.csp-plan.on .csp-plan-radio { background: var(--c-primary); border-color: var(--c-primary); }
.csp-plan-name { font-size: 17px; font-weight: 800; }
.csp-plan-desc { font-size: 12px; color: var(--c-text-muted); line-height: 1.7; }
.csp-plan-specs {
  display: flex; flex-direction: column; gap: 7px; padding: 12px; border-radius: 12px;
  background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); font-size: 12px;
}
.csp-plan-specs > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.csp-plan-specs dt { color: var(--c-text-muted); }
.csp-plan-specs dd { font-weight: 600; }
.csp-plan-foot { margin-top: auto; padding-top: 6px; display: flex; align-items: flex-end; justify-content: space-between; gap: 10px; }
.csp-plan-payable { font-size: 10.5px; color: var(--c-text-muted); }
.csp-plan-price { display: flex; align-items: baseline; gap: 4px; }
.csp-plan-price b { font-size: 17px; font-weight: 800; color: var(--c-primary); }
.csp-plan-price span { font-size: 10.5px; color: var(--c-text-muted); }
.csp-plan-select {
  flex-shrink: 0; padding: 6px 14px; border-radius: 999px; font-size: 11.5px; font-weight: 700;
  background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text);
}
.csp-plan-select.on { background: var(--c-primary); color: #fff; }

/* volume card */
.csp-vol { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.csp-vol-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.csp-vol-title { font-size: 15px; font-weight: 800; }
.csp-vol-sub { font-size: 12px; color: var(--c-text-muted); margin-top: 3px; }
.csp-vol-counter {
  display: flex; align-items: baseline; gap: 6px; padding: 6px 14px; border-radius: 14px;
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}
.csp-vol-counter b { font-size: 30px; font-weight: 800; color: var(--c-primary); line-height: 1; }
.csp-vol-counter span { font-size: 12px; color: var(--c-text-muted); }
.csp-vol-range { width: 100%; }
.csp-vol-scale { display: flex; justify-content: space-between; font-size: 11px; color: var(--c-text-muted); }
.csp-vol-chips { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }
.csp-vol-chips-l { font-size: 11px; color: var(--c-text-muted); }
.csp-vol-chip {
  border: 1px solid var(--c-border); background: var(--c-surface); cursor: pointer;
  padding: 5px 11px; border-radius: 9px; font-size: 12px; font-weight: 600; color: var(--c-text); transition: .15s;
}
.csp-vol-chip:hover { border-color: var(--c-primary); }
.csp-vol-chip.on { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.csp-vol-price {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding-top: 13px; border-top: 1px solid var(--c-border); font-size: 12.5px; color: var(--c-text-muted);
}
.csp-vol-price-v b { font-size: 18px; font-weight: 800; color: var(--c-primary); }
.csp-vol-price-v span { font-size: 11px; color: var(--c-text-muted); }

/* quality note + CTA */
.csp-store-note {
  display: flex; align-items: flex-start; gap: 11px; padding: 14px 16px; border-radius: 16px;
  background: color-mix(in srgb, var(--c-success) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-success) 24%, transparent);
}
.csp-store-note-ico {
  flex-shrink: 0; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px;
  background: color-mix(in srgb, var(--c-success) 16%, transparent); color: var(--c-success);
}
.csp-store-note-t { font-size: 13px; font-weight: 700; color: color-mix(in srgb, var(--c-success) 80%, var(--c-text)); }
.csp-store-note-d { font-size: 11.5px; color: var(--c-text-muted); margin-top: 3px; line-height: 1.6; }
.csp-store-empty { padding: 40px; text-align: center; color: var(--c-text-muted); }

.csp-store-cta {
  width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 14px 20px; border-radius: 16px; border: 0; cursor: pointer; font-weight: 700; font-size: 14px; color: #fff;
  background: linear-gradient(135deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 62%, #3f2bd0));
  box-shadow: 0 10px 26px -8px color-mix(in srgb, var(--c-primary) 55%, transparent);
  transition: filter .15s;
}
.csp-store-cta:hover:not(:disabled) { filter: brightness(1.06); }
.csp-store-cta:disabled { opacity: .6; cursor: default; }
[dir="rtl"] .csp-store-cta svg, [dir="rtl"] .csp-store-eyebrow svg { }
[dir="rtl"] .csp-store-cta > svg:last-child { transform: scaleX(-1); }
`
