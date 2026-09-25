import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman, digits } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'
import { useToast } from '../components/Toast'
import { useDeleteConfirm } from '../lib/confirmDelete'

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
    add: 'افزودن کارت جدید',
    fraud_h: 'تنظیمات ضد کلاهبرداری و مبالغ یکتای واریزی',
    fraud_body: 'سیستم به‌صورت خودکار به هر فاکتور کارت‌به‌کارت یک مبلغ تصادفی بین {min} تا {max} تومان اضافه می‌کند تا واریزکنندهٔ فیش، از روی شناسهٔ مبلغ و پیامک بانک به‌صورت خودکار در دیتابیس شناسایی و اکانتش فوراً فعال شود.',
    fraud_edit: 'ویرایش بازهٔ مبلغ در تنظیمات',
    modal_new: 'ثبت کارت جدید', modal_edit: 'ویرایش کارت: {n}',
    modal_sub: 'مشخصات حساب برای دریافت و تطبیق خودکار واریزی کاربران',
    f_number: 'شماره کارت بانکی (16 رقمی)', f_holder: 'نام و نام‌خانوادگی صاحب حساب',
    f_bank: 'نام بانک', f_order: 'ترتیب نمایش (اولویت)',
    f_active: 'فعال در درگاه واریز',
    f_active_hint: 'در صورت غیرفعال بودن، این کارت در فاکتورهای پرداخت نمایش داده نمی‌شود.',
    save: 'ذخیره و ثبت تغییرات', cancel: 'انصراف',
  },
  en: {
    title: 'Bank cards', connected: '{n} cards connected',
    subtitle: 'Manage the active card numbers used for card-to-card payments in the bot and website',
    m_total: 'Total successful deposits', m_total_sub: '{n} approved transactions',
    m_active: 'Cards ready to receive', m_active_u: 'active', m_active_sub: 'automatic unique-amount rotation',
    m_count: 'Total deposits', m_count_u: 'deposits', m_count_sub: 'across all cards',
    list_title: 'Active bank cards in the system', list_hint: 'Bot display priority follows the sort order',
    order: 'Sort order',
    add: 'Add new card',
    fraud_h: 'Anti-fraud & unique deposit amounts',
    fraud_body: 'The system automatically adds a random amount between {min} and {max} toman to every card-to-card invoice, so the depositor is auto-identified in the database from the amount code + the bank SMS and their account is activated instantly — no receipt needed.',
    fraud_edit: 'Edit the amount range in Settings',
    modal_new: 'Add a new card', modal_edit: 'Edit card: {n}',
    modal_sub: 'Account details for receiving and auto-matching user deposits',
    f_number: 'Card number (16 digits)', f_holder: 'Account holder full name',
    f_bank: 'Bank name', f_order: 'Display order (priority)',
    f_active: 'Active in the deposit gateway',
    f_active_hint: 'When off, this card is not shown on payment invoices.',
    save: 'Save changes', cancel: 'Cancel',
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

function MIco({ d, w = 20 }) {
  return <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
}
const MI = {
  vault: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="12" cy="12" r="3" /><path d="M12 9V6M12 18v-3M15 12h3M6 12h3" /></>,
  card: <><rect x="1" y="4" width="22" height="16" rx="2" /><path d="M1 10h22" /></>,
  layers: <><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5M2 12l10 5 10-5" /></>,
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  close: <path d="M18 6L6 18M6 6l12 12" />,
  check: <polyline points="20 6 9 17 4 12" />,
  plus: <path d="M12 5v14M5 12h14" />,
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

function CardModal({ row, s, t, lang, onClose, onSaved }) {
  const toast = useToast()
  const editing = !!row
  const [f, setF] = useState(() => (row ? { ...blank, ...row } : { ...blank }))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    const body = {
      card_number: String(f.card_number).replace(/\s+/g, ''),
      holder_name: f.holder_name,
      bank_name: f.bank_name || '',
      sort_order: Number(f.sort_order) || 0,
      is_active: f.is_active,
    }
    toast.loading(t('action_in_progress'))
    try {
      if (editing) await api.patch(`/admin/cards/${row.id}/`, body)
      else await api.post('/admin/cards/', body)
      toast.success(t('saved'))
      onSaved()
    } catch (e2) { setErr(apiError(e2)); toast.error(apiError(e2)) } finally { setBusy(false) }
  }

  return (
    <div className="cd-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="cd-modal card" onSubmit={submit} role="dialog" aria-modal="true">
        <div className="cd-modal-head">
          <div>
            <h2 className="font-bold flex items-center gap-2">
              <span style={{ color: 'var(--c-primary)' }}><MIco d={MI.card} w={18} /></span>
              {editing ? s.modal_edit.replace('{n}', row.holder_name || groupNumber(row.card_number)) : s.modal_new}
            </h2>
            <p className="text-xs text-muted mt-0.5">{s.modal_sub}</p>
          </div>
          <button type="button" className="cd-icon-btn" onClick={onClose} aria-label={s.cancel}><MIco d={MI.close} w={16} /></button>
        </div>

        <div className="cd-modal-body">
          <Alert>{err}</Alert>
          <div className="cd-modal-preview"><BankCard c={f} t={t} lang={lang} preview /></div>

          <div className="cd-modal-grid">
            <Field label={s.f_number}>
              <input className="input mono-num" dir="ltr" inputMode="numeric" required maxLength={23}
                placeholder="6037 •••• •••• ••••"
                value={f.card_number} onChange={(e) => setF({ ...f, card_number: e.target.value })} />
            </Field>
            <Field label={s.f_holder}>
              <input className="input" required placeholder={t('card_holder_placeholder')}
                value={f.holder_name} onChange={(e) => setF({ ...f, holder_name: e.target.value })} />
            </Field>
            <Field label={s.f_bank}>
              <input className="input" list="cd-banks" placeholder={t('bank_name_placeholder')}
                value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} />
              <datalist id="cd-banks">
                {['بلو بانک', 'بانک سامان', 'بانک ملت', 'بانک پاسارگاد', 'بانک ملی ایران', 'بانک تجارت', 'بانک صادرات', 'بانک رسالت'].map((b) => <option key={b} value={b} />)}
              </datalist>
            </Field>
            <Field label={s.f_order}>
              <input className="input" dir="ltr" type="number"
                value={f.sort_order} onChange={(e) => setF({ ...f, sort_order: e.target.value })} />
            </Field>
          </div>

          <div className="cd-modal-toggle">
            <div>
              <span className="text-sm font-semibold block">{s.f_active}</span>
              <span className="text-xs text-muted">{s.f_active_hint}</span>
            </div>
            <Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} label={s.f_active} />
          </div>
        </div>

        <div className="cd-modal-foot">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{s.cancel}</button>
          <button type="submit" className="btn-primary text-sm" disabled={busy}>
            {busy ? '…' : <><MIco d={MI.check} w={15} /> {s.save}</>}
          </button>
        </div>
      </form>
    </div>
  )
}

export default function Cards() {
  const { t, lang } = useI18n()
  const toast = useToast()
  const s = L[lang] || L.fa
  const [d, setD] = useState(null)
  const [modal, setModal] = useState(null) // { row } | { row: null } | null
  const [err, setErr] = useState('')
  const [range, setRange] = useState(null) // { min, max }

  const load = () =>
    api.get('/admin/cards/deposit-report/')
      .then((r) => { setD(r.data); setErr('') })
      .catch(() => { setD({ cards: [], grand_total: 0 }); setErr(t('load_error')) })
  useEffect(() => {
    load()
    api.get('/admin/settings/').then((r) => {
      const kv = Object.fromEntries(r.data.settings.map((x) => [x.key, x.value]))
      setRange({ min: kv.unique_amount_min, max: kv.unique_amount_max })
    }).catch(() => {})
  }, [])

  const toggle = async (c) => {
    setErr('')
    try {
      await api.patch(`/admin/cards/${c.id}/`, { is_active: !c.is_active })
      setD((p) => ({ ...p, cards: p.cards.map((x) => (x.id === c.id ? { ...x, is_active: !x.is_active } : x)) }))
    } catch (e2) { setErr(apiError(e2)); toast.error(apiError(e2)) }
  }
  const askDelete = useDeleteConfirm()
  const del = async (c) => {
    const ok = await askDelete({ what: (lang === 'en' ? 'bank card' : 'کارت بانکی'), name: c.card_number, id: c.id,
      note: c.holder_name || undefined, action: () => api.delete(`/admin/cards/${c.id}/`) })
    if (ok) { load(); toast.success(t('deleted')) }
  }
  const onSaved = () => { setModal(null); load() }

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
        <button className="btn-primary text-sm cd-add inline-flex items-center gap-1.5" onClick={() => setModal({ row: null })}>
          <MIco d={MI.plus} w={14} /> {s.add}
        </button>
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

      {/* anti-fraud / unique-amount info card — real range from /admin/settings/ */}
      <div className="card cd-fraud">
        <span className="cd-fraud-ico"><MIco d={MI.shield} w={18} /></span>
        <div className="min-w-0">
          <span className="font-bold text-sm block">{s.fraud_h}</span>
          <p className="text-xs text-muted leading-6 mt-1">
            {s.fraud_body
              .replace('{min}', range ? digits(range.min, lang) : '—')
              .replace('{max}', range ? digits(range.max, lang) : '—')}
          </p>
          <Link to="/settings/unique-amount" className="cd-fraud-link">{s.fraud_edit} →</Link>
        </div>
      </div>

      {cards.length === 0 ? (
        <div className="card text-center text-muted">{t('none_found')}</div>
      ) : (
        <>
          <div className="cd-list-head">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <span style={{ color: 'var(--c-primary)' }}><MIco d={MI.layers} /></span>{s.list_title}
            </h3>
            <span className="text-xs text-muted">{s.list_hint}</span>
          </div>

          <div className="bankcards-grid">
            {cards.map((c) => (
              <div className="bankcard-cell" key={c.id}>
                <BankCard c={c} t={t} lang={lang} />
                <div className="bankcard-actions">
                  <button className="btn-ghost text-xs" onClick={() => setModal({ row: c })}>{t('edit')}</button>
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
        </>
      )}

      {modal && <CardModal row={modal.row} s={s} t={t} lang={lang} onClose={() => setModal(null)} onSaved={onSaved} />}
    </div>
  )
}

const CSS = `
.cd-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.cd-add { flex-shrink: 0; }
.cd-badge { font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 999px; background: color-mix(in srgb, var(--c-primary) 14%, transparent); color: var(--c-primary); white-space: nowrap; }

.cd-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr)); gap: 14px; }
.cd-metric { min-width: 0; display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.cd-metric-label { font-size: 12px; font-weight: 600; color: var(--c-text-muted); }
.cd-metric-val { overflow-wrap: anywhere; font-size: 20px; font-weight: 800; letter-spacing: -.01em; margin-top: 5px; }
.cd-metric-unit { font-size: 11px; font-weight: 500; color: var(--c-text-muted); }
.cd-metric-sub { font-size: 11px; color: var(--c-text-muted); margin-top: 4px; }
.cd-metric-ico { width: 46px; height: 46px; border-radius: 13px; display: grid; place-items: center; flex-shrink: 0; }

.cd-fraud { display: flex; gap: 14px; align-items: flex-start;
  border-color: color-mix(in srgb, var(--c-warning) 30%, var(--c-border));
  background: color-mix(in srgb, var(--c-warning) 6%, var(--c-surface)); }
.cd-fraud-ico { width: 38px; height: 38px; border-radius: 11px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-warning) 16%, transparent); color: var(--c-warning); }
.cd-fraud-link { display: inline-block; margin-top: 8px; font-size: 12px; font-weight: 600; color: var(--c-primary); }
.cd-fraud-link:hover { text-decoration: underline; }

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

/* edit modal */
.cd-backdrop { position: fixed; inset: 0; z-index: 60; background: color-mix(in srgb, #0b1220 62%, transparent); backdrop-filter: blur(3px); display: flex; align-items: flex-start; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.cd-modal { width: 100%; max-width: 560px; padding: 0; overflow: hidden; }
.cd-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.cd-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.cd-modal-preview { max-width: 320px; margin: 0 auto; width: 100%; }
.cd-modal-grid { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 480px) { .cd-modal-grid { grid-template-columns: 1fr 1fr; } }
.cd-modal-toggle { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 14px; border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--c-primary) 22%, transparent); background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.cd-modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--c-border); }
.cd-modal-foot .btn-primary { display: inline-flex; align-items: center; gap: 6px; }
.cd-icon-btn { padding: 6px; border-radius: 9px; color: var(--c-text-muted); }
.cd-icon-btn:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
`
