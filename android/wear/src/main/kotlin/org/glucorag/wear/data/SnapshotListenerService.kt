package org.glucorag.wear.data

import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.WearableListenerService
import kotlinx.coroutines.runBlocking

/** Receives the phone's snapshot DataItem at [PATH]. */
class SnapshotListenerService : WearableListenerService() {
    override fun onDataChanged(dataEvents: DataEventBuffer) {
        // Copy the bytes out: the buffer is released when this returns.
        val payloads = dataEvents
            .filter { it.type == DataEvent.TYPE_CHANGED && it.dataItem.uri.path == PATH }
            .mapNotNull { it.dataItem.data }
        if (payloads.isEmpty()) return
        // onDataChanged runs on a background thread; blocking keeps the service alive until saved.
        runBlocking {
            for (bytes in payloads) SnapshotSync.receive(this@SnapshotListenerService, bytes)
        }
    }

    companion object {
        const val PATH = "/glucorag/snapshot"
    }
}
