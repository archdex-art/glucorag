package org.glucorag.app.sync

import org.glucorag.shared.GlucoseUnit
import org.junit.Assert.assertEquals
import org.junit.Test

class AlertTextTest {
    private val now = 1_759_737_600_000L
    private val min = 60_000L

    @Test
    fun saysWhenAndHowFarInTheAccountUnit() {
        assertEquals(
            "Low likely in about 25 min (could reach 66 mg/dL).",
            AlertNotifier.title(true, now + 24 * min + 1, 66.2, GlucoseUnit.MG_DL, now),
        )
        assertEquals(
            "High likely in about 45 min (could reach 11.4 mmol/L).",
            AlertNotifier.title(false, now + 45 * min, 205.0, GlucoseUnit.MMOL_L, now),
        )
        assertEquals("Low likely soon (could reach 60 mg/dL).", AlertNotifier.title(true, now, 60.0, GlucoseUnit.MG_DL, now))
    }
}
