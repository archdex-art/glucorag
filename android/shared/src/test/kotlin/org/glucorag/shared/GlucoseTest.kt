package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class GlucoseTest {
    @Test
    fun formatsMmolWithOneDecimal() {
        assertEquals("3.9", formatGlucose(70.0, GlucoseUnit.MMOL_L))
        assertEquals("10.0", formatGlucose(180.0, GlucoseUnit.MMOL_L))
    }

    @Test
    fun neverFormatsNegativeZero() {
        assertEquals("0.0", formatGlucose(-0.04, GlucoseUnit.MMOL_L))
        assertEquals("0", formatGlucose(-0.4, GlucoseUnit.MG_DL))
    }

    @Test
    fun formatsMgDlAsWholeNumber() {
        assertEquals("142", formatGlucose(142.4, GlucoseUnit.MG_DL))
        assertEquals("143", formatGlucose(142.5, GlucoseUnit.MG_DL))
    }

    @Test
    fun parsesUnitLabels() {
        assertEquals(GlucoseUnit.MG_DL, GlucoseUnit.parse("mg/dL"))
        assertEquals(GlucoseUnit.MMOL_L, GlucoseUnit.parse("mmol/L"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsUnknownUnit() {
        GlucoseUnit.parse("mg")
    }

    @Test
    fun zonesUseWebsiteBoundaries() {
        assertEquals(Zone.VERY_LOW, zoneOf(53.9))
        assertEquals(Zone.LOW, zoneOf(54.0))
        assertEquals(Zone.LOW, zoneOf(69.9))
        assertEquals(Zone.TARGET, zoneOf(70.0))
        assertEquals(Zone.TARGET, zoneOf(180.0))
        assertEquals(Zone.HIGH, zoneOf(180.1))
        assertEquals(Zone.HIGH, zoneOf(250.0))
        assertEquals(Zone.VERY_HIGH, zoneOf(250.1))
    }

    @Test
    fun trendBands() {
        assertEquals(Trend.RISING, trendOf(2.0))
        assertEquals(Trend.RISING_QUICKLY, trendOf(2.01))
        assertEquals(Trend.STEADY, trendOf(1.0))
        assertEquals(Trend.RISING, trendOf(1.01))
        assertEquals(Trend.STEADY, trendOf(-1.0))
        assertEquals(Trend.FALLING, trendOf(-1.01))
        assertEquals(Trend.FALLING, trendOf(-2.0))
        assertEquals(Trend.FALLING_QUICKLY, trendOf(-2.01))
        assertNull(trendOf(Double.NaN))
        assertNull(trendOf(null))
    }

    @Test
    fun trendLabelsMatchWebsite() {
        assertEquals("rising quickly", Trend.RISING_QUICKLY.label)
        assertEquals("steady", Trend.STEADY.label)
        assertEquals("falling quickly", Trend.FALLING_QUICKLY.label)
    }
}
