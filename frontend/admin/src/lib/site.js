// Where this build lives and where the other SPA is. Production values are the
// defaults; the preview build (scripts/preview.sh) overrides them via env.
export const IS_PREVIEW = import.meta.env.VITE_PREVIEW === '1'
export const ADMIN_URL = import.meta.env.VITE_ADMIN_URL || '/panel/'
export const USER_URL = import.meta.env.VITE_USER_URL || '/'
