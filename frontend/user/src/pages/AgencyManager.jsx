import { useEffect } from 'react'
import { useI18n } from '../lib/i18n'
import { ADMIN_LINK } from '../lib/paths'

// v1.25: the separate group-manager portal is gone — group managers sign in to the
// main admin panel (role "Group manager", same username and password). This route
// only forwards old bookmarks to the panel login.
export default function AgencyManager() {
  const { lang } = useI18n()
  const target = ADMIN_LINK ? `${ADMIN_LINK.replace(/\/+$/, '')}/login` : ''
  useEffect(() => { if (target) window.location.replace(target) }, [target])
  return (
    <div className="grid min-h-screen place-items-center p-6 text-center text-sm" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      {lang === 'fa'
        ? 'مدیران گروه حالا با همان نام کاربری و رمز در پنل اصلی مدیریت وارد می‌شوند.'
        : 'Group managers now sign in to the main admin panel with the same username and password.'}
      {target && <a className="mt-3 block text-primary underline" href={target}>{lang === 'fa' ? 'ورود به پنل' : 'Go to the panel sign-in'}</a>}
    </div>
  )
}
