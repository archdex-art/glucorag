package org.glucorag.wear.data

import android.content.ComponentName
import android.content.Context
import androidx.wear.tiles.TileService
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.glucorag.shared.Snapshot
import org.glucorag.shared.statusOf
import org.glucorag.wear.complication.ComplicationPusher
import org.glucorag.wear.complication.NextHourComplicationService
import org.glucorag.wear.complication.NowComplicationService
import org.glucorag.wear.tile.GlucoseTileService

/** Receiving a snapshot: the one path shared by the Data Layer listener and the debug receiver. */
object SnapshotSync {
    /** Serialises the load-decide-save of the persisted push throttle. */
    private val mutex = Mutex()

    /**
     * Saves [bytes] (if valid and newer), then pushes complications and requests a tile update
     * within the throttle limits. Returns the saved snapshot, or null if nothing changed.
     */
    suspend fun receive(context: Context, bytes: ByteArray): Snapshot? = mutex.withLock {
        val app = context.applicationContext
        val saved = SnapshotStore(app).save(bytes) ?: return@withLock null
        val nowMs = System.currentTimeMillis()
        val pusher = ComplicationPusher.load(app)
        val decision = pusher.decide(statusOf(saved, nowMs).kind, nowMs)
        pusher.save(app)
        if (decision.complications) {
            for (service in listOf(NowComplicationService::class.java, NextHourComplicationService::class.java)) {
                ComplicationDataSourceUpdateRequester.create(app, ComponentName(app, service)).requestUpdateAll()
            }
        }
        if (decision.tile) TileService.getUpdater(app).requestUpdate(GlucoseTileService::class.java)
        saved
    }
}
