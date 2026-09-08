import { useEffect, useMemo, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { digits } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

function Ico({ d, w = 15 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const ICONS = {
  bot: <><rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4M8 16h.01M16 16h.01" /></>,
  cart: <><circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" /><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6" /></>,
  backup: <><path d="M21 12a9 9 0 11-3-6.7L21 8" /><path d="M21 3v5h-5" /></>,
  link: <><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" /></>,
  edit: <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />,
  trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>,
  eye: <><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" /><path d="M1 1l22 22" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
}

// password/secret input with a show/hide eye toggle
function SecretInput({ value, onChange, placeholder, autoComplete = 'new-password' }) {
  const { t } = useI18n()
  const [show, setShow] = useState(false)
  return (
    <div className="int-secret">
      <input className="input" dir="ltr" type={show ? 'text' : 'password'} autoComplete={autoComplete}
        placeholder={placeholder} value={value} onChange={onChange} />
      <button type="button" className="int-secret-eye" onClick={() => setShow((v) => !v)}
        aria-label={t(show ? 'hide_password' : 'show_password')}>
        <Ico d={show ? ICONS.eyeOff : ICONS.eye} w={15} />
      </button>
    </div>
  )
}

const INT_CSS = `
.int-secret { position: relative; }
.int-secret .input { width: 100%; padding-inline-end: 40px; }
.int-secret-eye { position: absolute; inset-inline-end: 10px; top: 50%; transform: translateY(-50%); color: var(--c-text-muted); }
.int-secret-eye:hover { color: var(--c-text); }
.int-head { display: flex; align-items: flex-start; gap: 12px; }
.int-head-ico { width: 40px; height: 40px; border-radius: 12px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.int-card-head { display: flex; align-items: center; gap: 11px; }
.int-card-ico { width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.int-bot-grid { display: grid; grid-template-columns: 1fr; gap: 16px; align-items: start; }
@media (min-width: 1024px) { .int-bot-grid { grid-template-columns: 1fr 1fr; } }
.int-bot-card { height: 100%; }
.int-icon-btn { display: inline-flex; padding: 6px; border-radius: 8px; color: var(--c-text-muted); }
.int-icon-btn:hover { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.int-icon-btn--del:hover { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }

/* --- Pasargad panel list --- */
.pl-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (min-width: 900px) { .pl-stats { grid-template-columns: repeat(4, 1fr); } }
.pl-stat { padding: 14px 16px; }
.pl-stat-label { font-size: 11.5px; font-weight: 600; color: var(--c-text-muted); }
.pl-stat-val { font-size: 22px; font-weight: 800; margin-top: 4px; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.pl-stat-unit { font-size: 11px; font-weight: 500; color: var(--c-text-muted); font-family: inherit; }

.pl-list-h { display: flex; align-items: center; gap: 10px; }
.pl-count-badge { font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 999px;
  background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); color: var(--c-text-muted); }

.pl-row { display: flex; flex-direction: column; gap: 12px; }
.pl-row--off { opacity: .62; }
.pl-row-main { display: flex; gap: 14px; align-items: flex-start; }
.pl-row-ico { width: 46px; height: 46px; border-radius: 13px; flex-shrink: 0; display: grid; place-items: center; }
.pl-row-ico.on { background: color-mix(in srgb, var(--c-primary) 13%, transparent); color: var(--c-primary); }
.pl-row-ico.off { background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); color: var(--c-text-muted); }
.pl-row-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pl-row-title b { font-size: 14px; }
.pl-tag { display: inline-flex; align-items: center; gap: 3px; font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
.pl-tag.ok { background: color-mix(in srgb, var(--c-success) 15%, transparent); color: var(--c-success); }
.pl-tag.ssl { background: color-mix(in srgb, var(--c-primary) 13%, transparent); color: var(--c-primary); }
.pl-tag.muted { background: color-mix(in srgb, var(--c-text-muted) 15%, transparent); color: var(--c-text-muted); }
.pl-row-url { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; color: var(--c-text-muted); margin-top: 4px; word-break: break-all; }
.pl-row-meta { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 6px; font-size: 12px; color: var(--c-text-muted); }
.pl-row-groups { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.pl-gchip { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 5px;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.pl-row-acts { display: flex; flex-wrap: wrap; gap: 8px; border-top: 1px solid var(--c-border); padding-top: 12px; }
.pl-rbtn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border-radius: 9px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-muted); transition: .15s; }
.pl-rbtn:hover:not(:disabled) { color: var(--c-text); border-color: var(--c-primary); }
.pl-rbtn:disabled { opacity: .5; }
.pl-rbtn--primary { color: var(--c-primary); border-color: color-mix(in srgb, var(--c-primary) 32%, transparent); background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.pl-rbtn--primary:hover { background: color-mix(in srgb, var(--c-primary) 16%, transparent); }
.pl-rbtn--del { color: var(--c-danger); border-color: color-mix(in srgb, var(--c-danger) 28%, transparent); }
.pl-rbtn--del:hover { background: color-mix(in srgb, var(--c-danger) 12%, transparent); border-color: var(--c-danger); }
.pl-row-acts .pl-rbtn--del { margin-inline-start: auto; }
`

const T = {
  fa: {
    panel_intro: 'پنل‌های پاسارگارد/PasarGuard خود را اینجا مدیریت کنید. هر پلن به یک پنل متصل می‌شود. رمز عبور رمزنگاری‌شده ذخیره می‌شود و دیگر نمایش داده نمی‌شود.',
    add_panel: 'افزودن پنل', panel_name: 'نام پنل', new_panel: 'پنل جدید',
    del_panel: 'حذف پنل', confirm_del: 'این پنل حذف شود؟',
    in_use: 'پلن', in_use2: 'سرویس',
    base_url: 'آدرس پایه پنل (Base URL)', admin_user: 'نام کاربری ادمین پنل',
    admin_pass: 'رمز عبور ادمین پنل', sub_url: 'آدرس پایهٔ اشتراک (اختیاری)',
    verify_ssl: 'بررسی گواهی SSL پنل', panel_active: 'این پنل فعال است',
    unchanged: '•••••••• (بدون تغییر)',
    pass_stored: 'رمزی ذخیره شده است؛ برای تغییر، رمز جدید را وارد کنید.',
    pass_none: 'هنوز رمزی ذخیره نشده است.',
    saved: 'ذخیره شد.', save: 'ذخیره', test: 'تست اتصال',
    pl_h: 'پنل‌های متصل پاسارگاد (PasarGuard)',
    pl_st_total: 'کل پنل‌های متصل', pl_st_total_u: 'پنل',
    pl_st_plans: 'پلن‌های زیر پوشش', pl_st_plans_u: 'پلن',
    pl_st_svc: 'سرویس‌های فعال', pl_st_svc_u: 'سرویس',
    pl_st_active: 'پنل‌های فعال', pl_st_active_u: 'فعال',
    pl_list_h: 'لیست پنل‌ها و نودهای فعال', pl_count: '{n} مورد',
    pl_ssl_on: 'SSL معتبر', pl_ssl_off: 'بدون بررسی SSL',
    pl_connected: 'فعال', pl_disabled: 'غیرفعال',
    pl_usage: '{p} پلن فعال / {s} سرویس',
    pl_node_groups: 'گروه‌های نود:', pl_no_groups: 'گروه پیش‌فرضی ندارد',
    pl_edit: 'ویرایش و تنظیمات', pl_none: 'هنوز پنلی اضافه نشده است.',
    groups: 'گروه‌های پیش‌فرض این پنل', fetch_groups: 'دریافت گروه‌ها از پنل',
    fetching: 'در حال دریافت…',
    groups_hint: 'وقتی یک پلن روی این پنل گروهی تعیین نکند، این گروه‌ها استفاده می‌شوند.',
    groups_none_fetched: 'برای انتخاب از روی نام گروه‌ها، دکمهٔ «دریافت گروه‌ها از پنل» را بزنید. شناسه‌های ذخیره‌شدهٔ فعلی:',
    groups_empty: 'هیچ شناسه‌ای انتخاب نشده است.',
    group_word: 'گروه',
    bots_intro: 'هر ربات توکن جداگانه دارد. توکن‌ها رمزنگاری‌شده ذخیره می‌شوند و نمایش داده نمی‌شوند.',
    sales_bot: 'ربات فروش', backup_bot: 'ربات بک‌آپ', active: 'فعال',
    bot_token: 'توکن ربات (BotFather)', proxy: 'پروکسی (اختیاری)',
    chat_id: 'شناسهٔ چت بک‌آپ (chat_id)',
    token_stored: 'توکنی ذخیره شده است؛ برای تغییر، توکن جدید را وارد کنید.',
    token_none: 'هنوز توکنی ذخیره نشده است.',
    chat_hint: 'فایل‌های پشتیبان به این چت ارسال می‌شوند. برای گرفتن شناسه، در آن چت به ربات بک‌آپ /id بفرستید.',
    bots_saved: 'ذخیره شد. برای اعمال توکن جدید، کانتینر ربات ظرف یک دقیقه به‌روز می‌شود (در صورت نیاز ری‌استارت کنید).',
    email_title: 'ارسال ایمیل', email_host: 'میزبان', email_from: 'فرستنده',
    email_relay_on: 'رله فعال است', email_relay_off: 'رله تنظیم نشده — ایمیل خارجی ارسال نمی‌شود',
    email_ready: 'آمادهٔ ارسال بیرونی', email_not_ready: 'ارسال بیرونی فعال نیست',
    email_relay_hint: 'اطلاعات رله در فایل .env تنظیم می‌شود (SMTP_RELAY_*) — راهنما: docs/email-relay.md',
    email_test_to: 'ارسال ایمیل آزمایشی به', email_send_test: 'ارسال آزمایشی',
    email_verif_on: 'تأیید ایمیل الزامی است', email_verif_off: 'تأیید ایمیل اختیاری است',
    inactive: 'غیرفعال',
    ch_title_h: 'کانال‌های اجباری (عضویت پیش از استفاده از ربات)',
    ch_intro: 'کاربر باید پیش از استفاده از ربات فروش، در همهٔ کانال‌های فعال زیر عضو باشد.',
    ch_add: 'افزودن کانال', ch_cancel: 'انصراف', ch_confirm_del: 'این کانال حذف شود؟',
    ch_none: 'هنوز کانالی اضافه نشده است.',
    ch_id: 'شناسهٔ کانال (@username یا -100...)', ch_title: 'عنوان (اختیاری)',
    ch_invite: 'لینک دعوت (برای کانال خصوصی)',
    ch_invite_hint: 'برای کانال خصوصی که username ندارد، لینک دعوت را وارد کنید تا دکمهٔ «عضویت» به کاربر نمایش داده شود.',
    ch_members: 'اعضا', ch_test: 'تست دسترسی',
    force_join: 'عضویت اجباری در کانال‌ها (force_channel_join)',
    force_phone: 'اشتراک‌گذاری اجباری شمارهٔ تلفن (force_share_phone)',
    ch_admin_hint: 'برای بررسی عضویت کاربران، ربات فروش باید «ادمین» هر کانال باشد. پس از افزودن کانال، ربات را در آن ادمین کنید و سپس «تست دسترسی» را بزنید.',
  },
  en: {
    panel_intro: 'Manage your Pasargad / PasarGuard panels here. Every plan is bound to one panel. Passwords are stored encrypted and never shown again.',
    add_panel: 'Add panel', panel_name: 'Panel name', new_panel: 'New panel',
    del_panel: 'Delete panel', confirm_del: 'Delete this panel?',
    in_use: 'plan', in_use2: 'service',
    base_url: 'Panel Base URL', admin_user: 'Panel admin username',
    admin_pass: 'Panel admin password', sub_url: 'Subscription base URL (optional)',
    verify_ssl: 'Verify panel SSL certificate', panel_active: 'Panel is active',
    unchanged: '•••••••• (unchanged)',
    pass_stored: 'A password is stored; type a new one only to change it.',
    pass_none: 'No password stored yet.',
    saved: 'Saved.', save: 'Save', test: 'Test connection',
    pl_h: 'Connected Pasargad (PasarGuard) panels',
    pl_st_total: 'Connected panels', pl_st_total_u: 'panels',
    pl_st_plans: 'Plans covered', pl_st_plans_u: 'plans',
    pl_st_svc: 'Active services', pl_st_svc_u: 'services',
    pl_st_active: 'Active panels', pl_st_active_u: 'active',
    pl_list_h: 'Panels & active nodes', pl_count: '{n} items',
    pl_ssl_on: 'SSL verified', pl_ssl_off: 'SSL check off',
    pl_connected: 'Active', pl_disabled: 'Disabled',
    pl_usage: '{p} plans / {s} services',
    pl_node_groups: 'Node groups:', pl_no_groups: 'no default groups',
    pl_edit: 'Edit & settings', pl_none: 'No panels added yet.',
    groups: "This panel's default groups", fetch_groups: 'Fetch groups from panel',
    fetching: 'Fetching…',
    groups_hint: 'Used whenever a plan on this panel does not set its own groups.',
    groups_none_fetched: 'Click “Fetch groups from panel” to pick them by name. Currently saved ids:',
    groups_empty: 'No ids selected.',
    group_word: 'group',
    bots_intro: 'Each bot has its own token. Tokens are stored encrypted and never shown.',
    sales_bot: 'Sales bot', backup_bot: 'Backup bot', active: 'Active',
    bot_token: 'Bot token (BotFather)', proxy: 'Proxy (optional)',
    chat_id: 'Backup chat_id',
    token_stored: 'A token is stored; type a new one only to change it.',
    token_none: 'No token stored yet.',
    chat_hint: 'Backups are sent to this chat. Send /id to the backup bot there to get the id.',
    bots_saved: 'Saved. The bot container picks up a new token within a minute (restart it if needed).',
    email_title: 'Email delivery', email_host: 'Host', email_from: 'From',
    email_relay_on: 'Relay configured', email_relay_off: 'No relay — external email will not be delivered',
    email_ready: 'Ready for external delivery', email_not_ready: 'External delivery not active',
    email_relay_hint: 'Relay credentials are set in .env (SMTP_RELAY_*) — see docs/email-relay.md',
    email_test_to: 'Send a test email to', email_send_test: 'Send test',
    email_verif_on: 'Email verification is required', email_verif_off: 'Email verification is optional',
    inactive: 'Disabled',
    ch_title_h: 'Required channels (join before using the bot)',
    ch_intro: 'A user must be a member of every active channel below before using the sales bot.',
    ch_add: 'Add channel', ch_cancel: 'Cancel', ch_confirm_del: 'Delete this channel?',
    ch_none: 'No channels added yet.',
    ch_id: 'Channel (@username or -100...)', ch_title: 'Title (optional)',
    ch_invite: 'Invite link (for private channels)',
    ch_invite_hint: 'For a private channel with no username, add its invite link so users get a “Join” button.',
    ch_members: 'members', ch_test: 'Test access',
    force_join: 'Force channel join (force_channel_join)',
    force_phone: 'Force phone-number share (force_share_phone)',
    ch_admin_hint: 'To check user membership, the sales bot must be an ADMIN of each channel. After adding a channel, make the bot an admin there, then click “Test access”.',
  },
}

/* ================================================================== *
 *  Pasargad / PasarGuard Panels  —  /panel/panel-link                *
 *  Multi-panel manager: list, add, edit, disable, delete.            *
 * ================================================================== */
const PL_ICONS = {
  test: <><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></>,
  ssl: <><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0110 0v4" /></>,
  sync: <><path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" /></>,
}

function PanelRow({ s, panel, onEdit, onDeleted }) {
  const [msg, setMsg] = useState(null)
  const [testing, setTesting] = useState(false)
  const groups = panel.default_group_ids || []
  const inUse = panel.plan_count > 0 || panel.service_count > 0

  const test = async () => {
    setTesting(true); setMsg(null)
    try {
      const r = await api.post(`/admin/panels/${panel.id}/test/`)
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
    } catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
    finally { setTesting(false) }
  }
  const del = async () => {
    if (!confirm(s.confirm_del)) return
    try { await api.delete(`/admin/panels/${panel.id}/`); onDeleted?.() }
    catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
  }

  return (
    <div className={'card pl-row' + (panel.is_active ? '' : ' pl-row--off')}>
      <div className="pl-row-main">
        <span className={'pl-row-ico ' + (panel.is_active ? 'on' : 'off')}>
          <Ico d={ICONS.link} w={20} />
        </span>
        <div className="min-w-0">
          <div className="pl-row-title">
            <b>{panel.name}</b>
            <span className={'pl-tag ' + (panel.is_active ? 'ok' : 'muted')}>
              {panel.is_active ? s.pl_connected : s.pl_disabled}
            </span>
            <span className={'pl-tag ' + (panel.verify_ssl ? 'ssl' : 'muted')}>
              <Ico d={PL_ICONS.ssl} w={11} />{panel.verify_ssl ? s.pl_ssl_on : s.pl_ssl_off}
            </span>
          </div>
          <div className="pl-row-url" dir="ltr">{panel.base_url}</div>
          <div className="pl-row-meta">
            <span>{s.pl_usage.replace('{p}', panel.plan_count ?? 0).replace('{s}', panel.service_count ?? 0)}</span>
            <span className="pl-row-groups">
              {s.pl_node_groups}{' '}
              {groups.length
                ? groups.map((g) => <span key={g} className="pl-gchip" dir="ltr">{g}</span>)
                : <span className="text-muted">{s.pl_no_groups}</span>}
            </span>
          </div>
        </div>
      </div>

      {msg && <div className="pl-row-msg"><Alert kind={msg.kind}>{msg.text}</Alert></div>}

      <div className="pl-row-acts">
        <button type="button" className="pl-rbtn" onClick={test} disabled={testing}>
          <Ico d={PL_ICONS.test} w={14} />{testing ? '…' : s.test}
        </button>
        <button type="button" className="pl-rbtn pl-rbtn--primary" onClick={onEdit}>
          <Ico d={ICONS.edit} w={14} />{s.pl_edit}
        </button>
        {!inUse && (
          <button type="button" className="pl-rbtn pl-rbtn--del" onClick={del}>
            <Ico d={ICONS.trash} w={14} />{s.del_panel}
          </button>
        )}
      </div>
    </div>
  )
}

function PlStat({ label, value, unit, lang }) {
  return (
    <div className="card pl-stat">
      <span className="pl-stat-label">{label}</span>
      <div className="pl-stat-val">{digits(value, lang)}<span className="pl-stat-unit"> {unit}</span></div>
    </div>
  )
}

export function PanelConnection() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [panels, setPanels] = useState(null)
  const [editId, setEditId] = useState(null) // panel id | 'new' | null
  const [err, setErr] = useState('')

  const load = () =>
    api.get('/admin/panels/')
      .then((r) => { setPanels(r.data.results || r.data || []); setErr('') })
      .catch((e) => { setPanels([]); setErr(apiError(e)) })

  useEffect(() => { load() }, [])

  const stats = useMemo(() => {
    const ps = panels || []
    return {
      total: ps.length,
      active: ps.filter((p) => p.is_active).length,
      plans: ps.reduce((a, p) => a + (p.plan_count || 0), 0),
      svc: ps.reduce((a, p) => a + (p.service_count || 0), 0),
    }
  }, [panels])

  if (!panels) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <style>{INT_CSS}</style>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="int-head">
          <span className="int-head-ico"><Ico d={ICONS.link} w={20} /></span>
          <div>
            <h1 className="text-lg font-bold">{s.pl_h}</h1>
            <p className="mt-1 text-sm text-muted">{s.panel_intro}</p>
          </div>
        </div>
        {editId == null && (
          <button className="btn-primary shrink-0 text-sm inline-flex items-center gap-1.5" onClick={() => setEditId('new')}>
            <Ico d={ICONS.plus} w={14} /> {s.add_panel}
          </button>
        )}
      </div>

      <Alert>{err}</Alert>

      {editId == null && panels.length > 0 && (
        <div className="pl-stats">
          <PlStat label={s.pl_st_total} value={stats.total} unit={s.pl_st_total_u} lang={lang} />
          <PlStat label={s.pl_st_active} value={stats.active} unit={s.pl_st_active_u} lang={lang} />
          <PlStat label={s.pl_st_plans} value={stats.plans} unit={s.pl_st_plans_u} lang={lang} />
          <PlStat label={s.pl_st_svc} value={stats.svc} unit={s.pl_st_svc_u} lang={lang} />
        </div>
      )}

      {editId === 'new' && (
        <PanelCard s={s} isNew
          onSaved={() => { setEditId(null); load() }}
          onCancel={() => setEditId(null)} />
      )}

      {editId == null && panels.length > 0 && (
        <div className="pl-list-h">
          <h2 className="font-bold text-sm">{s.pl_list_h}</h2>
          <span className="pl-count-badge">{s.pl_count.replace('{n}', digits(panels.length, lang))}</span>
        </div>
      )}

      {editId == null && panels.length === 0 && (
        <div className="card text-center text-muted">{s.pl_none}</div>
      )}

      {panels.map((p) => (
        editId === p.id ? (
          <PanelCard key={p.id} s={s} panel={p}
            onSaved={() => { load(); setEditId(null) }}
            onDeleted={() => { load(); setEditId(null) }}
            onCancel={() => setEditId(null)} />
        ) : editId == null ? (
          <PanelRow key={p.id} s={s} panel={p} onEdit={() => setEditId(p.id)} onDeleted={load} />
        ) : null
      ))}

      {editId == null && <EmailCard s={s} />}
    </div>
  )
}

function PanelCard({ s, panel, isNew = false, onSaved, onDeleted, onCancel }) {
  const { t } = useI18n()
  const blank = {
    name: '', base_url: '', admin_username: '', admin_password: '',
    subscription_base_url: '', verify_ssl: true, is_active: true,
  }
  const [form, setForm] = useState(
    isNew ? blank : {
      name: panel.name || '', base_url: panel.base_url || '',
      admin_username: panel.admin_username || '', admin_password: '',
      subscription_base_url: panel.subscription_base_url || '',
      verify_ssl: panel.verify_ssl ?? true, is_active: panel.is_active ?? true,
    },
  )
  const [selected, setSelected] = useState(panel?.default_group_ids || [])
  const [groups, setGroups] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const toggleGroup = (id) =>
    setSelected((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))

  const groupRows = useMemo(() => {
    if (!groups) return null
    const byId = new Map(groups.map((g) => [g.id, g.name]))
    selected.forEach((id) => { if (!byId.has(id)) byId.set(id, `${s.group_word} ${id}`) })
    return [...byId.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.id - b.id)
  }, [groups, selected, s.group_word])

  const fetchGroups = async () => {
    setFetching(true); setMsg(null)
    try {
      const r = await api.get(`/admin/panels/${panel.id}/groups/`)
      setGroups(r.data.groups || [])
    } catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
    finally { setFetching(false) }
  }

  const test = async () => {
    setTesting(true); setMsg(null)
    try {
      const r = await api.post(`/admin/panels/${panel.id}/test/`)
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
    } catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
    finally { setTesting(false) }
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true); setMsg(null)
    const body = { ...form, default_group_ids: selected }
    if (!body.admin_password) delete body.admin_password
    try {
      if (isNew) await api.post('/admin/panels/', body)
      else await api.patch(`/admin/panels/${panel.id}/`, body)
      onSaved?.()
      if (!isNew) setMsg({ kind: 'success', text: s.saved })
    } catch (e2) { setMsg({ kind: 'danger', text: apiError(e2) }) }
    finally { setSaving(false) }
  }

  const del = async () => {
    if (!confirm(s.confirm_del)) return
    try { await api.delete(`/admin/panels/${panel.id}/`); onDeleted?.() }
    catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
  }

  const inUse = !isNew && (panel.plan_count > 0 || panel.service_count > 0)

  return (
    <form onSubmit={save} className="card grid gap-4 sm:grid-cols-2">
      <div className="flex flex-wrap items-center justify-between gap-2 sm:col-span-2">
        <span className="int-card-head font-bold">
          <span className="int-card-ico"><Ico d={ICONS.link} w={16} /></span>
          {isNew ? s.new_panel : (form.name || panel.name)}
        </span>
        {!isNew && (
          <span className="text-xs text-muted">
            {panel.plan_count} {s.in_use} · {panel.service_count} {s.in_use2}
          </span>
        )}
      </div>

      {msg && <div className="sm:col-span-2"><Alert kind={msg.kind}>{msg.text}</Alert></div>}

      <Field label={s.panel_name}>
        <input className="input" required placeholder="Wireguard / Unlimited / Volume"
          value={form.name} onChange={(e) => set('name', e.target.value)} />
      </Field>
      <Field label={s.base_url}>
        <input className="input" dir="ltr" required placeholder="https://panel.example.com"
          value={form.base_url} onChange={(e) => set('base_url', e.target.value)} />
      </Field>
      <Field label={s.admin_user}>
        <input className="input" dir="ltr" required
          value={form.admin_username} onChange={(e) => set('admin_username', e.target.value)} />
      </Field>
      <Field label={s.admin_pass}>
        <SecretInput
          placeholder={!isNew && panel.admin_password_set ? s.unchanged : ''}
          value={form.admin_password} onChange={(e) => set('admin_password', e.target.value)} />
        <span className="mt-1 block text-xs text-muted">
          {!isNew && panel.admin_password_set ? s.pass_stored : s.pass_none}
        </span>
      </Field>
      <Field label={s.sub_url}>
        <input className="input" dir="ltr"
          value={form.subscription_base_url} onChange={(e) => set('subscription_base_url', e.target.value)} />
      </Field>

      <label className="flex items-center gap-2 self-end text-sm">
        <Toggle checked={form.verify_ssl} onChange={(v) => set('verify_ssl', v)} label={s.verify_ssl} />
        {s.verify_ssl}
      </label>

      {/* ---- this panel's default groups ---- */}
      <div className="sm:col-span-2">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="label mb-0">{s.groups}</span>
          {!isNew && (
            <button type="button" className="btn-ghost text-xs" onClick={fetchGroups} disabled={fetching}>
              {fetching ? s.fetching : `⭳ ${s.fetch_groups}`}
            </button>
          )}
        </div>
        <p className="mb-2 text-xs text-muted">{s.groups_hint}</p>

        {isNew ? (
          <p className="text-xs text-muted">{s.groups_none_fetched.split('.')[0]}.</p>
        ) : !groupRows ? (
          <p className="text-sm">
            {s.groups_none_fetched}{' '}
            <span dir="ltr" className="font-mono">
              {selected.length ? selected.join(', ') : s.groups_empty}
            </span>
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {groupRows.map((g) => (
              <label key={g.id} className="flex items-center gap-2 rounded-xl border px-3 py-2 text-sm"
                style={{ borderColor: 'var(--c-border)' }}>
                <input type="checkbox" checked={selected.includes(g.id)} onChange={() => toggleGroup(g.id)} />
                <span className="truncate">{g.name}</span>
                <span dir="ltr" className="ms-auto shrink-0 text-xs text-muted">#{g.id}</span>
              </label>
            ))}
            {groupRows.length === 0 && <p className="text-sm text-muted">—</p>}
          </div>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <Toggle checked={form.is_active} onChange={(v) => set('is_active', v)} label={s.panel_active} />
        {s.panel_active}
      </label>

      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <button className="btn-primary text-sm" disabled={saving}>{saving ? '…' : s.save}</button>
        {!isNew && (
          <button type="button" className="btn-ghost text-sm" onClick={test} disabled={testing}>
            {testing ? '…' : s.test}
          </button>
        )}
        {onCancel && (
          <button type="button" className="btn-ghost text-sm" onClick={onCancel}>{t('cancel')}</button>
        )}
        {!isNew && !inUse && (
          <button type="button" className="btn-ghost ms-auto text-sm inline-flex items-center gap-1.5"
            style={{ color: 'var(--c-danger)' }} onClick={del}><Ico d={ICONS.trash} w={14} /> {s.del_panel}</button>
        )}
      </div>
    </form>
  )
}

function EmailCard({ s }) {
  const [st, setSt] = useState(null)
  const [to, setTo] = useState('')
  const [sending, setSending] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    api.get('/admin/integrations/email/').then((r) => setSt(r.data)).catch(() => setSt({ error: true }))
  }, [])

  const sendTest = async () => {
    setSending(true); setMsg(null)
    try {
      const r = await api.post('/admin/integrations/email/', { to })
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
    } catch (e) {
      setMsg({ kind: 'danger', text: apiError(e) })
    } finally { setSending(false) }
  }

  if (!st) return <div className="card"><Spinner /></div>
  if (st.error) return null

  const dot = (ok) => (
    <span className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ background: ok ? 'var(--c-success)' : 'var(--c-danger)' }} />
  )

  return (
    <div className="card space-y-3">
      <div className="font-bold">{s.email_title}</div>

      <div className="space-y-1.5 text-sm">
        <div className="flex items-center gap-2">
          {dot(st.external_delivery_ready)}
          <span>{st.external_delivery_ready ? s.email_ready : s.email_not_ready}</span>
        </div>
        <div className="flex items-center gap-2">
          {dot(st.relay_configured)}
          <span className="text-muted">
            {st.relay_configured ? `${s.email_relay_on} — ${st.relay_host}` : s.email_relay_off}
          </span>
        </div>
        <div className="text-xs text-muted">
          {s.email_host}: <span dir="ltr">{st.host || '—'}:{st.port}</span> · {s.email_from}: <span dir="ltr">{st.from_address}</span>
        </div>
        <div className="text-xs text-muted">
          {st.verification_required ? s.email_verif_on : s.email_verif_off}
        </div>
        <p className="text-xs text-muted">{s.email_relay_hint}</p>
      </div>

      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1" style={{ minWidth: '12rem' }}>
          <Field label={s.email_test_to}>
            <input className="input" dir="ltr" type="email" placeholder="you@example.com"
              value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
        <button type="button" className="btn-ghost text-sm" onClick={sendTest} disabled={sending || !to}>
          {sending ? '…' : s.email_send_test}
        </button>
      </div>
    </div>
  )
}

/* ================================================================== *
 *  Telegram Bots  —  /panel/bots                                     *
 * ================================================================== */
export function Bots() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [data, setData] = useState(null)
  const [sales, setSales] = useState(null)
  const [backup, setBackup] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState('')

  const hydrate = (row) => ({
    token: '',
    proxy_url: row.proxy_url || '',
    backup_chat_id: row.backup_chat_id ?? '',
    is_active: row.is_active ?? false,
  })

  const load = () =>
    api.get('/admin/integrations/telegram/').then((r) => {
      setData(r.data)
      setSales(hydrate(r.data.sales))
      setBackup(hydrate(r.data.backup))
    }).catch(() => setData({ error: true }))

  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault()
    setErr(''); setMsg(null)
    const clean = (o, isBackup) => {
      const body = { proxy_url: o.proxy_url || null, is_active: o.is_active }
      if (o.token) body.token = o.token
      if (isBackup) body.backup_chat_id = o.backup_chat_id === '' ? null : Number(o.backup_chat_id)
      return body
    }
    try {
      await api.put('/admin/integrations/telegram/', {
        sales: clean(sales, false),
        backup: clean(backup, true),
      })
      setMsg({ kind: 'success', text: s.bots_saved })
      load()
    } catch (e2) { setErr(apiError(e2)) }
  }

  if (!data) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <style>{INT_CSS}</style>
      <div className="int-head">
        <span className="int-head-ico"><Ico d={ICONS.bot} w={20} /></span>
        <div>
          <h1 className="text-lg font-bold">{t('bots')}</h1>
          <p className="mt-1 text-sm text-muted">{s.bots_intro}</p>
        </div>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      <form onSubmit={save} className="space-y-4">
        <div className="int-bot-grid">
          {sales && <BotCard title={s.sales_bot} icon={ICONS.cart} row={data.sales} value={sales} onChange={setSales} s={s} />}
          {backup && <BotCard title={s.backup_bot} icon={ICONS.backup} row={data.backup} value={backup} onChange={setBackup} s={s} showChatId />}
        </div>
        <button className="btn-primary text-sm">{s.save}</button>
      </form>

      <RequiredChannels s={s} />
    </div>
  )
}

/* ================================================================== *
 *  Forced-join channels  —  on the Bots page                         *
 * ================================================================== */
function RequiredChannels({ s }) {
  const { lang } = useI18n()
  const blank = { channel_id: '', title: '', invite_link: '', is_active: true }
  const [rows, setRows] = useState(null)
  const [enf, setEnf] = useState({ force_channel_join: false, force_share_phone: false })
  const [edit, setEdit] = useState(null)          // {channel...} | null
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState(null)
  const [testing, setTesting] = useState(null)    // channel id being tested

  const load = () =>
    api.get('/admin/channels/').then((r) => {
      setRows(r.data.results || [])
      setEnf(r.data.enforcement || {})
    }).catch((e) => { setRows([]); setMsg({ kind: 'danger', text: apiError(e) }) })
  useEffect(() => { load() }, [])

  const setToggle = async (k, v) => {
    setEnf((c) => ({ ...c, [k]: v }))
    try { await api.patch('/admin/channels/enforcement/', { [k]: v }) }
    catch (e) { setMsg({ kind: 'danger', text: apiError(e) }); load() }
  }

  const saveChannel = async (e) => {
    e.preventDefault(); setMsg(null)
    const body = { ...edit }
    try {
      if (edit.id) await api.patch(`/admin/channels/${edit.id}/`, body)
      else await api.post('/admin/channels/', body)
      setEdit(null); setAdding(false); load()
    } catch (e2) { setMsg({ kind: 'danger', text: apiError(e2) }) }
  }

  const del = async (id) => {
    if (!confirm(s.ch_confirm_del)) return
    try { await api.delete(`/admin/channels/${id}/`); load() }
    catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
  }

  const test = async (id) => {
    setTesting(id); setMsg(null)
    try {
      const r = await api.post(`/admin/channels/${id}/test/`)
      setMsg({ kind: r.data.ok ? 'success' : 'danger', text: r.data.detail })
      load()
    } catch (e) { setMsg({ kind: 'danger', text: apiError(e) }) }
    finally { setTesting(null) }
  }

  if (!rows) return <div className="card"><Spinner /></div>

  const Form = ({ value, onChange, onSubmit, onCancel }) => (
    <form onSubmit={onSubmit} className="card grid gap-3 sm:grid-cols-2"
      style={{ background: 'color-mix(in srgb, var(--c-primary) 5%, var(--c-surface))' }}>
      <Field label={s.ch_id}>
        <input className="input" dir="ltr" required placeholder="@mychannel  یا  -1001234567890"
          value={value.channel_id} onChange={(e) => onChange({ ...value, channel_id: e.target.value })} />
      </Field>
      <Field label={s.ch_title}>
        <input className="input" value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })} />
      </Field>
      <div className="sm:col-span-2">
        <Field label={s.ch_invite}>
          <input className="input" dir="ltr" placeholder="https://t.me/+AbC..."
            value={value.invite_link} onChange={(e) => onChange({ ...value, invite_link: e.target.value })} />
        </Field>
        <p className="mt-1 text-xs text-muted">{s.ch_invite_hint}</p>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Toggle checked={value.is_active} onChange={(v) => onChange({ ...value, is_active: v })} label={s.active} />
        {s.active}
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <button className="btn-primary text-sm">{s.save}</button>
        <button type="button" className="btn-ghost text-sm" onClick={onCancel}>{s.ch_cancel}</button>
      </div>
    </form>
  )

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-bold">{s.ch_title_h}</h2>
          <p className="mt-1 text-sm text-muted">{s.ch_intro}</p>
        </div>
        {!adding && !edit && (
          <button className="btn-primary shrink-0 text-sm" onClick={() => { setAdding(true); setEdit({ ...blank }) }}>
            + {s.ch_add}
          </button>
        )}
      </div>

      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      {/* enforcement toggles */}
      <div className="card">
        <div className="toggle-row">
          <span className="text-sm">{s.force_join}</span>
          <Toggle checked={!!enf.force_channel_join}
            onChange={(v) => setToggle('force_channel_join', v)} label={s.force_join} />
        </div>
        <div className="toggle-row">
          <span className="text-sm">{s.force_phone}</span>
          <Toggle checked={!!enf.force_share_phone}
            onChange={(v) => setToggle('force_share_phone', v)} label={s.force_phone} />
        </div>
      </div>

      <div className="rounded-xl p-3 text-xs" style={{ background: 'color-mix(in srgb, var(--c-warning) 12%, transparent)', color: 'var(--c-warning)' }}>
        ⚠️ {s.ch_admin_hint}
      </div>

      {adding && <Form value={edit} onChange={setEdit} onSubmit={saveChannel}
        onCancel={() => { setAdding(false); setEdit(null) }} />}

      {rows.length === 0 && !adding && (
        <div className="card text-center text-sm text-muted">{s.ch_none}</div>
      )}

      {rows.map((c) => (
        edit && edit.id === c.id ? (
          <Form key={c.id} value={edit} onChange={setEdit} onSubmit={saveChannel}
            onCancel={() => setEdit(null)} />
        ) : (
          <div key={c.id} className="card flex flex-wrap items-center gap-3">
            <span className={'shrink-0 rounded-full px-2 py-0.5 text-xs ' + (c.is_active ? '' : 'opacity-60')}
              style={{ background: c.is_active ? 'color-mix(in srgb, var(--c-success) 16%, transparent)' : 'var(--c-border)',
                color: c.is_active ? 'var(--c-success)' : 'var(--c-text-muted)' }}>
              {c.is_active ? s.active : s.inactive}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-bold">{c.title || c.channel_id}</div>
              <div dir="ltr" className="truncate text-xs text-muted">{c.channel_id}</div>
            </div>
            <div className="text-xs text-muted">
              {s.ch_members}: {c.member_count ?? 0}
              {c.last_synced_at ? ` · ${new Date(c.last_synced_at).toLocaleDateString(lang === 'fa' ? 'fa-IR' : 'en-GB')}` : ''}
            </div>
            <div className="flex gap-1">
              <button className="btn-ghost text-xs" onClick={() => test(c.id)} disabled={testing === c.id}>
                {testing === c.id ? '…' : s.ch_test}
              </button>
              <button className="int-icon-btn" title={s.save} onClick={() => { setEdit({ ...c }); setAdding(false) }}><Ico d={ICONS.edit} w={15} /></button>
              <button className="int-icon-btn int-icon-btn--del" onClick={() => del(c.id)}><Ico d={ICONS.trash} w={15} /></button>
            </div>
          </div>
        )
      ))}
    </div>
  )
}

function BotCard({ title, icon, row, value, onChange, s, showChatId }) {
  const set = (k, v) => onChange({ ...value, [k]: v })
  return (
    <div className="card int-bot-card flex flex-col gap-4">
      <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--c-border)' }}>
        <span className="int-card-head font-bold">
          <span className="int-card-ico"><Ico d={icon || ICONS.bot} w={16} /></span>{title}
        </span>
        <label className="flex items-center gap-2 text-sm">
          <Toggle checked={value.is_active} onChange={(v) => set('is_active', v)} label={s.active} />
          {s.active}
        </label>
      </div>

      <Field label={s.bot_token}>
        <SecretInput placeholder={row.token_set ? s.unchanged : '123456:ABC-DEF…'}
          value={value.token} onChange={(e) => set('token', e.target.value)} />
        <span className="mt-1 block text-xs text-muted">
          {row.token_set ? s.token_stored : s.token_none}
        </span>
      </Field>

      <Field label={s.proxy}>
        <input className="input" dir="ltr" placeholder="socks5://user:pass@host:port"
          value={value.proxy_url} onChange={(e) => set('proxy_url', e.target.value)} />
      </Field>

      {showChatId && (
        <Field label={s.chat_id}>
          <input className="input" dir="ltr" inputMode="numeric" placeholder="-1001234567890"
            value={value.backup_chat_id} onChange={(e) => set('backup_chat_id', e.target.value)} />
          <span className="mt-1 block text-xs text-muted">{s.chat_hint}</span>
        </Field>
      )}
    </div>
  )
}
