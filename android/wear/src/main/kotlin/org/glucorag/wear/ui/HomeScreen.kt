package org.glucorag.wear.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.wear.compose.foundation.lazy.ScalingLazyColumn
import androidx.wear.compose.foundation.lazy.ScalingLazyListScope
import androidx.wear.compose.foundation.lazy.rememberScalingLazyListState
import androidx.wear.compose.foundation.rotary.RotaryScrollableDefaults
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import org.glucorag.shared.Snapshot
import org.glucorag.shared.StatusKind
import org.glucorag.shared.Zone
import org.glucorag.shared.formatGlucose
import org.glucorag.shared.statusOf
import org.glucorag.shared.trendOf
import org.glucorag.shared.zoneOf

const val RESEARCH_NOTICE = "Research prototype. Not a medical device. Don't use it to make treatment decisions."

/**
 * The app's single screen, in spec §4 order: sentence, value with arrow and age, the 30/60-min
 * bands, the chart, the phone line, the research notice. In [ambient] it is text only, dimmed,
 * with the value in outline.
 */
@Composable
fun HomeScreen(snapshot: Snapshot?, nowMs: Long, phoneConnected: Boolean?, ambient: Boolean) {
    val listState = rememberScalingLazyListState()
    ScreenScaffold(scrollState = listState) { contentPadding ->
        ScalingLazyColumn(
            modifier = Modifier.fillMaxWidth(),
            state = listState,
            contentPadding = contentPadding,
            horizontalAlignment = Alignment.CenterHorizontally,
            // Explicit, though it is the default: the crown and bezel scroll the list.
            rotaryScrollableBehavior = RotaryScrollableDefaults.behavior(listState),
        ) {
            content(snapshot, nowMs, phoneConnected, ambient)
        }
    }
}

private fun ScalingLazyListScope.content(s: Snapshot?, nowMs: Long, phoneConnected: Boolean?, ambient: Boolean) {
    val status = statusOf(s, nowMs)
    val primary = if (ambient) Colors.Ink2 else Colors.Ink

    item {
        Text(
            status.sentence,
            style = MaterialTheme.typography.titleMedium,
            color = if (ambient) Colors.Ink2 else sentenceColor(status.kind),
            textAlign = TextAlign.Center,
        )
    }

    val now = s?.now
    if (s != null && now != null) {
        item {
            val old = isOld(s, nowMs)
            val color = when {
                ambient -> Colors.Ink2
                old -> Colors.Ink2
                else -> Colors.zoneText(zoneOf(now.mgdl))
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    formatGlucose(now.mgdl, s.unit) + (trendOf(now.rate)?.arrow ?: ""),
                    style = TextStyle(
                        fontSize = 44.sp,
                        fontWeight = FontWeight.Bold,
                        // Ambient: outline only, so few pixels are lit.
                        drawStyle = if (ambient) Stroke(width = 2f) else null,
                    ),
                    color = color,
                )
                Text(
                    if (old) "Old reading · ${ageText(now.t, nowMs)}" else ageText(now.t, nowMs),
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (old && !ambient) Colors.Ink else Colors.Ink2,
                )
            }
        }

        for (horizon in listOf(30, 60)) {
            val band = bandText(s, horizon, nowMs) ?: continue
            item { Text(band, style = MaterialTheme.typography.bodyMedium, color = primary) }
        }

        if (!ambient && s.recent.isNotEmpty()) {
            item {
                WearChart(
                    snapshot = s,
                    nowMs = nowMs,
                    modifier = Modifier.fillMaxWidth().height(96.dp).padding(horizontal = 8.dp),
                )
            }
        }
    }

    val phoneLine = when {
        phoneConnected == false -> "Phone not connected"
        s != null -> "Updated from phone ${ageText(s.written, nowMs)}"
        else -> null
    }
    if (phoneLine != null) {
        item {
            Text(phoneLine, style = MaterialTheme.typography.bodySmall, color = Colors.Ink2, textAlign = TextAlign.Center)
        }
    }

    item {
        Text(
            RESEARCH_NOTICE,
            style = MaterialTheme.typography.bodySmall,
            color = Colors.Ink2,
            textAlign = TextAlign.Center,
        )
    }
}

/** Low/high sentences take that zone's colour; everything else is ink. */
private fun sentenceColor(kind: StatusKind): Color = when (kind) {
    StatusKind.LOW_NOW, StatusKind.LOW_SOON -> Colors.zoneText(Zone.LOW)
    StatusKind.HIGH_NOW, StatusKind.HIGH_SOON -> Colors.zoneText(Zone.HIGH)
    else -> Colors.Ink
}
