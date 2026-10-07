package org.glucorag.app.sync

import org.glucorag.shared.CgmReading
import org.glucorag.shared.Now
import org.glucorag.shared.Snapshot

/**
 * [snapshot] updated with a newer CGM [reading] received on this phone: `now` and the end of
 * `recent` change, the server's forecast and state stay. An older reading changes nothing.
 */
fun withReading(snapshot: Snapshot, reading: CgmReading, nowMs: Long): Snapshot {
    val current = snapshot.now
    if (current != null && reading.t <= current.t) return snapshot
    val recent = (snapshot.recent + listOf(listOf(reading.t.toDouble(), reading.mgdl))).takeLast(SyncEngine.RECENT_POINTS)
    return snapshot.copy(
        now = Now(reading.t, reading.mgdl, reading.ratePerMin, reading.from),
        recent = recent,
        written = nowMs,
    )
}
