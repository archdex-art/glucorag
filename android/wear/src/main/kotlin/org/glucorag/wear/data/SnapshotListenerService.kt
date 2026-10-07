package org.glucorag.wear.data

import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.WearableListenerService
import kotlinx.coroutines.runBlocking
import org.glucorag.shared.SnapshotCodec

/** Receives the phone's snapshot DataItem at [SnapshotCodec.PATH]. */
class SnapshotListenerService : WearableListenerService() {
    override fun onDataChanged(dataEvents: DataEventBuffer) {
        // Copy the payloads out: the buffer is released when this returns.
        val payloads = dataEvents
            .filter { it.type == DataEvent.TYPE_CHANGED && it.dataItem.uri.path == SnapshotCodec.PATH }
            .mapNotNull { snapshotPayload(DataMapItem.fromDataItem(it.dataItem).dataMap) }
        if (payloads.isEmpty()) return
        // onDataChanged runs on a background thread; blocking keeps the service alive until saved.
        runBlocking {
            for (bytes in payloads) SnapshotSync.receive(this@SnapshotListenerService, bytes)
        }
    }
}
