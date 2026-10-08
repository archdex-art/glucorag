package org.glucorag.wear.tile

import android.content.ComponentName
import androidx.compose.ui.graphics.toArgb
import androidx.wear.protolayout.ActionBuilders
import androidx.wear.protolayout.LayoutElementBuilders.LayoutElement
import androidx.wear.protolayout.TimelineBuilders.Timeline
import androidx.wear.protolayout.layout.column
import androidx.wear.protolayout.material3.MaterialScope
import androidx.wear.protolayout.material3.Typography
import androidx.wear.protolayout.material3.primaryLayout
import androidx.wear.protolayout.material3.text
import androidx.wear.protolayout.modifiers.clickable
import androidx.wear.protolayout.types.LayoutColor
import androidx.wear.protolayout.types.LayoutString
import androidx.wear.tiles.Material3TileService
import androidx.wear.tiles.RequestBuilders.TileRequest
import androidx.wear.tiles.TileBuilders.Tile
import org.glucorag.shared.Snapshot
import org.glucorag.shared.formatGlucose
import org.glucorag.shared.statusOf
import org.glucorag.shared.trendOf
import org.glucorag.shared.zoneOf
import org.glucorag.wear.data.SnapshotStore
import org.glucorag.wear.ui.Colors
import org.glucorag.wear.ui.MainActivity
import org.glucorag.wear.ui.bandText
import org.glucorag.wear.ui.clockTime
import org.glucorag.wear.ui.isOld

/**
 * The glucose tile: sentence, value + arrow, "at 14:05" (absolute, since the tile doesn't advance
 * between updates) and the 60-min band. Updated on snapshot change,
 * at most once a minute (see `ComplicationPusher`).
 */
class GlucoseTileService : Material3TileService() {
    override suspend fun MaterialScope.tileResponse(requestParams: TileRequest): Tile {
        val snapshot = SnapshotStore(this@GlucoseTileService).latest()
        val nowMs = System.currentTimeMillis()
        val open = clickable(
            ActionBuilders.launchAction(ComponentName(this@GlucoseTileService, MainActivity::class.java)),
            "open_app",
        )
        val layout = primaryLayout(
            mainSlot = { column(*lines(snapshot, nowMs).toTypedArray()) },
            onClick = open,
        )
        // Re-rendered every minute: "in N min", staleness and forecast expiry are relative to now.
        return Tile.Builder()
            .setResourcesVersion(RESOURCES_VERSION)
            .setFreshnessIntervalMillis(FRESHNESS_MS)
            .setTileTimeline(Timeline.fromLayoutElement(layout))
            .build()
    }

    private fun MaterialScope.lines(s: Snapshot?, nowMs: Long): List<LayoutElement> {
        val status = statusOf(s, nowMs)
        val lines = mutableListOf(
            text(LayoutString(status.sentence), typography = Typography.BODY_MEDIUM, maxLines = 2),
        )
        val now = s?.now
        if (s != null && now != null) {
            val value = formatGlucose(now.mgdl, s.unit) + (trendOf(now.rate)?.arrow ?: "")
            val color = if (isOld(s, nowMs)) Colors.Ink2 else Colors.zoneText(zoneOf(now.mgdl))
            lines += text(LayoutString(value), typography = Typography.DISPLAY_SMALL, color = LayoutColor(color.toArgb()))
            lines += text(LayoutString("at ${clockTime(now.t)}"), typography = Typography.BODY_SMALL)
            bandText(s, 60, nowMs)?.let { lines += text(LayoutString(it), typography = Typography.BODY_SMALL) }
        }
        return lines
    }

    private companion object {
        const val RESOURCES_VERSION = "1"
        const val FRESHNESS_MS = 60_000L
    }
}
