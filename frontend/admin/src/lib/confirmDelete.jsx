// Generic "delete X?" through the shared ConfirmDialog — used by every admin
// list that deletes a row (pages, roles, staff, plans, cards, panels, SMS …).
import { useConfirm } from '../components/ConfirmDialog'
import { useI18n } from './i18n'

const T = {
  fa: {
    title: (what) => `حذف ${what}`, btn: 'بله، حذف کن', impact: 'دامنه تأثیر عملیات:', tag: 'غیرقابل بازگشت',
    msg: (name) => <>آیا از حذف <strong>{name}</strong> اطمینان دارید؟ این کار قابل بازگشت نیست.</>,
    id: 'شناسه:',
  },
  en: {
    title: (what) => `Delete ${what}`, btn: 'Yes, delete', impact: 'Impact:', tag: 'Irreversible',
    msg: (name) => <>Delete <strong>{name}</strong>? This cannot be undone.</>,
    id: 'ID:',
  },
}

/** returns `ask({ what, name, id?, note?, action })` → Promise<boolean>.
 * `action` runs with the confirm button spinning; an error stays in the dialog. */
export function useDeleteConfirm() {
  const confirm = useConfirm()
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  return ({ what, name, id, note, action }) => confirm({
    tone: 'danger', icon: 'trash',
    title: s.title(what),
    targetLabel: id != null ? s.id : undefined, targetId: id != null ? `#${id}` : undefined,
    message: <>{s.msg(name)}{note ? <><br />{note}</> : null}</>,
    details: { title: s.impact, tag: s.tag },
    confirmLabel: s.btn,
    action,
  })
}
