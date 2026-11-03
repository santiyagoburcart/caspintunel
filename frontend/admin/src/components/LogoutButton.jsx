import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useConfirm } from './ConfirmDialog'

// v1.38.1 the group manager's «خروج»: bottom of the desktop sidebar and of the Settings tab on phones,
// red, always behind a confirm (the avatar only opens Settings).
export default function LogoutButton({ className = '', testId = 'gm-logout' }) {
  const { logout } = useAuth()
  const { t } = useI18n()
  const confirm = useConfirm()
  const go = useNavigate()
  const ask = async () => {
    const ok = await confirm({ tone: 'danger', icon: 'warning', title: t('logout_q'), message: t('logout_msg'), confirmLabel: t('logout') })
    if (ok) { logout(); go('/login') }
  }
  return (
    <button type="button" className={'gm-out ' + className} onClick={ask} data-testid={testId}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>
      <span>{t('logout')}</span>
    </button>
  )
}

export const LOGOUT_CSS = `
.gm-out { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; min-height: 44px; padding: 0 14px; border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--c-danger) 40%, transparent); background: color-mix(in srgb, var(--c-danger) 6%, transparent);
  color: var(--c-danger-fg, var(--c-danger)); font: inherit; font-size: 14px; font-weight: 800; cursor: pointer; }
.gm-out:hover { background: color-mix(in srgb, var(--c-danger) 13%, transparent); }
.gm-out:focus-visible { outline: 2px solid var(--c-danger); outline-offset: 2px; }
.gm-out svg { width: 18px; height: 18px; flex-shrink: 0; }
`
