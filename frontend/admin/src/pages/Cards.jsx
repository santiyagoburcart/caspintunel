import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Alert, Field, Spinner } from '../components/ui'

const blank = { card_number: '', holder_name: '', bank_name: '', sort_order: 0, is_active: true }

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
    if (!confirm(lang === 'fa' ? 'حذف این کارت؟' : 'Delete this card?')) return
    try { await api.delete(`/admin/cards/${c.id}/`); load() } catch (e2) { setErr(apiError(e2)) }
  }

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{lang === 'fa' ? 'کارت‌های بانکی' : 'Bank cards'}</h1>
        <button className="btn-primary text-sm" onClick={() => setEdit({ ...blank })}>{t('create')}</button>
      </div>
      <Alert>{err}</Alert>

      {edit && (
        <form onSubmit={save} className="card grid gap-4 sm:grid-cols-2">
          <Field label={t('card_number')}>
            <input className="input" dir="ltr" inputMode="numeric" required maxLength={20}
              placeholder="6037••••••••••••"
              value={edit.card_number} onChange={(e) => setEdit({ ...edit, card_number: e.target.value })} />
          </Field>
          <Field label={t('holder')}>
            <input className="input" required
              value={edit.holder_name} onChange={(e) => setEdit({ ...edit, holder_name: e.target.value })} />
          </Field>
          <Field label={t('bank')}>
            <input className="input"
              value={edit.bank_name} onChange={(e) => setEdit({ ...edit, bank_name: e.target.value })} />
          </Field>
          <Field label={lang === 'fa' ? 'ترتیب نمایش' : 'Sort order'}>
            <input className="input" dir="ltr" type="number"
              value={edit.sort_order} onChange={(e) => setEdit({ ...edit, sort_order: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={edit.is_active}
              onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
            {t('active')}
          </label>
          <div className="col-span-full flex gap-2">
            <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : t('save')}</button>
            <button type="button" className="btn-ghost text-sm" onClick={() => setEdit(null)}>{t('cancel')}</button>
          </div>
        </form>
      )}

      <DataTable
        empty={t('none_found')}
        columns={[
          { key: 'card_number', label: t('card_number'), render: (r) => <span dir="ltr">{r.card_number}</span> },
          { key: 'holder_name', label: t('holder') },
          { key: 'bank_name', label: t('bank'), render: (r) => r.bank_name || '—' },
          { key: 'deposit_count', label: t('deposit_count'), render: (r) => r.deposit_count || 0 },
          { key: 'deposit_total', label: t('deposit_total'), render: (r) => toman(r.deposit_total || 0, lang) },
          { key: 'is_active', label: t('active'), render: (r) => (r.is_active ? '✓' : '—') },
          { key: 'act', label: '', render: (r) => (
            <span className="flex gap-1">
              <button className="btn-ghost text-xs" onClick={() => setEdit({ ...r })}>✎</button>
              <button className="btn-ghost text-xs" onClick={() => toggle(r)}>
                {r.is_active ? t('disable') : t('enable')}
              </button>
              <button className="btn-ghost text-xs" onClick={() => del(r)}>🗑</button>
            </span>
          ) },
        ]}
        rows={d.cards || []}
      />
      <div className="card flex justify-between font-bold">
        <span>{t('total')}</span><span>{toman(d.grand_total, lang)}</span>
      </div>
    </div>
  )
}
