import { useEffect, useMemo, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman, digits } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

const blank = { card_number: '', holder_name: '', bank_name: '', sort_order: 0, is_active: true }

const L = {
  fa: {
    title: 'کارت‌های بانکی', connected: '{n} کارت متصل',
    subtitle: 'مدیریت شماره‌کارت‌های فعال برای پرداخت کارت‌به‌کارت کاربران در ربات و وب‌سایت',
    m_total: 'مجموع واریزی‌های موفق', m_total_sub: '{n} تراکنش تأییدشده',
    m_active: 'کارت‌های آماده دریافت', m_active_u: 'کارت فعال', m_active_sub: 'چرخش خودکار مبالغ یکتا',
    m_count: 'تعداد کل واریز', m_count_u: 'واریز', m_count_sub: 'مجموع روی همهٔ کارت‌ها',
    list_title: 'کارت‌های بانکی فعال در سیستم', list_hint: 'اولویت نمایش در ربات بر اساس ترتیب نمایش است',
    order: 'ترتیب نمایش',
  },
  en: {
    title: 'Bank cards', connected: '{n} cards connected',
    subtitle: 'Manage the active card numbers used for card-to-card payments in the bot and website',
    m_total: 'Total successful deposits', m_total_sub: '{n} approved transactions',
    m_active: 'Cards ready to receive', m_active_u: 'active', m_active_sub: 'automatic unique-amount rotation',
    m_count: 'Total deposits', m_count_u: 'deposits', m_count_sub: 'across all cards',
    list_title: 'Active bank cards in the system', list_hint: 'Bot display priority follows the sort order',
    order: 'Sort order',
  },
}

function Metric({ label, value, unit, sub, tone, icon, lang }) {
  return (
    <div className="card cd-metric">
      <div>
        <span className="cd-metric-label">{label}</span>
        <div className="cd-metric-val">
          {value}{unit ? <span className="cd-metric-unit"> {unit}</span> : null}
        </div>
        {sub ? <div className="cd-metric-sub">{sub}</div> : null}
      </div>
      <span className="cd-metric-ico" style={{ background: `color-mix(in srgb, ${tone} 13%, transparent)`, color: tone }}>{icon}</span>
    </div>
  )
}

function MIco({ d }) {
  return <svg viewBox="0 0 24 24" width={20} height={20} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
}
const MI = {
  vault: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="12" cy="12" r="3" /><path d="M12 9V6M12 18v-3M15 12h3M6 12h3" /></>,
  card: <><rect x="1" y="4" width="22" height="16" rx="2" /><path d="M1 10h22" /></>,
  layers: <><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5M2 12l10 5 10-5" /></>,
}

const groupNumber = (raw) => {
  const s = String(raw || '').replace(/\D/g, '')
  return s ? s.replace(/(.{4})(?=.)/g, '$1 ') : String(raw || '')
}

// A real-looking bank-card graphic. Theme-driven (--c-primary blue gradient),
// with the deposit totals printed ON the card itself.
function BankCard({ c, t, lang, preview = false }) {
  return (
    <div className={'bankcard' + (c.is_active ? '' : ' bankcard--off')}>
      <div className="bankcard-row">
        <span className="bankcard-bank">{c.bank_name || t('bank')}</span>
        {!preview && (
          <span className={'bankcard-state ' + (c.is_active ? 'on' : 'off')}>
            {c.is_active ? t('active') : t('inactive')}
          </span>
        )}
      </div>
      <div className="bankcard-chip" aria-hidden="true" />
      <div className="bankcard-num mono-num" dir="ltr">{groupNumber(c.card_number) || '•••• •••• •••• ••••'}</div>
      <div className="bankcard-row bankcard-foot">
        <div className="bankcard-holder">
          <span className="bankcard-label">{t('holder')}</span>
          <span className="bankcard-name">{c.holder_name || '—'}</span>
        </div>
        <span className="bankcard-brand">CASPIAN</span>
      </div>
      {!preview && (
        <div className="bankcard-deposits">
          <span className="bankcard-dep">
            <span className="bankcard-label">{t('deposit_total')}</span>
            <b>{toman(c.deposit_total || 0, lang)}</b>
          </span>
          <span className="bankcard-dep-count">
            <b>{digits(c.deposit_count || 0, lang)}</b>
            <span className="bankcard-label">{t('deposit_count')}</span>
          </span>
        </div>
      )}
    </div>
  )
}

export default function Cards() {
  const { t, lang } = useI18n()
  const s = L[lang] || L.fa
  const [d, setD] = useState(null)
  const [edit, setEdit] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () =>
    api.get('/admin/cards/deposit-report/')
      .then((r) => { setD(r.data); setErr('') })
      .catch(() => { setD({ cards: [], grand_total: 0 }); setErr(t('load_error')) })
  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    const body = {
      card_number: edit.card_number.replace(/\s+/g, ''),
      holder_name: edit.holder_name,
      bank_name: edit.bank_name || '',
      sort_order: Number(edit.sort_order) || 0,
      is_active: edit.is_active,
    }
    try {
      if (edit.id) await api.patch(`/admin/cards/${edit.id}/`, body)
      else await api.post('/admin/cards/', body)
      setEdit(null); load()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  const toggle = async (c) => {
    setErr('')
    try { await api.patch(`/admin/cards/${c.id}/`, { is_active: !c.is_active }); load() }
    catch (e2) { setErr(apiError(e2)) }
  }
  const del = async (c) => {
    if (!confirm(t('delete_card_confirm'))) return
    try { await api.delete(`/admin/cards/${c.id}/`); load() } catch (e2) { setErr(apiError(e2)) }
  }

  const cards = d?.cards || []
  const metrics = useMemo(() => ({
    activeCount: cards.filter((c) => c.is_active).length,
    depositCount: cards.reduce((a, c) => a + (c.deposit_count || 0), 0),
  }), [cards])

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-5">
      <style>{CSS}</style>

      <div className="cd-head">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-bold">{s.title}</h1>
            <span className="cd-badge">{s.connected.replace('{n}', digits(cards.length, lang))}</span>
          </div>
          <p className="text-sm text-muted mt-1">{s.subtitle}</p>
        </div>
        {!edit && (
          <button className="btn-primary text-sm cd-add" onClick={() => setEdit({ ...blank })}>{t('add_card')}</button>
        )}
      </div>

      <div className="cd-metrics">
        <Metric label={s.m_total} value={toman(d.grand_total || 0, lang)}
          sub={s.m_total_sub.replace('{n}', digits(metrics.depositCount, lang))}
          tone="#1464BA" icon={<MIco d={MI.vault} />} lang={lang} />
        <Metric label={s.m_active} value={digits(metrics.activeCount, lang)} unit={s.m_active_u}
          sub={s.m_active_sub} tone="#11AB53" icon={<MIco d={MI.card} />} lang={lang} />
        <Metric label={s.m_count} value={digits(metrics.depositCount, lang)} unit={s.m_count_u}
          sub={s.m_count_sub} tone="#7C3AED" icon={<MIco d={MI.layers} />} lang={lang} />
      </div>

      <Alert>{err}</Alert>

      {edit && (
        <div className="card grid gap-5 lg:grid-cols-[minmax(0,320px)_1fr]">
          <div className="bankcard-preview">
            <BankCard c={edit} t={t} lang={lang} preview />
          </div>
          <form onSubmit={save} className="grid gap-4 sm:grid-cols-2 self-start">
            <Field label={t('card_number')}>
              <input className="input" dir="ltr" inputMode="numeric" required maxLength={20}
                placeholder="6037••••••••••••"
                value={edit.card_number} onChange={(e) => setEdit({ ...edit, card_number: e.target.value })} />
            </Field>
            <Field label={t('holder')}>
              <input className="input" required placeholder={t('card_holder_placeholder')}
                value={edit.holder_name} onChange={(e) => setEdit({ ...edit, holder_name: e.target.value })} />
            </Field>
            <Field label={t('bank')}>
              <input className="input" placeholder={t('bank_name_placeholder')}
                value={edit.bank_name} onChange={(e) => setEdit({ ...edit, bank_name: e.target.value })} />
            </Field>
            <Field label={lang === 'fa' ? 'ترتیب نمایش' : 'Sort order'}>
              <input className="input" dir="ltr" type="number"
                value={edit.sort_order} onChange={(e) => setEdit({ ...edit, sort_order: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <Toggle checked={edit.is_active}
                onChange={(v) => setEdit({ ...edit, is_active: v })} label={t('active')} />
              {t('active')}
            </label>
            <div className="col-span-full flex gap-2">
              <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : t('save')}</button>
              <button type="button" className="btn-ghost text-sm" onClick={() => setEdit(null)}>{t('cancel')}</button>
            </div>
          </form>
        </div>
      )}

      {cards.length === 0 && !edit && (
        <div className="card text-center text-muted">{t('none_found')}</div>
      )}

      {cards.length > 0 && (
        <div className="cd-list-head">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <span style={{ color: 'var(--c-primary)' }}><MIco d={MI.layers} /></span>{s.list_title}
          </h3>
          <span className="text-xs text-muted">{s.list_hint}</span>
        </div>
      )}

      <div className="bankcards-grid">
        {cards.map((c) => (
          <div className="bankcard-cell" key={c.id}>
            <BankCard c={c} t={t} lang={lang} />
            <div className="bankcard-actions">
              <button className="btn-ghost text-xs" onClick={() => setEdit({ ...c })}>{t('edit')}</button>
              <span className="bankcard-order">{s.order}: <b className="mono-num">{digits(c.sort_order ?? 0, lang)}</b></span>
              <span className="bankcard-actions-sp">
                <Toggle checked={c.is_active} onChange={() => toggle(c)} label={t('active')} />
              </span>
              <button className="btn-ghost text-xs bankcard-del" onClick={() => del(c)}>{t('delete')}</button>
            </div>
          </div>
        ))}
      </div>

      {cards.length > 1 && (
        <div className="card flex justify-between font-bold">
          <span>{t('total')}</span><span>{toman(d.grand_total, lang)}</span>
        </div>
      )}
    </div>
  )
}

const CSS = `
.cd-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.cd-add { flex-shrink: 0; }
.cd-badge { font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 999px; background: color-mix(in srgb, var(--c-primary) 14%, transparent); color: var(--c-primary); white-space: nowrap; }

.cd-metrics { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 768px) { .cd-metrics { grid-template-columns: repeat(3, 1fr); } }
.cd-metric { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.cd-metric-label { font-size: 12px; font-weight: 600; color: var(--c-text-muted); }
.cd-metric-val { font-size: 20px; font-weight: 800; letter-spacing: -.01em; margin-top: 5px; }
.cd-metric-unit { font-size: 11px; font-weight: 500; color: var(--c-text-muted); }
.cd-metric-sub { font-size: 11px; color: var(--c-text-muted); margin-top: 4px; }
.cd-metric-ico { width: 46px; height: 46px; border-radius: 13px; display: grid; place-items: center; flex-shrink: 0; }

.cd-list-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; justify-content: space-between; }

.bankcards-grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
.bankcard-cell { display: flex; flex-direction: column; gap: 10px; }
.bankcard-preview { max-width: 320px; }
.bankcard-order { font-size: 11px; color: var(--c-text-muted); white-space: nowrap; }
.bankcard-order b { color: var(--c-text); }

.bankcard {
  position: relative; overflow: hidden;
  border-radius: 16px; padding: 20px; color: #fff;
  min-height: 216px;
  display: flex; flex-direction: column; justify-content: space-between;
  background:
    radial-gradient(130% 130% at 100% 0%, color-mix(in srgb, var(--c-secondary) 92%, #fff) 0%, transparent 46%),
    linear-gradient(135deg, var(--c-primary) 0%, color-mix(in srgb, var(--c-primary) 52%, #06284a) 100%);
  box-shadow: 0 14px 34px -10px color-mix(in srgb, var(--c-primary) 50%, transparent);
}
.bankcard::after {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(115deg, transparent 42%, rgba(255,255,255,.12) 50%, transparent 58%);
}
.bankcard > * { position: relative; z-index: 1; }
.bankcard--off { filter: grayscale(.65) brightness(.82); }

.bankcard-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.bankcard-foot { align-items: flex-end; }
.bankcard-bank { font-weight: 700; font-size: 14px; text-shadow: 0 1px 2px rgba(0,0,0,.25); }
.bankcard-state {
  font-size: 9.5px; font-weight: 700; padding: 3px 9px; border-radius: 999px;
  text-transform: uppercase; letter-spacing: .04em; white-space: nowrap;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.25);
}
.bankcard-state.on { background: color-mix(in srgb, var(--c-success) 88%, transparent); color: #fff; }
.bankcard-state.off { background: rgba(0,0,0,.32); }

.bankcard-chip {
  position: relative;
  width: 40px; height: 30px; border-radius: 6px; margin: 2px 0;
  background: linear-gradient(135deg, #f0e2b6, #c7a852);
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.15);
}
.bankcard-chip::before {
  content: ''; position: absolute; inset: 7px 5px; border: 1px solid rgba(0,0,0,.22); border-radius: 3px;
}

.bankcard-num { font-size: 19px; font-weight: 600; letter-spacing: 2px; text-shadow: 0 1px 3px rgba(0,0,0,.35); }
@media (max-width: 360px) { .bankcard-num { font-size: 16px; letter-spacing: 1px; } }

.bankcard-label { display: block; font-size: 8.5px; text-transform: uppercase; letter-spacing: .07em; opacity: .72; }
.bankcard-name { font-size: 13px; font-weight: 600; }
.bankcard-brand { font-size: 12px; font-weight: 800; font-style: italic; letter-spacing: .12em; opacity: .85; }

/* deposit totals printed on the card — a translucent strip flush to the bottom edge */
.bankcard-deposits {
  margin: 14px -20px -20px; padding: 9px 20px;
  background: rgba(0,0,0,.24);
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.bankcard-deposits .bankcard-label { display: inline; margin-inline-end: 5px; }
.bankcard-dep b { font-size: 13px; font-weight: 700; }
.bankcard-dep-count { display: inline-flex; align-items: baseline; gap: 4px; white-space: nowrap; }
.bankcard-dep-count b { font-size: 13px; font-weight: 700; }

.bankcard-actions { display: flex; align-items: center; gap: 8px; padding: 0 2px; }
.bankcard-actions-sp { margin-inline-start: auto; display: inline-flex; }
.bankcard-del:hover { color: var(--c-danger); border-color: var(--c-danger); }
`
