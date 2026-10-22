import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Spinner, Toggle } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'

// Ticket topics, saved replies (per topic or general) and ticket settings — tickets.manage_topics.
const T = {
  fa: {
    title: 'موضوعات و پاسخ‌های آماده', sub: 'موضوعات تیکت، پاسخ‌های آماده برای هر موضوع و تنظیمات تیکت', back: 'صندوق تیکت‌ها',
    topics: 'موضوعات', new_topic: 'موضوع جدید', name_fa: 'نام فارسی', name_en: 'نام انگلیسی', desc_fa: 'توضیح فارسی', desc_en: 'توضیح انگلیسی',
    needs: 'فقط برای مشتریان (کسانی که حداقل یک‌بار خرید کرده‌اند)', pre: 'قبل از خرید — برای همه', active: 'فعال', order: 'ترتیب',
    tickets: 'تیکت', save: 'ذخیره', cancel: 'انصراف', edit: 'ویرایش', del: 'حذف', del_q: 'حذف شود؟', in_use: 'موضوع دارای تیکت را غیرفعال کنید',
    canned: 'پاسخ‌های آماده', new_canned: 'پاسخ آماده جدید', c_title: 'عنوان', c_body: 'متن پاسخ', c_topic: 'موضوع', general: 'همهٔ موضوعات',
    settings: 'تنظیمات تیکت', max_open: 'حداکثر تیکت باز برای هر کاربر', auto_close: 'بستن خودکار پس از چند روز بی‌پاسخی کاربر',
    reopen: 'مهلت بازگشایی توسط کاربر (روز، 0 = هرگز)', show_name: 'نمایش نام نمایشی پشتیبان به کاربر (به‌جای «پشتیبانی»)',
    none: 'موردی نیست.', inactive: 'غیرفعال',
  },
  en: {
    title: 'Topics & saved replies', sub: 'Ticket topics, saved replies per topic and ticket settings', back: 'Ticket inbox',
    topics: 'Topics', new_topic: 'New topic', name_fa: 'Persian name', name_en: 'English name', desc_fa: 'Persian description', desc_en: 'English description',
    needs: 'Customers only (anyone who ever bought)', pre: 'Pre-purchase — open to everyone', active: 'Active', order: 'Order',
    tickets: 'tickets', save: 'Save', cancel: 'Cancel', edit: 'Edit', del: 'Delete', del_q: 'Delete?', in_use: 'A topic with tickets can only be deactivated',
    canned: 'Saved replies', new_canned: 'New saved reply', c_title: 'Title', c_body: 'Reply text', c_topic: 'Topic', general: 'All topics',
    settings: 'Ticket settings', max_open: 'Max open tickets per user', auto_close: 'Auto-close after N days without a user reply',
    reopen: 'User can reopen within (days, 0 = never)', show_name: 'Show the staff display name to users (instead of “Support”)',
    none: 'Nothing yet.', inactive: 'inactive',
  },
}
const blankTopic = { name_fa: '', name_en: '', description_fa: '', description_en: '', requires_active_service: true, is_active: true, sort_order: 100 }
const blankCanned = { title: '', body: '', topic: '', is_active: true, sort_order: 100 }

export default function TicketTopics() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const [topics, setTopics] = useState(null)
  const [canned, setCanned] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [topicForm, setTopicForm] = useState(null)
  const [cannedForm, setCannedForm] = useState(null)

  const load = () => {
    api.get('/admin/tickets/topics/').then((r) => setTopics(r.data)).catch(() => setTopics([]))
    api.get('/admin/tickets/canned/?all=1').then((r) => setCanned(r.data)).catch(() => setCanned([]))
    api.get('/admin/tickets/settings/').then((r) => setCfg(r.data.settings)).catch(() => {})
  }
  useEffect(() => { load() }, [])
  const tname = (id) => { const tp = (topics || []).find((x) => x.id === id); return tp ? (lang === 'en' ? tp.name_en : tp.name_fa) : s.general }

  const saveTopic = async (e) => {
    e.preventDefault()
    const f = topicForm
    if (f.id) await api.patch(`/admin/tickets/topics/${f.id}/`, f); else await api.post('/admin/tickets/topics/', f)
    setTopicForm(null); load()
  }
  const saveCanned = async (e) => {
    e.preventDefault()
    const f = { ...cannedForm, topic: cannedForm.topic || null }
    if (f.id) await api.patch(`/admin/tickets/canned/${f.id}/`, f); else await api.post('/admin/tickets/canned/', f)
    setCannedForm(null); load()
  }
  const del = (url, name) => confirm({ tone: 'danger', title: s.del_q, message: name, action: async () => { await api.delete(url); load() } })
  const saveCfg = async (patch) => {
    const r = await api.patch('/admin/tickets/settings/', patch)
    setCfg(r.data.settings)
  }

  if (!topics || !canned) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="tt space-y-5">
      <style>{CSS}</style>
      <div className="tt-head">
        <div className="min-w-0 flex-1"><h1 className="text-lg font-bold">{s.title}</h1><p className="text-sm text-muted mt-1">{s.sub}</p></div>
        <Link to="/tickets" className="btn-ghost text-sm">← {s.back}</Link>
      </div>

      <section className="space-y-3">
        <div className="tt-sec-head"><h2 className="font-bold">{s.topics}</h2>
          <button type="button" className="btn-primary text-sm" onClick={() => setTopicForm({ ...blankTopic })}>+ {s.new_topic}</button></div>
        {topicForm && (
          <form className="card tt-form" onSubmit={saveTopic}>
            <div className="tt-grid">
              <label><span className="label">{s.name_fa}</span><input className="input" required value={topicForm.name_fa} onChange={(e) => setTopicForm({ ...topicForm, name_fa: e.target.value })} /></label>
              <label><span className="label">{s.name_en}</span><input className="input" dir="ltr" required value={topicForm.name_en} onChange={(e) => setTopicForm({ ...topicForm, name_en: e.target.value })} /></label>
              <label><span className="label">{s.desc_fa}</span><input className="input" value={topicForm.description_fa} onChange={(e) => setTopicForm({ ...topicForm, description_fa: e.target.value })} /></label>
              <label><span className="label">{s.desc_en}</span><input className="input" dir="ltr" value={topicForm.description_en} onChange={(e) => setTopicForm({ ...topicForm, description_en: e.target.value })} /></label>
              <label><span className="label">{s.order}</span><input className="input" type="number" dir="ltr" value={topicForm.sort_order} onChange={(e) => setTopicForm({ ...topicForm, sort_order: e.target.value })} /></label>
            </div>
            <label className="tt-toggle"><Toggle checked={!topicForm.requires_active_service} onChange={(v) => setTopicForm({ ...topicForm, requires_active_service: !v })} label={s.pre} /> {s.pre}</label>
            <label className="tt-toggle"><Toggle checked={topicForm.is_active} onChange={(v) => setTopicForm({ ...topicForm, is_active: v })} label={s.active} /> {s.active}</label>
            <div className="tt-actions"><button type="button" className="btn-ghost text-sm" onClick={() => setTopicForm(null)}>{s.cancel}</button><button className="btn-primary text-sm">{s.save}</button></div>
          </form>
        )}
        <div className="card p-0 tt-list">
          {topics.map((tp) => (
            <div key={tp.id} className={'tt-row' + (tp.is_active ? '' : ' off')}>
              <div className="min-w-0 flex-1">
                <b>{lang === 'en' ? tp.name_en : tp.name_fa}</b> <span className="text-muted text-xs">· {lang === 'en' ? tp.name_fa : tp.name_en}</span>
                <span className="tt-meta">
                  <span className={'tt-chip' + (tp.requires_active_service ? '' : ' pre')}>{tp.requires_active_service ? s.needs : s.pre}</span>
                  {!tp.is_active && <span className="tt-chip off">{s.inactive}</span>}
                  <span className="text-muted">{tp.ticket_count} {s.tickets}</span>
                </span>
              </div>
              <div className="tt-acts">
                <button type="button" className="tt-btn" onClick={() => setTopicForm({ ...tp })}>{s.edit}</button>
                <button type="button" className="tt-btn del" disabled={tp.ticket_count > 0} title={tp.ticket_count ? s.in_use : ''}
                  onClick={() => del(`/admin/tickets/topics/${tp.id}/`, tp.name_fa)}>{s.del}</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="tt-sec-head"><h2 className="font-bold">{s.canned}</h2>
          <button type="button" className="btn-primary text-sm" onClick={() => setCannedForm({ ...blankCanned })}>+ {s.new_canned}</button></div>
        {cannedForm && (
          <form className="card tt-form" onSubmit={saveCanned}>
            <div className="tt-grid">
              <label><span className="label">{s.c_title}</span><input className="input" required value={cannedForm.title} onChange={(e) => setCannedForm({ ...cannedForm, title: e.target.value })} /></label>
              <label><span className="label">{s.c_topic}</span>
                <select className="input" value={cannedForm.topic || ''} onChange={(e) => setCannedForm({ ...cannedForm, topic: e.target.value })}>
                  <option value="">{s.general}</option>
                  {topics.map((tp) => <option key={tp.id} value={tp.id}>{lang === 'en' ? tp.name_en : tp.name_fa}</option>)}
                </select></label>
            </div>
            <label className="block"><span className="label">{s.c_body}</span>
              <textarea className="input" rows={4} required value={cannedForm.body} onChange={(e) => setCannedForm({ ...cannedForm, body: e.target.value })} /></label>
            <label className="tt-toggle"><Toggle checked={cannedForm.is_active} onChange={(v) => setCannedForm({ ...cannedForm, is_active: v })} label={s.active} /> {s.active}</label>
            <div className="tt-actions"><button type="button" className="btn-ghost text-sm" onClick={() => setCannedForm(null)}>{s.cancel}</button><button className="btn-primary text-sm">{s.save}</button></div>
          </form>
        )}
        <div className="card p-0 tt-list">
          {canned.length === 0 && <div className="tt-row text-muted">{s.none}</div>}
          {canned.map((c) => (
            <div key={c.id} className={'tt-row' + (c.is_active ? '' : ' off')}>
              <div className="min-w-0 flex-1">
                <b>{c.title}</b> <span className="tt-chip">{tname(c.topic)}</span>
                <p className="tt-body">{c.body}</p>
              </div>
              <div className="tt-acts">
                <button type="button" className="tt-btn" onClick={() => setCannedForm({ ...c, topic: c.topic || '' })}>{s.edit}</button>
                <button type="button" className="tt-btn del" onClick={() => del(`/admin/tickets/canned/${c.id}/`, c.title)}>{s.del}</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {cfg && (
        <section className="space-y-3">
          <h2 className="font-bold">{s.settings}</h2>
          <div className="card tt-form">
            <div className="tt-grid">
              {[['tickets_max_open_per_user', s.max_open], ['tickets_auto_close_days', s.auto_close], ['tickets_reopen_days', s.reopen]].map(([k, l]) => (
                <label key={k}><span className="label">{l}</span>
                  <input className="input" type="number" dir="ltr" defaultValue={cfg[k]} onBlur={(e) => Number(e.target.value) !== cfg[k] && saveCfg({ [k]: e.target.value })} /></label>
              ))}
            </div>
            <label className="tt-toggle"><Toggle checked={!!cfg.tickets_show_staff_name} onChange={(v) => saveCfg({ tickets_show_staff_name: v })} label={s.show_name} /> {s.show_name}</label>
          </div>
        </section>
      )}
    </div>
  )
}

const CSS = `
.tt-head, .tt-sec-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: space-between; }
.tt-form { display: flex; flex-direction: column; gap: 12px; }
.tt-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
.tt-toggle { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.tt-actions { display: flex; justify-content: flex-end; gap: 8px; }
.tt-list { overflow: hidden; }
.tt-row { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border-bottom: 1px solid var(--c-border); flex-wrap: wrap; }
.tt-row:last-child { border-bottom: 0; }
.tt-row.off { opacity: .6; }
.tt-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 4px; font-size: 12px; }
.tt-chip { display: inline-flex; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.tt-chip.pre { color: var(--c-success-fg, var(--c-success)); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.tt-chip.off { color: var(--c-warning-fg, var(--c-warning)); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.tt-body { margin: 4px 0 0; font-size: 12.5px; color: var(--c-text-muted); white-space: pre-wrap; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.tt-acts { display: flex; gap: 6px; flex-shrink: 0; }
.tt-btn { min-height: 34px; padding: 0 12px; border-radius: 9px; font-size: 12.5px; font-weight: 600; border: 1px solid var(--c-border); background: none; color: var(--c-text); cursor: pointer; }
.tt-btn.del { color: var(--c-danger-fg, var(--c-danger)); border-color: color-mix(in srgb, var(--c-danger) 40%, transparent); }
.tt-btn:disabled { opacity: .4; cursor: not-allowed; }
@media (max-width: 767px) { .tt-acts { width: 100%; } .tt-acts .tt-btn { flex: 1; } }
`
