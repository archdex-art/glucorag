package org.glucorag.wear.ui

import androidx.compose.ui.graphics.Color
import org.glucorag.shared.Zone

/** Dark-scheme values from `web/src/styles/tokens.css`, drawn on pure black. */
object Colors {
    val Background = Color(0xFF000000)
    val Ink = Color(0xFFE6EDF5)
    val Ink2 = Color(0xFFA7B8CB)

    /** Forecast band (`--p-mid`) and median (`--p-median`). */
    val BandFill = Color(0xFF284A72)
    val BandMedian = Color(0xFFE6EDF5)

    /** Target range behind the chart (`--zone-target-tint`). */
    val TargetTint = Color(0xFF132A2F)

    fun zoneText(zone: Zone): Color = when (zone) {
        Zone.VERY_LOW -> Color(0xFFFF9A94)
        Zone.LOW -> Color(0xFFFFA49B)
        Zone.TARGET -> Color(0xFF8FDCA6)
        Zone.HIGH -> Color(0xFFF2D27A)
        Zone.VERY_HIGH -> Color(0xFFFFB988)
    }

    fun zoneFill(zone: Zone): Color = when (zone) {
        Zone.VERY_LOW -> Color(0xFFE0605C)
        Zone.LOW -> Color(0xFFF07A6E)
        Zone.TARGET -> Color(0xFF5CC27A)
        Zone.HIGH -> Color(0xFFE8C24A)
        Zone.VERY_HIGH -> Color(0xFFF09A5A)
    }
}
