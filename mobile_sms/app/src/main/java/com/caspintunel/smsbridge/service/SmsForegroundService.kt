package com.caspintunel.smsbridge.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.caspintunel.smsbridge.MainActivity
import com.caspintunel.smsbridge.NOTIFICATION_CHANNEL_ID
import com.caspintunel.smsbridge.R
import com.caspintunel.smsbridge.work.SourcesRefreshWorker

/**
 * Persistent foreground service — its only real job is to keep the process
 * alive and show the "active" notification the SMS-receiving flow depends on.
 * The actual SMS handling happens in [com.caspintunel.smsbridge.receiver.SmsReceiver],
 * which is a manifest-registered receiver independent of this service's lifecycle;
 * this service exists so Android doesn't kill the app while it's supposed to be
 * watching for messages, and so [com.caspintunel.smsbridge.receiver.BootReceiver]
 * has something to (re)start after a reboot.
 */
class SmsForegroundService : Service() {

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())
        SourcesRefreshWorker.enqueuePeriodic(applicationContext)
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun buildNotification(): Notification {
        val openApp = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or pendingIntentImmutableFlag(),
        )
        return NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_text))
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setContentIntent(openApp)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun pendingIntentImmutableFlag(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0

    companion object {
        const val NOTIFICATION_ID = 1001
    }
}
