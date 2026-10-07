package org.glucorag.wear.data

import com.google.android.gms.wearable.DataMap
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Now
import org.glucorag.shared.Server
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SnapshotPayloadTest {
    private val snapshot = Snapshot(
        v = 1, unit = GlucoseUnit.MG_DL, now = Now(1_000L, 142.0, 0.4, "juggluco"),
        recent = emptyList(), forecast = null, risk = null, server = Server("ok", 1_000L), written = 1_001L,
    )

    /** The phone wraps the encoded snapshot in a DataMap; the watch must unwrap it, not decode the map. */
    @Test
    fun snapshotIsReadFromTheDataMapKeyThePhoneWrites() {
        val map = DataMap().apply { putByteArray(SnapshotCodec.DATA_KEY, SnapshotCodec.encode(snapshot)) }
        val bytes = snapshotPayload(map)
        assertEquals(snapshot, SnapshotCodec.decode(bytes!!))
    }

    @Test
    fun dataMapWithoutTheKeyHasNoPayload() {
        assertNull(snapshotPayload(DataMap()))
    }
}
