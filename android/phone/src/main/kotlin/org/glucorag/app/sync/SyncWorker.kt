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
import org.glucorag.app.data.LocalDb
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.QueuedReading
import org.glucorag.app.data.StoredReading
import org.glucorag.app.forecast.OnDevice
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

/** From a received CGM reading to the phone's store, the forecast, the watch and the upload. */
object Pipeline {
    /** [receiveAll] for one reading (a CGM app's broadcast). */
    suspend fun receive(context: Context, reading: CgmReading, nowMs: Long = System.currentTimeMillis()) =
        receiveAll(context, listOf(reading), nowMs)

    /**
     * Records each of [readings] (oldest first) as the phone's newest value. Those due for keeping
     * (≈ every 5 min) are stored, and queued for upload whenever a server is set up and not left
     * for this phone only (so readings taken while the token was revoked upload after the next
     * sign-in); then one forecast runs
     * on the phone and, when signed in, a sync starts.
     */
    suspend fun receiveAll(context: Context, readings: List<CgmReading>, nowMs: Long = System.currentTimeMillis()) {
        val app = context.applicationContext
        val local = LocalState.get(app)
        val store = SessionStore(app)
        val session = store.current()
        val thinner = Thinner(session.lastStoredT)
        val kept = readings.filter { r ->
            local.offerReading(r)
            thinner.shouldKeep(r.t)
        }
        if (kept.isEmpty()) return
        val db = LocalDb.get(app)
        db.readings().insert(kept.map { StoredReading(it.t, it.mgdl, it.from) })
        db.readings().deleteBefore(nowMs - StoredReading.KEEP_MS)
        if (session.server != null && !session.localOnly) db.queue().insertAll(kept.map { QueuedReading(it.t, it.mgdl, it.from) })
        store.update { it.copy(lastStoredT = thinner.lastKeptT) }
        OnDevice.run(app, nowMs)
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
            queue = LocalDb.get(app).queue(),
            store = store,
            localProfile = { local.profile.value },
            saveProfile = local::setProfile,
        )
        val outcome = engine.run()
        val now = System.currentTimeMillis()
        when (outcome) {
            is SyncOutcome.Synced -> {
                local.recordSync(SyncState.SYNCED, now, outcome.refused)
                // About you changed on the website: forecast again with it.
                if (outcome.profileChanged) OnDevice.run(app, now)
            }
            is SyncOutcome.Retry -> local.recordSync(SyncState.UNREACHABLE, now, 0)
            SyncOutcome.NeedsSetup -> local.recordSync(SyncState.NEEDS_SETUP, now, 0)
            SyncOutcome.SignedOut -> {
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
