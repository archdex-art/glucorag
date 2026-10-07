package org.glucorag.app.ui

import org.glucorag.shared.GlucoseUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MeasuresTest {
    @Test
    fun metricBmiToOneDecimal() {
        assertEquals(22.9, bmiMetric(175.0, 70.0)!!, 0.0)
        assertEquals(27.2, bmiMetric(182.0, 90.0)!!, 0.0)
    }

    @Test
    fun metricBmiNeedsBothPositiveValues() {
        assertNull(bmiMetric(null, 70.0))
        assertNull(bmiMetric(175.0, null))
        assertNull(bmiMetric(0.0, 70.0))
        assertNull(bmiMetric(175.0, -1.0))
        assertNull(bmiMetric(Double.NaN, 70.0))
    }

    @Test
    fun imperialMatchesMetric() {
        // 5 ft 9 in = 175.26 cm; 154 lb = 69.85 kg.
        assertEquals(22.7, bmiImperial(5.0, 9.0, 154.0)!!, 0.0)
        assertEquals(bmiMetric(feetInchesToCm(5.0, 9.0), poundsToKg(154.0)), bmiImperial(5.0, 9.0, 154.0))
        // Missing inches count as zero; a missing weight gives nothing.
        assertEquals(bmiImperial(6.0, 0.0, 180.0), bmiImperial(6.0, null, 180.0))
        assertNull(bmiImperial(5.0, 9.0, null))
        assertNull(bmiImperial(-1.0, 9.0, 154.0))
    }

    @Test
    fun conversionsAreExact() {
        assertEquals(175.26, feetInchesToCm(5.0, 9.0), 1e-9)
        assertEquals(2.54, feetInchesToCm(0.0, 1.0), 1e-12)
        assertEquals(0.45359237, poundsToKg(1.0), 1e-12)
        assertEquals(68.0388555, poundsToKg(150.0), 1e-7)
    }

    @Test
    fun rangeIsTheServers() {
        assertTrue(bmiInRange(10.0))
        assertTrue(bmiInRange(80.0))
        assertFalse(bmiInRange(9.9))
        assertFalse(bmiInRange(80.1))
        assertFalse(bmiInRange(null))
    }

    @Test
    fun numbersParseInAnyLocale() {
        assertEquals(23.5, parseNumber("23,5")!!, 0.0)
        assertEquals(23.5, parseNumber(" 23.5 ")!!, 0.0)
        assertNull(parseNumber(""))
        assertNull(parseNumber("abc"))
        assertNull(parseNumber("NaN"))
    }

    @Test
    fun bmiTextDropsATrailingZero() {
        assertEquals("23", bmiText(23.0))
        assertEquals("23.4", bmiText(23.4))
    }

    @Test
    fun measureSystemFollowsTheRegion() {
        assertTrue(usesImperial("US"))
        assertTrue(usesImperial("lr"))
        assertTrue(usesImperial("MM"))
        assertFalse(usesImperial("GB"))
        assertFalse(usesImperial("IN"))
        assertFalse(usesImperial(""))
        assertFalse(usesImperial(null))
    }

    @Test
    fun glucoseUnitFollowsTheRegion() {
        assertEquals(GlucoseUnit.MG_DL, defaultGlucoseUnit("US"))
        assertEquals(GlucoseUnit.MG_DL, defaultGlucoseUnit("IN"))
        assertEquals(GlucoseUnit.MG_DL, defaultGlucoseUnit("jp"))
        assertEquals(GlucoseUnit.MMOL_L, defaultGlucoseUnit("GB"))
        assertEquals(GlucoseUnit.MMOL_L, defaultGlucoseUnit("CN"))
        assertEquals(GlucoseUnit.MMOL_L, defaultGlucoseUnit("AU"))
        assertEquals(GlucoseUnit.MMOL_L, defaultGlucoseUnit(""))
        assertEquals(GlucoseUnit.MMOL_L, defaultGlucoseUnit(null))
    }
}
