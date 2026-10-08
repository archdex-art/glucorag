package org.glucorag.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import org.glucorag.app.data.LocalDb
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.Session
import org.glucorag.app.data.SyncState
import org.glucorag.app.source.Simulation
import org.glucorag.app.sync.SyncWorker
import org.glucorag.shared.Snapshot
import org.glucorag.shared.StatusKind
import org.glucorag.shared.formatGlucose
import org.glucorag.shared.statusOf
import org.glucorag.shared.trendOf
import org.glucorag.shared.zoneOf

private const val OLD_MS = 15 * 60_000L

/** Whether a watch is connected over the Data Layer, refreshed every 30 s. */
@Composable
fun rememberWatchConnected(): Boolean? {
    val context = LocalContext.current
    var connected by remember { mutableStateOf<Boolean?>(null) }
    LaunchedEffect(Unit) {
        while (true) {
            connected = try {
                Wearable.getNodeClient(context).connectedNodes.await().isNotEmpty()
            } catch (e: Exception) {
                false
            }
            delay(30_000L)
        }
    }
    return connected
}

fun watchLine(connected: Boolean?) = when (connected) {
    true -> "Watch connected"
    false -> "No watch connected"
    null -> "Checking for a watch…"
}

@Composable
fun TodayScreen(session: Session, onSettings: () -> Unit, onSignIn: () -> Unit, onEnterDetails: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val local = LocalState.get(context)
    val snapshot by local.snapshot.collectAsState()
    val sync by local.sync.collectAsState()
    val waiting by LocalDb.get(context).queue().observeCount().collectAsState(initial = 0)
    val watch = rememberWatchConnected()
    val now = rememberNow()

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("GlucoRAG", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            TextButton(onClick = onSettings) { Text("Settings") }
        }
        if (session.simulated) {
            Sheet {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Simulated readings, not from a sensor", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    OutlinedButton(onClick = { scope.launch { Simulation.stop(context) } }) { Text("Stop") }
                }
            }
        }
        Sheet {
            Answer(snapshot, now)
            if (snapshot?.server?.state == "needs_setup") OutlinedButton(onClick = onEnterDetails) { Text("Enter your details") }
        }
        snapshot?.let { s ->
            Sheet {
                SectionTitle("The last 3 hours and the next hour")
                GlucoseChart(s, now, chartDescription(s, now))
                Hint(
                    "Line: your readings. Shaded: where your glucose is likely to be in the next hour. Lines at " +
                        "${formatGlucose(70.0, s.unit)} and ${formatGlucose(180.0, s.unit)} ${s.unit.label}.",
                )
            }
        }
        Sheet {
            SectionTitle("Phone and watch")
            if (session.localOnly) {
                Text("Forecasts run on this phone. No server connected.", style = MaterialTheme.typography.bodyMedium)
                Text(watchLine(watch), style = MaterialTheme.typography.bodyMedium)
            } else {
                Text(syncLine(sync, waiting, now), style = MaterialTheme.typography.bodyMedium)
                Text(watchLine(watch), style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    when (sync?.state) {
                        SyncState.SIGNED_OUT -> OutlinedButton(onClick = onSignIn) { Text("Sign in again") }
                        SyncState.NEEDS_SETUP -> OutlinedButton(onClick = onEnterDetails) { Text("Enter your details") }
                        else -> OutlinedButton(onClick = { SyncWorker.enqueue(context) }) { Text("Sync now") }
                    }
                    session.server?.let { server ->
                        TextButton(onClick = { openUrl(context, "$server/ui/history") }) { Text("Full history on the website") }
                    }
                }
            }
        }
        ResearchNotice()
    }
}

@Composable
private fun Answer(snapshot: Snapshot?, now: Long) {
    val c = LocalGr.current
    val status = statusOf(snapshot, now)
    val unit = snapshot?.unit ?: org.glucorag.shared.GlucoseUnit.MG_DL
    val urgentColor: Color? = when {
        !status.urgent -> null
        status.kind == StatusKind.LOW_NOW || status.kind == StatusKind.LOW_SOON -> c.zoneFill.getValue(org.glucorag.shared.Zone.LOW)
        else -> c.zoneFill.getValue(org.glucorag.shared.Zone.HIGH)
    }
    // The shared sentences speak from the watch; two of them need the phone's own words.
    val sentence = when (status.kind) {
        StatusKind.OPEN_PHONE -> "Enter your details to see your forecast"
        StatusKind.WAITING -> "Waiting for the first reading"
        else -> status.sentence
    }
    Text(
        sentence,
        style = MaterialTheme.typography.headlineSmall,
        color = if (urgentColor != null) Color(0xFF0E2742) else c.ink,
        modifier = Modifier
            .semantics { heading() }
            .then(if (urgentColor != null) Modifier.background(urgentColor, RoundedCornerShape(4.dp)).padding(horizontal = 10.dp, vertical = 4.dp) else Modifier),
    )
    val reading = snapshot?.now ?: return
    val old = now - reading.t >= OLD_MS
    val trend = trendOf(reading.rate)
    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            formatGlucose(reading.mgdl, unit),
            fontSize = 44.sp,
            style = MaterialTheme.typography.displaySmall,
            color = if (old) c.ink2 else c.zoneText.getValue(zoneOf(reading.mgdl)),
        )
        Text(unit.label, style = MaterialTheme.typography.bodyLarge, color = c.ink2, modifier = Modifier.padding(bottom = 8.dp))
        trend?.let { Text("${it.arrow} ${it.label}", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(bottom = 8.dp)) }
    }
    Text((if (old) "Old reading, " else "") + ageText(reading.t, now), style = MaterialTheme.typography.bodyMedium, color = c.ink2)
    val f = snapshot.forecast?.takeIf { now < it.t0 + 3_600_000L } ?: return
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
        for (h in listOf(30, 60)) {
            val i = f.horizons.indexOf(h)
            if (i < 0) continue
            Column {
                Text("In $h min", style = MaterialTheme.typography.labelMedium, color = c.ink2)
                Text(
                    "About ${formatGlucose(f.median[i], unit)} ${unit.label}",
                    style = MaterialTheme.typography.titleMedium,
                    color = c.zoneText.getValue(zoneOf(f.median[i])),
                )
                Text("Likely ${formatGlucose(f.low[i], unit)}–${formatGlucose(f.high[i], unit)}", style = MaterialTheme.typography.bodySmall, color = c.ink2)
            }
        }
    }
}

private fun chartDescription(s: Snapshot, now: Long): String {
    val reading = s.now ?: return "No readings in the last 3 hours."
    val f = s.forecast?.takeIf { now < it.t0 + 3_600_000L }
    val base = "Latest reading ${formatGlucose(reading.mgdl, s.unit)} ${s.unit.label}."
    return if (f == null) "$base No current forecast." else
        "$base In the next hour likely between ${formatGlucose(f.low.min(), s.unit)} and ${formatGlucose(f.high.max(), s.unit)} ${s.unit.label}."
}
