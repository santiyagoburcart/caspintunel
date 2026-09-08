import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman, digits } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

const blank = { card_number: '', holder_name: '', bank_name: '', sort_order: 0, is_active: true }

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

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <style>{CSS}</style>

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{lang === 'fa' ? 'کارت‌های بانکی' : 'Bank cards'}</h1>
        {!edit && (
          <button className="btn-primary text-sm" onClick={() => setEdit({ ...blank })}>{t('add_card')}</button>
        )}
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

      {(d.cards || []).length === 0 && !edit && (
        <div className="card text-center text-muted">{t('none_found')}</div>
      )}

      <div className="bankcards-grid">
        {(d.cards || []).map((c) => (
          <div className="bankcard-cell" key={c.id}>
            <BankCard c={c} t={t} lang={lang} />
            <div className="bankcard-actions">
              <button className="btn-ghost text-xs" onClick={() => setEdit({ ...c })}>{t('edit')}</button>
              <span className="bankcard-actions-sp">
                <Toggle checked={c.is_active} onChange={() => toggle(c)} label={t('active')} />
              </span>
              <button className="btn-ghost text-xs bankcard-del" onClick={() => del(c)}>{t('delete')}</button>
            </div>
          </div>
        ))}
      </div>

      {(d.cards || []).length > 1 && (
        <div className="card flex justify-between font-bold">
          <span>{t('total')}</span><span>{toman(d.grand_total, lang)}</span>
        </div>
      )}
    </div>
  )
}

const CSS = `
.bankcards-grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
.bankcard-cell { display: flex; flex-direction: column; gap: 10px; }
.bankcard-preview { max-width: 320px; }

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
