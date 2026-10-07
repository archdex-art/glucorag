package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SnapshotTest {
    private val specExample = """
        {
          "v": 1,
          "unit": "mmol/L",
          "now": {"t": 1759738800000, "mgdl": 142.0, "rate": 0.4, "from": "juggluco"},
          "recent": [[1759728000000, 128.0]],
          "forecast": {"t0": 1759738500000, "horizons": [15, 30, 45, 60],
                       "median": [145, 150, 154, 157], "low": [139, 140, 140, 139], "high": [152, 161, 170, 178]},
          "risk": {"type": "hyper", "at": 1759740300000, "severity": "medium"},
          "server": {"state": "ok", "since": 1759738810000},
          "written": 1759738811000
        }
    """.trimIndent()

    private val expected = Snapshot(
        v = 1,
        unit = GlucoseUnit.MMOL_L,
        now = Now(t = 1759738800000, mgdl = 142.0, rate = 0.4, from = "juggluco"),
        recent = listOf(listOf(1759728000000.0, 128.0)),
        forecast = Forecast(
            t0 = 1759738500000,
            horizons = listOf(15, 30, 45, 60),
            median = listOf(145.0, 150.0, 154.0, 157.0),
            low = listOf(139.0, 140.0, 140.0, 139.0),
            high = listOf(152.0, 161.0, 170.0, 178.0),
        ),
        risk = Risk(type = "hyper", at = 1759740300000, severity = "medium"),
        server = Server(state = "ok", since = 1759738810000),
        written = 1759738811000,
    )

    @Test
    fun decodesSpecExample() {
        assertEquals(expected, SnapshotCodec.decode(specExample.encodeToByteArray()))
    }

    @Test
    fun roundTripsSpecExample() {
        assertEquals(expected, SnapshotCodec.decode(SnapshotCodec.encode(expected)))
    }

    @Test
    fun roundTripsNullsAndOmitsThem() {
        val bare = expected.copy(now = null, forecast = null, risk = null, recent = emptyList())
        val bytes = SnapshotCodec.encode(bare)
        assertEquals(bare, SnapshotCodec.decode(bytes))
        assertTrue(!bytes.decodeToString().contains("null"))
    }

    @Test
    fun fullSnapshotWithThirtySevenPointsFitsInTwoKilobytes() {
        val t = 1759738812345L
        val full = expected.copy(
            now = Now(t = t, mgdl = 142.123456, rate = -1.23456789, from = "xdrip"),
            recent = (0 until 37).map { i -> listOf((t - i * 300_123L).toDouble(), 100.0 + i * 3.14159) },
            forecast = expected.forecast!!.copy(
                t0 = t,
                median = listOf(145.123, 150.456, 154.789, 157.012),
                low = listOf(139.345, 140.678, 140.901, 139.234),
                high = listOf(152.567, 161.890, 170.123, 178.456),
            ),
            risk = Risk(type = "hypo", at = t + 1_800_000, severity = "high"),
            server = Server(state = "unreachable", since = t),
            written = t,
        )
        val bytes = SnapshotCodec.encode(full)
        assertTrue("${bytes.size} bytes", bytes.size < 2048)
        assertEquals(full, SnapshotCodec.decode(bytes))
    }

    @Test
    fun ignoresUnknownKeys() {
        val withExtra = specExample.replace("\"v\": 1,", "\"v\": 1, \"extra\": {\"a\": [1]},")
        assertEquals(expected, SnapshotCodec.decode(withExtra.encodeToByteArray()))
    }

    @Test
    fun rejectsOtherVersionsAndGarbage() {
        assertNull(SnapshotCodec.decode("""{"v":2}""".encodeToByteArray()))
        assertNull(SnapshotCodec.decode(specExample.replace("\"v\": 1", "\"v\": 2").encodeToByteArray()))
        assertNull(SnapshotCodec.decode("not json".encodeToByteArray()))
        assertNull(SnapshotCodec.decode(byteArrayOf(0x00, 0xFF.toByte(), 0x7B)))
        assertNull(SnapshotCodec.decode("[]".encodeToByteArray()))
        assertNull(SnapshotCodec.decode(specExample.replace("mmol/L", "mg").encodeToByteArray()))
    }
}
