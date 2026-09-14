package com.caspintunel.smsbridge.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.caspintunel.smsbridge.repo.SOURCES_STALE_MILLIS
import com.caspintunel.smsbridge.repo.SmsRepository
import java.util.concurrent.TimeUnit

private const val UNIQUE_NAME = "sms_sources_refresh"

/** Keeps the allowed-sender cache from going stale even when no SMS arrives
 * to trigger the lazy refresh in SmsReceiver — runs every 30 minutes while
 * the foreground service is alive. */
class SourcesRefreshWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        SmsRepository.get(applicationContext).refreshSources()
        // best-effort: a transient failure just means we retry on the next
        // periodic tick (or the next SMS/ping), never worth giving up on
        return Result.success()
    }

    companion object {
        fun enqueuePeriodic(context: Context) {
            val request = PeriodicWorkRequestBuilder<SourcesRefreshWorker>(
                SOURCES_STALE_MILLIS, TimeUnit.MILLISECONDS,
            ).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                UNIQUE_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
