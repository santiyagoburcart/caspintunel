package com.caspintunel.smsbridge.work

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.caspintunel.smsbridge.repo.MAX_SEND_ATTEMPTS
import com.caspintunel.smsbridge.repo.SmsRepository
import java.util.concurrent.TimeUnit

private const val KEY_ENTRY_ID = "entry_id"

/** Sends one queued SMS log entry; retries (via WorkManager's own backoff) up
 * to [MAX_SEND_ATTEMPTS] times, then gives up and leaves the entry marked FAILED. */
class SmsSendWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val entryId = inputData.getLong(KEY_ENTRY_ID, -1L)
        if (entryId < 0) return Result.failure()

        val repo = SmsRepository.get(applicationContext)
        val ok = repo.attemptSend(entryId)
        if (ok) return Result.success()

        val entry = repo.getEntry(entryId)
        return if (entry != null && entry.attempts < MAX_SEND_ATTEMPTS) {
            Result.retry()
        } else {
            Result.failure()
        }
    }

    companion object {
        fun enqueue(context: Context, entryId: Long) {
            val request = OneTimeWorkRequestBuilder<SmsSendWorker>()
                .setInputData(workDataOf(KEY_ENTRY_ID to entryId))
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                "sms_send_$entryId",
                ExistingWorkPolicy.KEEP,
                request,
            )
        }
    }
}
