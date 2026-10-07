package org.glucorag.wear.data

import android.content.ComponentName
import android.content.Context
import androidx.wear.tiles.TileService
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.google.android.gms.wearable.DataMap
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec
import org.glucorag.shared.statusOf
import org.glucorag.wear.complication.ComplicationPusher
import org.glucorag.wear.complication.NextHourComplicationService
import org.glucorag.wear.complication.NowComplicationService
import org.glucorag.wear.tile.GlucoseTileService
import java.util.concurrent.TimeUnit

/** The encoded snapshot the phone put in its DataItem's map, or null if absent. */
fun snapshotPayload(map: DataMap): ByteArray? = map.getByteArray(SnapshotCodec.DATA_KEY)

/** Receiving a snapshot: the one path shared by the Data Layer listener and the debug receiver. */
object SnapshotSync {
    /** Serialises the load-decide-save of the persisted push throttle. */
    private val mutex = Mutex()

    /**
     * Saves [bytes] (if valid and newer), then updates complications and the tile within the
     * throttle limits, scheduling any held-back update. Returns the saved snapshot, or null if
     * nothing changed.
     */
    suspend fun receive(context: Context, bytes: ByteArray): Snapshot? = mutex.withLock {
        val app = context.applicationContext
        val saved = SnapshotStore(app).save(bytes) ?: return@withLock null
        update(app, saved) { pusher, kind, now -> pusher.decide(kind, now) }
        saved
    }

    /** Sends updates held back by the throttle; run by [DeferredUpdateWorker]. */
    suspend fun flush(context: Context) = mutex.withLock {
        val app = context.applicationContext
        update(app, SnapshotStore(app).latest()) { pusher, kind, now -> pusher.flush(kind, now) }
    }

    private fun update(
        app: Context,
        snapshot: Snapshot?,
        step: (ComplicationPusher, org.glucorag.shared.StatusKind, Long) -> ComplicationPusher.Decision,
    ) {
        val nowMs = System.currentTimeMillis()
        val pusher = ComplicationPusher.load(app)
        val decision = step(pusher, statusOf(snapshot, nowMs).kind, nowMs)
        pusher.save(app)
        if (decision.complications) {
            for (service in listOf(NowComplicationService::class.java, NextHourComplicationService::class.java)) {
                ComplicationDataSourceUpdateRequester.create(app, ComponentName(app, service)).requestUpdateAll()
            }
        }
        if (decision.tile) TileService.getUpdater(app).requestUpdate(GlucoseTileService::class.java)
        decision.retryAt?.let { at ->
            val request = OneTimeWorkRequestBuilder<DeferredUpdateWorker>()
                .setInitialDelay((at - nowMs).coerceAtLeast(0L), TimeUnit.MILLISECONDS)
                .build()
            // The newest retry time covers everything held back, so it replaces an older one.
            WorkManager.getInstance(app).enqueueUniqueWork(DEFERRED_WORK, ExistingWorkPolicy.REPLACE, request)
        }
    }

    private const val DEFERRED_WORK = "deferred-surface-update"
}

/** Sends tile/complication updates the throttle held back, once their window opens. */
class DeferredUpdateWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        SnapshotSync.flush(applicationContext)
        return Result.success()
    }
}
