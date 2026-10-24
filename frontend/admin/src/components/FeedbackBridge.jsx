import { useEffect } from 'react'
import { feedback, failureReason } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useToast } from './Toast'

// Turns every action's outcome (lib/api.js `feedback`) into a toast:
// "ذخیره شد" / the server's message, or the real failure reason.
const WORDS = {
  fa: { saved: 'ذخیره شد', deleted: 'حذف شد', done: 'انجام شد' },
  en: { saved: 'Saved', deleted: 'Deleted', done: 'Done' },
}

export default function FeedbackBridge() {
  const toast = useToast()
  const { lang } = useI18n()
  useEffect(() => {
    feedback.emit = ({ ok, method, url, data, error }) => {
      const w = WORDS[lang] || WORDS.fa
      if (!ok) { toast.error(failureReason(error, lang)); return }
      if (data && typeof data === 'object' && data.ok === false) {            // 200 with a failed test/action
        toast.error((lang !== 'en' && (data.message_fa || data.error_fa)) || data.message || data.error || data.detail || failureReason({ response: { status: 200, data } }, lang)); return
      }
      const server = data && typeof data === 'object' && typeof data.message === 'string' && data.message.length < 160 ? data.message : null
      // a server message in Persian (message_fa) is shown in fa too
      const serverFa = data && typeof data === 'object' && typeof data.message_fa === 'string' ? data.message_fa : null
      const generic = method === 'delete' ? w.deleted : /\/(test|run|sync|send|activate|restore|reset|revoke|status|approve|reject|void)\b|test\/?$/.test(url) ? w.done : w.saved
      toast.success(lang === 'en' ? (server || generic) : (serverFa || generic))
    }
    return () => { feedback.emit = null }
  }, [lang, toast])
  return null
}
