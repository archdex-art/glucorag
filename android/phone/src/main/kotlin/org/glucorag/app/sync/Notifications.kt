package org.glucorag.app.sync

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import org.glucorag.app.R
import org.glucorag.app.forecast.LocalAlert
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.formatGlucose

/** Notification channels. Importance is fixed when a channel is first created. */
object Channels {
    const val ALERTS = "alerts"
    const val SYNC = "sync"

    fun ensure(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(ALERTS, "Forecast alerts", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "A low or high likely within the hour"
            },
        )
        manager.createNotificationChannel(
            NotificationChannel(SYNC, "Uploading readings", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Shown while readings upload on older Android versions"
            },
        )
    }

    fun canPost(context: Context): Boolean =
        (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
            NotificationManagerCompat.from(context).areNotificationsEnabled()

    /** Opens the app when a notification is tapped. */
    fun openApp(context: Context): PendingIntent? = context.packageManager.getLaunchIntentForPackage(context.packageName)?.let {
        PendingIntent.getActivity(context, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}

/**
 * Posts alerts on the high-importance channel, one notification per type (a newer one replaces
 * the last). Never ongoing or local-only, so Wear OS bridges it to the watch.
 */
class AlertNotifier(private val context: Context) {
    fun notify(alert: LocalAlert, unit: GlucoseUnit, nowMs: Long) {
        val low = alert.type == "hypo"
        post(if (low) LOW_ID else HIGH_ID, title(low, alert.at, alert.couldReachMgdl, unit, nowMs))
    }

    /** A local test notification on the same channel, so the user can check the watch shows it. */
    fun test() = post(TEST_ID, "Test alert from GlucoRAG")

    private fun post(id: Int, title: String) {
        Channels.ensure(context)
        if (!Channels.canPost(context)) return
        val notification = NotificationCompat.Builder(context, Channels.ALERTS)
            .setSmallIcon(R.drawable.ic_stat_glucorag)
            .setContentTitle(title)
            .setContentText(BODY)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setAutoCancel(true)
            .setContentIntent(Channels.openApp(context))
            .build()
        try {
            NotificationManagerCompat.from(context).notify(id, notification)
        } catch (e: SecurityException) {
            // The permission was revoked between the check and the post.
        }
    }

    companion object {
        const val BODY = "Research forecast. Your CGM app's alarms still apply."
        private const val TEST_ID = -1
        private const val LOW_ID = 1
        private const val HIGH_ID = 2
        private const val MINUTE_MS = 60_000L

        /** "Low likely in about 25 min (could reach 66 mg/dL)." [at] is when it first crosses 70 / 180. */
        fun title(low: Boolean, at: Long, couldReachMgdl: Double, unit: GlucoseUnit, nowMs: Long): String {
            val word = if (low) "Low" else "High"
            val minutes = (at - nowMs + MINUTE_MS - 1) / MINUTE_MS
            val time = if (minutes > 0) "in about $minutes min" else "soon"
            return "$word likely $time (could reach ${formatGlucose(couldReachMgdl, unit)} ${unit.label})."
        }
    }
}
