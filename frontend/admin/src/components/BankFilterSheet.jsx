// Bank/payment-method filter — shares the DateRangePicker's dialog/sheet
// chrome (.drp-*, see DateRangePicker.jsx — its CSS must be mounted
// alongside BFS_CSS). Banks come from the admin's real registered receiving
// cards (/admin/cards/); methods come from the real Payment.method enum.
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'

const T = {
  fa: {
    title: 'فیلتر بانک‌ها و روش پرداخت',
    banks_h: 'بانک‌های مقصد', methods_h: 'روش تأیید تراکنش',
    all: 'انتخاب همه', clear: 'پاک‌سازی', apply: 'اعمال فیلتر', cancel: 'انصراف',
    none: 'هنوز کارت بانکی‌ای ثبت نشده است',
  },
  en: {
    title: 'Filter by bank & payment method',
    banks_h: 'Destination banks', methods_h: 'Confirmation method',
    all: 'Select all', clear: 'Clear', apply: 'Apply filter', cancel: 'Cancel',
    none: 'No bank cards registered yet',
  },
}
const METHODS = ['card_manual', 'sms_auto', 'gateway']

/** value/onApply shape: { banks: string[], methods: string[] } */
export function BankFilterSheet({ open, onClose, value, onApply }) {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [cards, setCards] = useState(null)
  const [banks, setBanks] = useState(value?.banks || [])
  const [methods, setMethods] = useState(value?.methods || [])

  useEffect(() => {
    if (!open) return
    api.get('/admin/cards/').then((r) => setCards(r.data.results || r.data || [])).catch(() => setCards([]))
    setBanks(value?.banks || [])
    setMethods(value?.methods || [])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!open) return null

  const bankNames = [...new Set((cards || []).map((c) => c.bank_name).filter(Boolean))]
  const toggleBank = (b) => setBanks((cur) => (cur.includes(b) ? cur.filter((x) => x !== b) : [...cur, b]))
  const toggleMethod = (m) => setMethods((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]))
  const apply = () => { onApply({ banks, methods }); onClose() }
  const clear = () => { setBanks([]); setMethods([]); onApply({ banks: [], methods: [] }); onClose() }

  return (
    <div className="drp-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="drp-sheet card" role="dialog" aria-modal="true">
        <div className="drp-handle" />
        <div className="drp-head">
          <h2 className="font-bold text-sm">{s.title}</h2>
          <button type="button" className="drp-icon-btn" onClick={onClose} aria-label={s.cancel}>✕</button>
        </div>

        <div className="drp-body">
          <div>
            <div className="bfs-row-head">
              <span className="drp-presets-label" style={{ marginBottom: 0 }}>{s.banks_h}</span>
              <div className="flex gap-2">
                <button type="button" className="bfs-mini-btn" onClick={() => setBanks(bankNames)}>{s.all}</button>
                <button type="button" className="bfs-mini-btn" onClick={() => setBanks([])}>{s.clear}</button>
              </div>
            </div>
            {cards === null ? (
              <div className="text-xs text-muted py-2">…</div>
            ) : bankNames.length === 0 ? (
              <div className="text-xs text-muted py-2">{s.none}</div>
            ) : (
              <div className="bfs-chip-grid">
                {bankNames.map((b) => (
                  <button key={b} type="button" className={'bfs-chip' + (banks.includes(b) ? ' on' : '')} onClick={() => toggleBank(b)}>
                    <span className="bfs-chip-dot" />{b}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <span className="drp-presets-label">{s.methods_h}</span>
            <div className="bfs-chip-grid">
              {METHODS.map((m) => (
                <button key={m} type="button" className={'bfs-chip' + (methods.includes(m) ? ' on' : '')} onClick={() => toggleMethod(m)}>
                  <span className="bfs-chip-dot" />{enumLabel(t, 'm_', m)}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="drp-foot">
          <button type="button" className="btn-ghost text-sm" onClick={clear}>{s.clear}</button>
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{s.cancel}</button>
          <button type="button" className="btn-primary text-sm" onClick={apply}>{s.apply}</button>
        </div>
      </div>
    </div>
  )
}

export const BFS_CSS = `
.bfs-row-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.bfs-mini-btn { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 999px; color: var(--c-text-muted); border: 1px solid var(--c-border); }
.bfs-mini-btn:hover { color: var(--c-primary); border-color: var(--c-primary); }
.bfs-chip-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
.bfs-chip { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 10px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bfs-chip:hover { border-color: var(--c-primary); }
.bfs-chip-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--c-text-muted); flex-shrink: 0; }
.bfs-chip.on { border-color: color-mix(in srgb, var(--c-success) 45%, transparent); background: color-mix(in srgb, var(--c-success) 12%, transparent); color: var(--c-success); }
.bfs-chip.on .bfs-chip-dot { background: var(--c-success); }
.bfs-filter-btn { display: inline-flex; align-items: center; gap: 6px; }
.bfs-count-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 16px; height: 16px; padding: 0 4px;
  border-radius: 999px; font-size: 10px; font-weight: 700; background: var(--c-success); color: #fff; }
`
