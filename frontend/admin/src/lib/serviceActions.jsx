// Confirmed service actions shared by the Services list and the service
// edit/details page — every one goes through the base ConfirmDialog.
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { api } from './api'
import { digits, gb } from './format'
import { useI18n } from './i18n'

const T = {
  fa: {
    audit: 'این عملیات با نام کاربری شما در گزارش ممیزی ثبت می‌شود.',
    target: 'شناسه سرویس:', impact: 'دامنه تأثیر عملیات:', irreversible: 'غیرقابل بازگشت', reversible: 'قابل برگشت',
    panel: 'پنل', used: 'حجم مصرف‌شده', devices: 'دستگاه‌های متصل با لینک فعلی', all_disconnect: 'همه قطع می‌شوند',
    reset_t: 'ریست حجم مصرفی', reset_btn: 'بله، حجم را ریست کن', reset_done: 'حجم مصرفی ریست شد',
    reset_m: (n, u) => <>حجم مصرف‌شدهٔ سرویس <strong>{n}</strong> متعلق به کاربر <strong>{u}</strong> صفر می‌شود و کاربر دوباره کل سهمیه را در اختیار خواهد داشت.</>,
    revoke_t: 'تغییر لینک اشتراک', revoke_btn: 'بله، لینک جدید بساز', revoke_done: 'لینک ساب تغییر کرد',
    revoke_m: (n, u) => <>لینک اشتراک سرویس <strong>{n}</strong> متعلق به کاربر <strong>{u}</strong> باطل می‌شود و <em>همهٔ دستگاه‌های متصل</em> تا تنظیم لینک جدید قطع خواهند شد.</>,
    delete_t: 'حذف دائمی سرویس و کلاینت', delete_btn: 'بله، حذف دائمی سرویس', delete_done: 'سرویس حذف شد',
    delete_m: (n, u) => <>آیا از حذف سرویس <strong>{n}</strong> متعلق به کاربر <strong>{u}</strong> اطمینان دارید؟ با تأیید این مرحله، اکانت روی پنل حذف و <em>دسترسی کاربر فوراً قطع</em> می‌شود و غیرقابل بازگشت خواهد بود.</>,
    disable_t: 'غیرفعال کردن سرویس', disable_btn: 'بله، غیرفعال کن',
    disable_m: (n, u) => <>سرویس <strong>{n}</strong> متعلق به کاربر <strong>{u}</strong> غیرفعال می‌شود و کاربر دیگر نمی‌تواند متصل شود. بعداً می‌توانید دوباره فعالش کنید.</>,
    status_done: 'وضعیت سرویس بروزرسانی شد', unlimited: 'نامحدود',
  },
  en: {
    audit: 'This action is recorded under your username in the audit log.',
    target: 'Service ID:', impact: 'Impact:', irreversible: 'Irreversible', reversible: 'Reversible',
    panel: 'Panel', used: 'Data used', devices: 'Devices on the current link', all_disconnect: 'all disconnected',
    reset_t: 'Reset data usage', reset_btn: 'Yes, reset usage', reset_done: 'Usage was reset',
    reset_m: (n, u) => <>The used data of <strong>{n}</strong> (user <strong>{u}</strong>) goes back to zero and the full quota becomes available again.</>,
    revoke_t: 'Revoke subscription link', revoke_btn: 'Yes, issue a new link', revoke_done: 'Subscription link revoked',
    revoke_m: (n, u) => <>The subscription link of <strong>{n}</strong> (user <strong>{u}</strong>) is invalidated and <em>every connected device</em> disconnects until it is set up with the new link.</>,
    delete_t: 'Permanently delete service', delete_btn: 'Yes, delete permanently', delete_done: 'Service deleted',
    delete_m: (n, u) => <>Delete <strong>{n}</strong> owned by <strong>{u}</strong>? The panel account is removed and <em>the user loses access immediately</em>. This cannot be undone.</>,
    disable_t: 'Disable service', disable_btn: 'Yes, disable',
    disable_m: (n, u) => <><strong>{n}</strong> (user <strong>{u}</strong>) will be disabled and can no longer connect. You can re-enable it later.</>,
    status_done: 'Service status updated', unlimited: 'unlimited',
  },
}

export function useServiceActions() {
  const confirm = useConfirm()
  const toast = useToast()
  const { lang } = useI18n()
  const s = T[lang] || T.fa

  const base = (row) => ({
    targetLabel: s.target, targetId: `SRV-${row.id}`, footnote: s.audit,
  })
  const usedRow = (row) => [s.used, <span dir="ltr">{digits(gb(row.data_used || 0), lang)} GB{row.data_limit ? ` / ${digits(gb(row.data_limit), lang)} GB` : ` / ${s.unlimited}`}</span>]
  const panelRow = (row) => [s.panel, row.panel_name || '—']
  const who = (row) => row.user || '—'

  /** each resolves to the updated service (or `true` for delete), or null when cancelled */
  const run = async (opts, fn, done) => {
    let result = null
    const ok = await confirm({ ...opts, action: async () => { result = await fn() } })
    if (!ok) return null
    toast.success(done)
    return result ?? true
  }

  return {
    reset: (row) => run({
      ...base(row), tone: 'success', icon: 'refresh', badge: 'services.manage',
      title: s.reset_t, message: s.reset_m(row.panel_username, who(row)), confirmLabel: s.reset_btn,
      details: { title: s.impact, tag: s.reversible, rows: [panelRow(row), usedRow(row)] },
    }, async () => (await api.post(`/admin/services/${row.id}/reset/`)).data, s.reset_done),

    revoke: (row) => run({
      ...base(row), tone: 'warning', icon: 'link', badge: 'services.manage',
      title: s.revoke_t, message: s.revoke_m(row.panel_username, who(row)), confirmLabel: s.revoke_btn,
      details: { title: s.impact, tag: s.irreversible, rows: [panelRow(row), [s.devices, s.all_disconnect]] },
    }, async () => (await api.post(`/admin/services/${row.id}/revoke/`)).data, s.revoke_done),

    remove: (row) => run({
      ...base(row), tone: 'danger', icon: 'trash', badge: 'services.delete',
      title: s.delete_t, message: s.delete_m(row.panel_username, who(row)), confirmLabel: s.delete_btn,
      details: { title: s.impact, tag: s.irreversible, rows: [panelRow(row), usedRow(row)] },
    }, async () => { await api.delete(`/admin/services/${row.id}/`); return true }, s.delete_done),

    /** status change; disabling asks first, other statuses apply directly */
    setStatus: async (row, status) => {
      const call = async () => (await api.post(`/admin/services/${row.id}/status/`, { status })).data
      if (status !== 'disabled') {
        const data = await call()
        toast.success(s.status_done)
        return data
      }
      return run({
        ...base(row), tone: 'danger', icon: 'ban', badge: 'services.manage',
        title: s.disable_t, message: s.disable_m(row.panel_username, who(row)), confirmLabel: s.disable_btn,
        details: { title: s.impact, tag: s.reversible, rows: [panelRow(row), usedRow(row)] },
      }, call, s.status_done)
    },
  }
}
