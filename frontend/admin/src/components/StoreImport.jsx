import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, digits, toman } from '../lib/format'
import { useConfirm } from './ConfirmDialog'

// v1.56 «ورود داده از ربات قبلی» on our «فروشگاه» card (backend apps/tenancy/importers, docs/store-import.md). Our staff upload
// the old bot's database dump → a background scan shows what WOULD happen (nothing is written) → plans are mapped, large
// balances confirmed one by one, the checklist ticked → the import runs (DB backup first). PasarGuard is never changed:
// existing accounts are only linked, and only when the store's own PasarGuard admin owns them. «بازگردانی» removes it again.
const T = {
  fa: {
    title: 'ورود داده از ربات قبلی', desc: 'مشتری‌ها، سرویس‌ها، موجودی کیف پول و سابقهٔ پرداخت ربات قبلی نماینده را به همین فروشگاه می‌آورد. تا «شروع ورود» را نزنید چیزی نوشته نمی‌شود.',
    pick: 'انتخاب فایل پشتیبان (.zip / .sql / .sql.gz)', upload: 'بارگذاری و بررسی', none: 'هنوز فایلی بارگذاری نشده است.',
    st_uploaded: 'در صف بررسی', st_scanning: 'در حال بررسی', st_ready: 'پیش‌نمایش آماده', st_running: 'در حال ورود', st_done: 'انجام شد',
    st_failed: 'ناموفق', st_undone: 'بازگردانده شد', st_discarded: 'کنار گذاشته شد',
    source: 'منبع', store_rules: 'قوانین ثبت‌نام همین فروشگاه برای مشتری‌های واردشده هم اجرا می‌شود:',
    phone_on: 'شماره موبایل اجباری است — هر مشتری در اولین ورود به ربات یا مینی‌اپ شماره‌اش را می‌فرستد.',
    phone_off: 'شماره موبایل اجباری نیست — مشتری‌ها بدون شماره وارد می‌شوند.', iran_only: 'فقط شمارهٔ ایران پذیرفته می‌شود.',
    customers: 'مشتری‌ها', c_new: 'جدید', c_existing: 'از قبل در فروشگاه', c_blocked: 'مسدود در ربات قبلی (غیرفعال وارد می‌شوند)',
    c_agents: 'نمایندهٔ ربات قبلی', c_phone: 'با شماره', c_ref: 'با معرف',
    services: 'سرویس‌ها', reseller: 'فقط اکانت‌های این ادمین پاسارگارد وصل می‌شوند:',
    missing_live: 'فعال در ربات قبلی ولی در پاسارگارد پیدا نشد — برای بررسی نماینده', report: 'دریافت گزارش کامل (CSV)',
    plans: 'پلن سرویس‌ها', plans_hint: 'برای تمدید، هر محصول ربات قبلی را به یکی از پلن‌های این فروشگاه وصل کنید (یا «بدون پلن» — مشتری هنگام تمدید پلن را انتخاب می‌کند).',
    no_plan: 'بدون پلن', svc_n: '{n} سرویس', gbdays: '{g} گیگ · {d} روز',
    credits: 'موجودی کیف پول → کد اعتبار یک‌بار مصرف', credits_sum: '{n} مشتری · جمع {t}', credit_days: 'اعتبار کدها (روز)',
    review: 'موجودی‌های بزرگ‌تر از {t} — فقط با تأیید شما وارد می‌شوند:', confirm_credit: 'تأیید و وارد کردن',
    history: 'سابقهٔ پرداخت (فقط نمایش در «مشتری ۳۶۰»، جزو درآمد نیست)', history_sum: '{n} پرداخت موفق · جمع {t}',
    check: 'ربات قبلی فروش را متوقف کرده است', check_hint: 'وگرنه یک اکانت ممکن است در دو جا تمدید شود.',
    run: 'شروع ورود', run_t: 'شروع ورود داده', run_m: 'اول یک پشتیبان از پایگاه داده گرفته می‌شود، سپس {c} مشتری و {s} سرویس وارد فروشگاه «{n}» می‌شوند. در پاسارگارد چیزی تغییر نمی‌کند و به مشتری‌ها پیامی فرستاده نمی‌شود.',
    discard: 'کنار گذاشتن', undo: 'بازگردانی', undo_t: 'بازگردانی ورود داده', undo_m: 'هر چه این ورود ساخته (مشتری، اتصال سرویس، کد اعتبار، سابقه) و از آن به بعد استفاده نشده حذف می‌شود. اکانت‌های پاسارگارد دست نمی‌خورند.',
    result: 'نتیجه', r_customers_created: 'مشتری جدید', r_customers_existing: 'مشتری موجود', r_services_linked: 'سرویس وصل شد',
    r_services_failed: 'سرویس ناموفق', r_referrals: 'معرف', r_credits: 'کد اعتبار', r_credits_held: 'موجودی نگه داشته شد', r_history: 'سابقهٔ پرداخت',
    kept: '{n} مورد به خاطر استفاده پس از ورود نگه داشته شد.', by: 'توسط', file_until: 'فایل تا {t} نگه داشته می‌شود', again: 'بارگذاری فایل دیگر',
  },
  en: {
    title: 'Import from the previous bot', desc: 'Brings the reseller’s customers, services, wallet balances and payment history from their old bot into this store. Nothing is written until you press “Start import”.',
    pick: 'Choose the backup file (.zip / .sql / .sql.gz)', upload: 'Upload and check', none: 'No file uploaded yet.',
    st_uploaded: 'Queued', st_scanning: 'Checking', st_ready: 'Preview ready', st_running: 'Importing', st_done: 'Done',
    st_failed: 'Failed', st_undone: 'Undone', st_discarded: 'Discarded',
    source: 'Source', store_rules: 'This store’s sign-up rules apply to imported customers too:',
    phone_on: 'Phone number required — each customer shares it the first time they open the bot or Mini App.',
    phone_off: 'Phone number not required — customers come in without one.', iran_only: 'Iranian numbers only.',
    customers: 'Customers', c_new: 'new', c_existing: 'already in the store', c_blocked: 'blocked in the old bot (imported as disabled)',
    c_agents: 'agents of the old bot', c_phone: 'with phone', c_ref: 'with a referrer',
    services: 'Services', reseller: 'Only accounts of this PasarGuard admin are linked:',
    missing_live: 'Active in the old bot but not found on PasarGuard — for the reseller to check', report: 'Download the full report (CSV)',
    plans: 'Service plans', plans_hint: 'For renewals, match each product of the old bot to a plan of this store (or “No plan” — the customer picks one when renewing).',
    no_plan: 'No plan', svc_n: '{n} services', gbdays: '{g} GB · {d} days',
    credits: 'Wallet balances → one-use credit codes', credits_sum: '{n} customers · total {t}', credit_days: 'Code validity (days)',
    review: 'Balances above {t} — imported only when you confirm:', confirm_credit: 'Confirm and import',
    history: 'Payment history (shown on Customer 360 only, not revenue)', history_sum: '{n} paid payments · total {t}',
    check: 'The old bot has stopped selling', check_hint: 'Otherwise one account may be renewed in two places.',
    run: 'Start import', run_t: 'Start the import', run_m: 'A database backup is taken first, then {c} customers and {s} services come into “{n}”. Nothing changes on PasarGuard and no customer is messaged.',
    discard: 'Discard', undo: 'Undo', undo_t: 'Undo the import', undo_m: 'Everything this import made (customers, linked services, credit codes, history) and nothing used since is removed. PasarGuard accounts are not touched.',
    result: 'Result', r_customers_created: 'new customers', r_customers_existing: 'existing customers', r_services_linked: 'services linked',
    r_services_failed: 'services failed', r_referrals: 'referrers', r_credits: 'credit codes', r_credits_held: 'balances held', r_history: 'payment notes',
    kept: '{n} items were kept because they were used after the import.', by: 'by', file_until: 'File kept until {t}', again: 'Upload another file',
  },
}
const BUSY = ['uploaded', 'scanning', 'running']
const SVC_ORDER = ['link', 'linked', 'missing', 'other_admin', 'linked_elsewhere', 'test', 'not_sold', 'no_customer', 'duplicate', 'already', 'failed']

export default function StoreImport({ base, storeName }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const [d, setD] = useState(null)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [choice, setChoice] = useState({ plan_map: {}, confirm_credits: [], credit_days: 180, old_bot_stopped: false })
  const timer = useRef(null)
  const load = () => api.get(base).then((r) => setD(r.data)).catch(() => setD((x) => x || { results: [] }))
  useEffect(() => { load(); return () => clearTimeout(timer.current) }, [base])
  useEffect(() => { clearTimeout(timer.current); if (d?.busy) timer.current = setTimeout(load, 2500) }, [d])
  const cur = d?.results?.[0]
  const pv = cur?.preview
  useEffect(() => {                                       // the suggested plan for each product, once per preview
    if (cur?.state === 'ready' && pv?.plan_groups) {
      setChoice((c) => ({ ...c, credit_days: pv.credit_days || 180,
        plan_map: Object.fromEntries(pv.plan_groups.map((g) => [g.name, c.plan_map[g.name] ?? g.suggested_plan ?? null])) }))
    }
  }, [cur?.id, cur?.state])

  const upload = async () => {
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    setBusy(true)
    try { await api.post(base, fd); setFile(null); await load() } catch { /* the toast shows why */ } finally { setBusy(false) }
  }
  const run = async () => {
    const ok = await confirm({ tone: 'warning', icon: 'cart', title: s.run_t, targetLabel: s.title, targetId: storeName,
      message: s.run_m.replace('{c}', digits(pv.customers.total, lang)).replace('{s}', digits(pv.services.link || 0, lang)).replace('{n}', storeName),
      confirmLabel: s.run, action: () => api.post(`${base}${cur.id}/run/`, choice) })
    if (ok) load()
  }
  const undo = async () => {
    const ok = await confirm({ tone: 'danger', icon: 'trash', title: s.undo_t, targetLabel: s.title, targetId: `#${cur.id}`,
      message: s.undo_m, confirmLabel: s.undo, action: () => api.post(`${base}${cur.id}/undo/`, {}) })
    if (ok) load()
  }
  const discard = async () => { try { await api.delete(`${base}${cur.id}/`); load() } catch { /* toast */ } }
  const report = async () => {
    try {
      const r = await api.get(`${base}${cur.id}/report.csv`, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = `store-import-${cur.id}-report.csv`
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000)
    } catch { /* toast */ }
  }
  const toggleCredit = (k) => setChoice((c) => ({ ...c, confirm_credits: c.confirm_credits.includes(k)
    ? c.confirm_credits.filter((x) => x !== k) : [...c.confirm_credits, k] }))

  if (!d) return null
  const showUpload = !cur || ['done', 'undone', 'discarded', 'failed'].includes(cur.state)
  const n = (v) => digits(v ?? 0, lang)
  return (
    <section className="si" data-testid="store-import">
      <style>{CSS}</style>
      <b className="si-h">{s.title}</b>
      <p className="si-desc">{s.desc}</p>

      {cur && (
        <article className="si-card" data-state={cur.state} data-testid="import-row">
          <div className="si-top">
            <span className="si-pill" data-st={cur.state}>{s['st_' + cur.state] || cur.state}</span>
            <span className="text-xs text-muted"><bdi dir="ltr">{cur.file_name}</bdi> · {jalali(cur.created_at, true, lang)} · {s.by} <bdi>{cur.created_by}</bdi></span>
          </div>
          {BUSY.includes(cur.state) && (
            <div className="si-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={cur.progress}>
              <i style={{ width: `${Math.max(3, cur.progress)}%` }} /><span>{n(`${cur.progress}%`)}</span></div>
          )}
          {cur.error && <p className="si-err" role="alert"><bdi dir="ltr">{cur.error}</bdi></p>}

          {pv && pv.source && (
            <div className="si-pv" data-testid="import-preview">
              <p className="si-line">{s.source}: <b>{pv.source.label}</b>{pv.source.panels?.length ? <> · {pv.source.panels.map((p) => p.name).join('، ')}</> : null}</p>
              <div className="si-rules" data-testid="import-rules">
                <span>{s.store_rules}</span>
                <span>{pv.store.phone_required ? s.phone_on : s.phone_off}{pv.store.phone_required && pv.store.iran_phone_only ? ` ${s.iran_only}` : ''}</span>
              </div>

              <h4>{s.customers}: {n(pv.customers.total)}</h4>
              <div className="si-kv">
                <span><b>{n(pv.customers.new)}</b> {s.c_new}</span><span><b>{n(pv.customers.existing)}</b> {s.c_existing}</span>
                <span><b>{n(pv.customers.blocked)}</b> {s.c_blocked}</span><span><b>{n(pv.customers.with_phone)}</b> {s.c_phone}</span>
                <span><b>{n(pv.customers.referred)}</b> {s.c_ref}</span>{pv.customers.agents > 0 && <span><b>{n(pv.customers.agents)}</b> {s.c_agents}</span>}
              </div>

              <h4>{s.services}: {n(pv.services.total)}</h4>
              <p className="si-line">{s.reseller} <bdi dir="ltr"><b>{pv.store.reseller}</b></bdi></p>
              <ul className="si-buckets" data-testid="import-buckets">
                {SVC_ORDER.filter((k) => pv.services[k]).map((k) => (
                  <li key={k} data-k={k}><b>{n(pv.services[k])}</b> {pv.outcomes[k]?.[lang] || k}</li>
                ))}
              </ul>
              {pv.missing_live?.length > 0 && (
                <details className="si-miss" data-testid="import-missing">
                  <summary>{s.missing_live} ({n(pv.missing_live.length)})</summary>
                  <ul>{pv.missing_live.slice(0, 200).map((m) => (
                    <li key={m.panel_username}><bdi dir="ltr">{m.panel_username}</bdi> · <bdi dir="ltr">{m.bot_status}</bdi> · {s.gbdays.replace('{g}', n(m.gb)).replace('{d}', n(m.days))}{m.sold_at ? ` · ${jalali(m.sold_at, false, lang)}` : ''}</li>
                  ))}</ul>
                </details>
              )}
              <button type="button" className="btn-ghost text-sm si-btn" onClick={report} data-testid="import-report">{s.report}</button>

              {cur.state === 'ready' && pv.plan_groups?.length > 0 && <>
                <h4>{s.plans}</h4>
                <p className="si-desc">{s.plans_hint}</p>
                <div className="si-plans">
                  {pv.plan_groups.map((g) => (
                    <label key={g.name} className="si-plan"><span><b><bdi>{g.name}</bdi></b> <small>{s.svc_n.replace('{n}', n(g.count))} · {s.gbdays.replace('{g}', n(g.gb)).replace('{d}', n(g.days))}</small></span>
                      <select className="input" value={choice.plan_map[g.name] ?? ''} data-testid="import-plan"
                        onChange={(e) => setChoice((c) => ({ ...c, plan_map: { ...c.plan_map, [g.name]: e.target.value ? Number(e.target.value) : null } }))}>
                        <option value="">{s.no_plan}</option>
                        {pv.plans.map((p) => <option key={p.id} value={p.id}>{p.name}{p.active ? '' : ' (—)'}</option>)}
                      </select></label>
                  ))}
                </div>
              </>}

              <h4>{s.credits}</h4>
              <p className="si-line">{s.credits_sum.replace('{n}', n(pv.credits.count)).replace('{t}', toman(pv.credits.total, lang))}</p>
              {pv.credits.review?.length > 0 && (
                <div className="si-review" data-testid="import-review">
                  <span>{s.review.replace('{t}', toman(pv.credits.review_above, lang))}</span>
                  {pv.credits.review.map((r) => (
                    <label key={r.key} className="si-chk"><input type="checkbox" disabled={cur.state !== 'ready'} checked={choice.confirm_credits.includes(r.key)}
                      onChange={() => toggleCredit(r.key)} data-testid="import-credit-confirm" />
                      <bdi dir="ltr">{r.who}</bdi> · <b>{toman(r.amount, lang)}</b> — {s.confirm_credit}</label>
                  ))}
                </div>
              )}
              {cur.state === 'ready' && (
                <label className="si-f"><span>{s.credit_days}</span>
                  <input className="input" type="number" min="7" max="365" dir="ltr" inputMode="numeric" value={choice.credit_days}
                    onChange={(e) => setChoice((c) => ({ ...c, credit_days: e.target.value }))} /></label>
              )}

              <h4>{s.history}</h4>
              <p className="si-line">{s.history_sum.replace('{n}', n(pv.history.paid)).replace('{t}', toman(pv.history.total, lang))}</p>

              {cur.state === 'ready' && <>
                <label className="si-chk si-must"><input type="checkbox" checked={choice.old_bot_stopped} data-testid="import-checklist"
                  onChange={(e) => setChoice((c) => ({ ...c, old_bot_stopped: e.target.checked }))} />
                  <span><b>{s.check}</b><small>{s.check_hint}</small></span></label>
                <div className="si-act">
                  <button type="button" className="btn-primary text-sm si-btn" disabled={!choice.old_bot_stopped} onClick={run} data-testid="import-run">{s.run}</button>
                  <button type="button" className="btn-ghost text-sm si-btn" onClick={discard}>{s.discard}</button>
                </div>
              </>}
            </div>
          )}

          {cur.result && Object.keys(cur.result).some((k) => k.startsWith('customers') || k.startsWith('services')) && (
            <div className="si-kv" data-testid="import-result">
              <b className="w-full">{s.result}:</b>
              {Object.entries(cur.result).filter(([k]) => s['r_' + k]).map(([k, v]) => <span key={k}><b>{n(v)}</b> {s['r_' + k]}</span>)}
            </div>
          )}
          {cur.result?.kept?.length > 0 && <p className="si-desc">{s.kept.replace('{n}', n(cur.result.kept.length))}</p>}
          {cur.file_kept && cur.file_expires_at && ['uploaded', 'scanning', 'ready'].includes(cur.state) && (
            <p className="text-xs text-muted">{s.file_until.replace('{t}', jalali(cur.file_expires_at, true, lang))}</p>)}
          {cur.state === 'failed' && !cur.can_undo && <button type="button" className="btn-ghost text-sm si-btn" onClick={discard}>{s.discard}</button>}
          {cur.can_undo && <button type="button" className="btn-ghost text-sm si-btn si-danger" onClick={undo} data-testid="import-undo">{s.undo}</button>}
        </article>
      )}

      {showUpload && (
        <div className="si-up">
          {!cur && <p className="text-sm text-muted">{s.none}</p>}
          <label className="si-file">
            <input type="file" accept=".zip,.sql,.gz" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="import-file" />
            <span>{file ? <bdi dir="ltr">{file.name}</bdi> : (cur ? s.again : s.pick)}</span>
          </label>
          <button type="button" className="btn-primary text-sm si-btn" disabled={!file || busy} onClick={upload} data-testid="import-upload">{busy ? '…' : s.upload}</button>
        </div>
      )}
    </section>
  )
}

const CSS = `
.si { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.si-h { font-size: 14px; }
.si-desc, .si-line { font-size: 12.5px; line-height: 1.8; color: var(--c-text-muted); margin: 0; }
.si-line b { color: var(--c-text); }
.si-card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border: 1px solid var(--c-border); border-radius: 14px; min-width: 0; }
.si-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.si-pill { font-size: 12px; font-weight: 800; padding: 2px 10px; border-radius: 999px; color: var(--c-muted-fg);
  background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.si-pill[data-st="ready"], .si-pill[data-st="done"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.si-pill[data-st="failed"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.si-pill[data-st="running"], .si-pill[data-st="scanning"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.si-bar { position: relative; height: 18px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); overflow: hidden; }
.si-bar i { position: absolute; inset-block: 0; inset-inline-start: 0; background: var(--c-primary); }
.si-bar span { position: relative; display: block; text-align: center; font-size: 11px; font-weight: 700; line-height: 18px; }
.si-err { font-size: 12.5px; color: var(--c-danger-fg); margin: 0; overflow-wrap: anywhere; }
.si-pv { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.si-pv h4 { font-size: 13px; font-weight: 800; margin: 6px 0 0; }
.si-rules { display: flex; flex-direction: column; gap: 2px; font-size: 12.5px; line-height: 1.8; padding: 8px 10px; border-radius: 10px;
  background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.si-rules span:first-child { font-weight: 700; }
.si-kv { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12.5px; }
.si-buckets { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 4px 12px; font-size: 12.5px; }
.si-buckets li[data-k="link"] b, .si-buckets li[data-k="linked"] b { color: var(--c-success-fg); }
.si-buckets li[data-k="other_admin"] b, .si-buckets li[data-k="failed"] b { color: var(--c-danger-fg); }
.si-buckets li[data-k="missing"] b { color: var(--c-warning-fg); }
.si-miss { font-size: 12.5px; }
.si-miss summary { cursor: pointer; font-weight: 700; color: var(--c-warning-fg); min-height: 32px; }
.si-miss ul { margin: 6px 0 0; padding-inline-start: 18px; max-height: 240px; overflow: auto; line-height: 1.9; }
.si-plans { display: flex; flex-direction: column; gap: 6px; }
.si-plan { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 220px); gap: 8px; align-items: center; font-size: 12.5px; }
.si-plan small { color: var(--c-text-muted); }
.si-review { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border-radius: 10px; font-size: 12.5px;
  border: 1px solid color-mix(in srgb, var(--c-warning) 45%, transparent); background: color-mix(in srgb, var(--c-warning) 8%, transparent); }
.si-chk { display: flex; align-items: center; gap: 8px; font-size: 13px; min-height: 44px; }
.si-chk input { width: 18px; height: 18px; flex: none; }
.si-must { padding: 6px 10px; border-radius: 10px; border: 1px solid var(--c-border); }
.si-must span { display: flex; flex-direction: column; }
.si-must small { color: var(--c-text-muted); font-size: 11.5px; }
.si-f { display: flex; flex-direction: column; gap: 3px; font-size: 12px; font-weight: 700; max-width: 220px; }
.si-act, .si-up { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.si-btn { min-height: 44px; }
.si-danger { color: var(--c-danger-fg); }
.si-file { position: relative; display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px; border-radius: 12px; cursor: pointer;
  border: 1px dashed var(--c-border); font-size: 13px; max-width: 100%; overflow: hidden; }
.si-file input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
@media (max-width: 767px) { .si-plan { grid-template-columns: 1fr; } .si-f .input, .si-plan .input { font-size: 16px; min-height: 44px; } }
`
