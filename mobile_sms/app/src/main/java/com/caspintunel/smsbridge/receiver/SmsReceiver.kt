package com.caspintunel.smsbridge.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import com.caspintunel.smsbridge.repo.SmsRepository
import com.caspintunel.smsbridge.work.SmsSendWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (messages.isNullOrEmpty()) return

        // one SmsMessage per PDU part — the same sender/timestamp, concatenate the bodies
        val sender = messages[0].originatingAddress ?: "unknown"
        val receivedAt = messages[0].timestampMillis
        val body = messages.joinToString(separator = "") { it.messageBody ?: "" }

        val pendingResult = goAsync()
        val appContext = context.applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val repo = SmsRepository.get(appContext)
                val entryId = repo.recordIncoming(sender, body, receivedAt)
                SmsSendWorker.enqueue(appContext, entryId)
            } finally {
                pendingResult.finish()
            }
        }
    }
}
