// "Delete user" (soft delete) + "restore" through the shared ConfirmDialog —
// used by the Users list, a user's purchase-history page and the deleted-users
// archive. The reason textarea is required for a delete.
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { api } from './api'
import { digits, toman } from './format'
import { useI18n } from './i18n'

const T = {
  fa: {
    del_t: 'حذف کاربر', del_btn: 'بله، کاربر حذف شود', del_done: 'کاربر حذف و به بایگانی منتقل شد',
    target: 'شناسه کاربر:', impact: 'دامنه تأثیر عملیات:', tag: 'قابل بازگردانی از بایگانی',
    del_m: (u) => <>کاربر <strong>{u}</strong> حذف می‌شود: <em>همهٔ سرویس‌هایش روی پنل غیرفعال</em> (نه حذف) می‌شوند، از همهٔ نشست‌ها خارج و اتصال تلگرامش جدا می‌شود. سفارش‌ها و پرداخت‌ها در حسابداری بدون تغییر باقی می‌مانند.</>,
    r_services: 'سرویس‌هایی که غیرفعال می‌شوند', r_login: 'ورود به سایت و ربات', r_login_v: 'مسدود — نشست‌ها باطل می‌شوند',
    r_ids: 'نام کاربری / موبایل / ایمیل', r_ids_v: 'آزاد می‌شوند (ثبت‌نام دوباره ممکن است)',
    reason: 'دلیل حذف (الزامی)', reason_ph: 'مثلاً: درخواست خود کاربر، تخلف، حساب تکراری…',
    audit: 'این عملیات با نام کاربری شما در گزارش ممیزی ثبت می‌شود.',
    failed: (n) => `${n} سرویس روی پنل غیرفعال نشد؛ کاربر حذف نشد. پس از رفع مشکل پنل دوباره تلاش کنید.`,
    res_t: 'بازگردانی کاربر', res_btn: 'بله، بازگردانی شود', res_done: 'کاربر بازگردانی شد',
    res_m: (u) => <>حساب <strong>{u}</strong> با نام کاربری، موبایل و ایمیل اصلی دوباره فعال می‌شود. <em>سرویس‌ها غیرفعال می‌مانند</em> تا ادمین آن‌ها را جداگانه فعال کند.</>,
    res_tag: 'قابل برگشت', r_orders: 'سفارش‌ها', r_paid: 'مجموع پرداخت‌شده',
    tg_warn: 'شناسهٔ تلگرام این کاربر اکنون به حساب دیگری وصل است و دوباره متصل نشد.',
    conflict: 'بازگردانی ممکن نیست؛ این مقادیر اصلی اکنون متعلق به حساب دیگری است:',
    f_username: 'نام کاربری', f_phone: 'موبایل', f_email: 'ایمیل', owner: 'حساب',
  },
  en: {
    del_t: 'Delete user', del_btn: 'Yes, delete this user', del_done: 'User deleted and archived',
    target: 'User ID:', impact: 'Impact:', tag: 'Restorable from the archive',
    del_m: (u) => <>User <strong>{u}</strong> will be deleted: <em>every service is disabled on its panel</em> (not deleted), all sessions are revoked and the Telegram link is removed. Orders and payments stay in accounting unchanged.</>,
    r_services: 'Services to disable', r_login: 'Site & bot login', r_login_v: 'blocked — sessions revoked',
    r_ids: 'Username / phone / email', r_ids_v: 'freed (can register again)',
    reason: 'Reason for deletion (required)', reason_ph: 'e.g. requested by the user, abuse, duplicate account…',
    audit: 'This action is recorded under your username in the audit log.',
    failed: (n) => `${n} service(s) could not be disabled on the panel; the user was NOT deleted. Retry once the panel is reachable.`,
    res_t: 'Restore user', res_btn: 'Yes, restore', res_done: 'User restored',
    res_m: (u) => <>Account <strong>{u}</strong> is reactivated with its original username, phone and email. <em>Services stay disabled</em> until an admin re-enables them.</>,
    res_tag: 'Reversible', r_orders: 'Orders', r_paid: 'Total paid',
    tg_warn: "This user's Telegram id now belongs to another account and was not relinked.",
    conflict: 'Cannot restore — these original values now belong to another account:',
    f_username: 'Username', f_phone: 'Phone', f_email: 'Email', owner: 'account',
  },
}

/** "Username: ali (account #12 ali) · Phone: …" */
export function conflictText(conflicts, s) {
  const parts = Object.entries(conflicts).map(([k, v]) => `${s[`f_${k}`] || k}: ${v.value} (${s.owner} #${v.user_id} ${v.username})`)
  return `${s.conflict} ${parts.join(' · ')}`
}

export const USER_ACTION_STRINGS = T

export function useUserActions() {
  const confirm = useConfirm()
  const toast = useToast()
  const { lang } = useI18n()
  const s = T[lang] || T.fa

  return {
    /** row: { id, username, service_count? } → true once deleted, false when cancelled */
    remove: async (row) => {
      const ok = await confirm({
        tone: 'danger', icon: 'trash', badge: 'users.delete',
        title: s.del_t, targetLabel: s.target, targetId: `#${row.id}`,
        message: s.del_m(row.username), footnote: s.audit, confirmLabel: s.del_btn,
        details: {
          title: s.impact, tag: s.tag,
          rows: [
            ...(row.service_count != null ? [[s.r_services, digits(row.service_count, lang)]] : []),
            [s.r_login, s.r_login_v],
            [s.r_ids, s.r_ids_v],
          ],
        },
        reason: { label: s.reason, placeholder: s.reason_ph, required: true },
        action: async (reason) => {
          try {
            await api.post(`/admin/users/${row.id}/delete/`, { reason })
          } catch (e) {
            const failed = e?.response?.data?.failed_services
            if (failed?.length) {
              const names = failed.map((f) => f.panel_username).join('، ')
              throw new Error(`${s.failed(digits(failed.length, lang))} (${names})`)
            }
            throw e
          }
        },
      })
      if (ok) toast.success(s.del_done)
      return ok
    },

    /** archive row → the restore response, or null when cancelled */
    restore: async (a) => {
      let res = null
      const ok = await confirm({
        tone: 'success', icon: 'refresh', badge: 'users.delete',
        title: s.res_t, targetLabel: s.target, targetId: a.user ? `#${a.user}` : undefined,
        message: s.res_m(a.original_username), footnote: s.audit, confirmLabel: s.res_btn,
        details: {
          title: s.impact, tag: s.res_tag,
          rows: [[s.r_orders, digits(a.orders_count, lang)], [s.r_paid, toman(a.total_paid, lang)]],
        },
        action: async () => {
          try {
            res = (await api.post(`/admin/deleted-users/${a.id}/restore/`)).data
          } catch (e) {
            const c = e?.response?.status === 409 && e.response.data?.conflicts
            if (c) throw new Error(conflictText(c, s))
            throw e
          }
        },
      })
      if (!ok) return null
      toast.success(s.res_done)
      if (res?.warnings?.includes('telegram_id_in_use')) toast.error(s.tg_warn)
      return res
    },
  }
}
