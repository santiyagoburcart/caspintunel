// v1.59 our panel's store filter for CRM + «تحلیل کسب‌وکار»: the chosen store id (this tab only) is sent as `?store=` on every
// /admin/crm/ request (lib/api.js). The server ignores it on a store's own domain — a store only ever sees itself.
const KEY = 'ct_crm_store'
export function getStoreScope() { try { return sessionStorage.getItem(KEY) || '' } catch { return '' } }
export function setStoreScope(id) { try { id ? sessionStorage.setItem(KEY, String(id)) : sessionStorage.removeItem(KEY) } catch { /* private mode */ } }
export const isScopedUrl = (url) => /^\/admin\/crm\//.test(url || '') && !/^\/admin\/crm\/stores\//.test(url || '')
