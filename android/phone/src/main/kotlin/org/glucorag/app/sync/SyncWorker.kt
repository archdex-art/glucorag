package org.glucorag.app.sync

import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.tasks.await
import org.glucorag.app.R
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.QueueDb
import org.glucorag.app.data.QueuedReading
import org.glucorag.app.data.SessionStore
import org.glucorag.app.data.SyncState
import org.glucorag.app.net.GlucoApi
import org.glucorag.shared.CgmReading
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec
import org.glucorag.shared.Thinner

/** Writes the snapshot DataItem the watch reads, marked urgent so it syncs without delay. */
class SnapshotPublisher(private val context: Context) {
    suspend fun publish(s: Snapshot) {
        val request = PutDataMapRequest.create(SnapshotCodec.PATH).apply {
            dataMap.putByteArray(SnapshotCodec.DATA_KEY, SnapshotCodec.encode(s))
        }.asPutDataRequest().setUrgent()
        Wearable.getDataClient(context).putDataItem(request).await()
    }
}

/** From a received CGM reading to the queue, the watch and the upload. */
object Pipeline {
    /**
     * Records [reading] as the phone's newest value. If it is due for upload (≈ every 5 min):
     * queues it, shows it on the watch right away (the server may be out of reach), and starts a
     * sync when signed in. Readings are queued whenever a server is set up, so readings taken while
     * the token was revoked upload after the next sign-in.
     */
    suspend fun receive(context: Context, reading: CgmReading, nowMs: Long = System.currentTimeMillis()) {
        val app = context.applicationContext
        val local = LocalState.get(app)
        local.offerReading(reading)
        val store = SessionStore(app)
        val session = store.current()
        if (session.server == null || !Thinner(session.lastQueuedT).shouldQueue(reading.t)) return
        QueueDb.get(app).queue().insert(QueuedReading(reading.t, reading.mgdl, reading.from))
        store.update { it.copy(lastQueuedT = reading.t) }
        local.snapshot.value?.let { last ->
            val updated = withReading(last, reading, nowMs)
            if (updated !== last) publishQuietly(app, local, updated)
        }
        if (session.token != null) SyncWorker.enqueue(app)
    }

    suspend fun publishQuietly(context: Context, local: LocalState, s: Snapshot) {
        local.setSnapshot(s)
        try {
            SnapshotPublisher(context).publish(s)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            // No Wear OS / Play services: the phone still shows the snapshot itself.
        }
    }
}

/** One sync run (see [SyncEngine]). Failures end the run; the next queued reading retries. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext
        val store = SessionStore(app)
        val session = store.current()
        val server = session.server ?: return Result.success()
        val token = session.token ?: return Result.success()
        val api = try {
            GlucoApi(server, GlucoApi.defaultClient(), { token })
        } catch (e: IllegalArgumentException) {
            return Result.success()
        }
        val local = LocalState.get(app)
        val engine = SyncEngine(
            api = api,
            queue = QueueDb.get(app).queue(),
            store = store,
            publish = { s ->
                local.setSnapshot(s)
                SnapshotPublisher(app).publish(s)
            },
            notify = AlertNotifier(app)::notify,
            clock = System::currentTimeMillis,
            latestReading = { local.reading.value },
            lastSnapshot = { local.snapshot.value },
        )
        val outcome = engine.run()
        val now = System.currentTimeMillis()
        when (outcome) {
            is SyncOutcome.Synced -> local.recordSync(SyncState.SYNCED, now, outcome.refused)
            is SyncOutcome.Retry -> local.recordSync(SyncState.UNREACHABLE, now, 0)
            is SyncOutcome.NeedsSetup -> local.recordSync(SyncState.NEEDS_SETUP, now, 0)
            is SyncOutcome.SignedOut -> {
                local.recordSync(SyncState.SIGNED_OUT, now, 0)
                // The server revoked this device: stop retrying until the user signs in again.
                store.update { it.copy(token = null) }
            }
        }
        return Result.success()
    }

    /** Needed for expedited work on Android 9–11, where it runs as a foreground service. */
    override suspend fun getForegroundInfo(): ForegroundInfo {
        Channels.ensure(applicationContext)
        val notification = NotificationCompat.Builder(applicationContext, Channels.SYNC)
            .setSmallIcon(R.drawable.ic_stat_glucorag)
            .setContentTitle("Uploading readings")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(FOREGROUND_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(FOREGROUND_ID, notification)
        }
    }

    companion object {
        private const val WORK = "sync"
        private const val FOREGROUND_ID = 7_001

        /** Starts a sync unless one is already queued or running (it drains the whole queue). */
        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(WORK, ExistingWorkPolicy.KEEP, request)
        }
    }
}
