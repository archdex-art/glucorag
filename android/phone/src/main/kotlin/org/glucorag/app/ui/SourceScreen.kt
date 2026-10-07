package org.glucorag.app.ui

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.net.toUri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.glucorag.app.data.LocalState
import org.glucorag.app.source.SimulatedFeed
import org.glucorag.app.source.Simulation
import org.glucorag.app.sync.AlertNotifier
import org.glucorag.app.sync.Channels
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Zone
import org.glucorag.shared.formatGlucose

const val APP_ID = "org.glucorag.app"

/** A CGM app that shares its readings with GlucoRAG, and where to get it. */
private class CgmApp(val name: String, val pkg: String, val store: List<String>, val steps: List<String>)

private val CGM_APPS = listOf(
    CgmApp(
        "Juggluco", "tk.glucodata",
        listOf("market://details?id=tk.glucodata", "https://play.google.com/store/apps/details?id=tk.glucodata"),
        listOf("Open Juggluco, then Settings.", "Under Glucodata broadcast, tick $APP_ID.", "Save."),
    ),
    CgmApp(
        "xDrip+", "com.eveningoutpost.dexdrip",
        listOf("https://github.com/NightscoutFoundation/xDrip/releases"),
        listOf(
            "Open xDrip+, then Settings, then Inter-app settings.",
            "Turn on Broadcast locally.",
            "Set Identify receiver to $APP_ID.",
            "Keep Compatible Broadcast on.",
        ),
    ),
)

private const val ARRIVED_MS = 1_500L

private fun installed(context: Context, pkg: String) = try {
    context.packageManager.getPackageInfo(pkg, 0)
    true
} catch (e: PackageManager.NameNotFoundException) {
    false
}

/** Copies this app's ID for pasting into the CGM app (Android 13+ confirms copies itself). */
private fun copyAppId(context: Context) {
    context.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("GlucoRAG app ID", APP_ID))
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) Toast.makeText(context, "App ID copied", Toast.LENGTH_SHORT).show()
}

private fun openApp(context: Context, app: CgmApp) {
    copyAppId(context)
    context.packageManager.getLaunchIntentForPackage(app.pkg)?.let { context.startActivity(it) }
}

/** The app store page, or the download page when there is no store app. */
private fun getApp(context: Context, app: CgmApp) {
    for (url in app.store) {
        try {
            context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))
            return
        } catch (e: ActivityNotFoundException) {
            // No store app: try the next address.
        }
    }
}

@Composable
private fun Steps(app: CgmApp) {
    app.steps.forEachIndexed { i, s -> Text("${i + 1}. $s", style = MaterialTheme.typography.bodyMedium) }
}

@Composable
private fun InstalledCard(app: CgmApp) {
    val context = LocalContext.current
    Sheet {
        SectionTitle(app.name)
        Hint("Installed on this phone. Open it and paste the app ID where the steps say $APP_ID.")
        Steps(app)
        Button(onClick = { openApp(context, app) }) { Text("Open ${app.name}") }
    }
}

@Composable
private fun NotInstalledCard(app: CgmApp) {
    val context = LocalContext.current
    Sheet {
        SectionTitle(app.name)
        Hint("Not installed on this phone. After installing it, set it up with your sensor, then:")
        Steps(app)
        OutlinedButton(onClick = { getApp(context, app) }) { Text("Get ${app.name}") }
    }
}

/**
 * Which CGM app sends readings, and a live check that they arrive: the first new reading moves on
 * by itself after [ARRIVED_MS]. Installed apps are re-checked on every resume ([resumeTick]).
 */
@Composable
fun SourceScreen(unit: GlucoseUnit, simulated: Boolean, resumeTick: Int, onContinue: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val reading by LocalState.get(context).reading.collectAsState()
    val present = remember(resumeTick) { CGM_APPS.filter { installed(context, it.pkg) } }
    val missing = CGM_APPS - present.toSet()
    var showMissing by rememberSaveable { mutableStateOf(false) }
    // Only a reading newer than the one already shown on arrival counts as the live check passing.
    val shownOnArrival = rememberSaveable { reading?.t ?: Long.MIN_VALUE }
    var arrived by remember { mutableStateOf(false) }

    LaunchedEffect(reading) {
        val r = reading ?: return@LaunchedEffect
        if (r.t <= shownOnArrival) return@LaunchedEffect
        arrived = true
        // A backfill delivers many readings at once: each restarts the wait, so it ends after the last.
        delay(ARRIVED_MS)
        onContinue()
    }

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Where your readings come from", style = MaterialTheme.typography.headlineSmall)
        Hint("GlucoRAG reads the readings that Juggluco or xDrip+ share with other apps. Using only the official Libre or Dexcom app? Add Juggluco or xDrip+; both read the same sensors.")
        present.forEach { InstalledCard(it) }
        if (present.isEmpty()) {
            Sheet {
                SectionTitle("Get a CGM app")
                Hint("Neither Juggluco nor xDrip+ is on this phone. Install one and set it up with your sensor, then come back here.")
                missing.forEach { app ->
                    OutlinedButton(onClick = { getApp(context, app) }) { Text("Get ${app.name}") }
                }
                TextButton(onClick = { showMissing = !showMissing }) { Text(if (showMissing) "Hide the steps" else "Show the steps") }
            }
            if (showMissing) missing.forEach { NotInstalledCard(it) }
        } else if (missing.isNotEmpty()) {
            TextButton(onClick = { showMissing = !showMissing }) {
                Text(if (showMissing) "Hide other apps" else "Use ${missing.joinToString(" or ") { it.name }} instead")
            }
            if (showMissing) missing.forEach { NotInstalledCard(it) }
        }
        Sheet {
            SectionTitle("No sensor at hand?")
            if (simulated) {
                Hint("Simulated readings are on. Turn them off in Settings or on Today.")
            } else {
                Hint("Try GlucoRAG with simulated readings: the last 3 hours at once, then one every 5 minutes. They upload to your account like real readings, so you see a forecast and alerts. Stop them any time.")
                OutlinedButton(onClick = { scope.launch { Simulation.start(context) } }) { Text("Try with simulated readings") }
            }
        }
        Sheet {
            SectionTitle("Live check")
            val r = reading
            Text(
                when {
                    r == null -> "Waiting for the first reading…"
                    arrived && r.from == SimulatedFeed.FROM -> "Receiving simulated readings"
                    arrived -> "Receiving readings from ${sourceName(r.from)}"
                    else -> "Receiving: ${formatGlucose(r.mgdl, unit)} ${unit.label} at ${clockText(r.t)}"
                },
                style = MaterialTheme.typography.bodyLarge,
                color = if (arrived) LocalGr.current.zoneText.getValue(Zone.TARGET) else MaterialTheme.colorScheme.onSurface,
            )
            Button(onClick = onContinue, enabled = r != null) { Text("Continue") }
            TextButton(onClick = onContinue) { Text("Skip for now") }
        }
        ResearchNotice()
    }
}

private const val CHECKLIST_PREFS = "checklist"

/** Opens Samsung's "Never sleeping apps" list; elsewhere, this app's settings. */
private fun openNeverSleeping(context: Context) {
    val samsung = Intent("com.samsung.android.sm.ACTION_OPEN_CHECKABLE_LISTACTIVITY")
        .setPackage("com.samsung.android.lool")
        .putExtra("activity_type", 2)
    try {
        context.startActivity(samsung)
    } catch (e: ActivityNotFoundException) {
        openAppDetails(context)
    } catch (e: SecurityException) {
        openAppDetails(context)
    }
}

private fun openAppDetails(context: Context) {
    context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, "package:${context.packageName}".toUri()))
}

@Composable
private fun ChecklistItem(title: String, text: String, done: Boolean?, onConfirm: ((Boolean) -> Unit)?, action: @Composable () -> Unit) {
    Sheet {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (onConfirm != null) Checkbox(checked = done == true, onCheckedChange = onConfirm)
            Column {
                SectionTitle(title)
                if (onConfirm == null && done != null) Hint(if (done) "Done." else "Not done yet.")
            }
        }
        Hint(text)
        action()
    }
}

/** The settings that decide whether readings keep flowing and alerts reach the watch. */
@Composable
fun ChecklistScreen(onDone: () -> Unit, resumeTick: Int) {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences(CHECKLIST_PREFS, Context.MODE_PRIVATE) }
    fun confirmed(key: String) = prefs.getBoolean(key, false)
    var sleeping by remember { mutableStateOf(confirmed("never_sleeping")) }
    var wearable by remember { mutableStateOf(confirmed("wearable_notifications")) }
    var watch by remember { mutableStateOf(confirmed("watch_installed")) }
    var notifications by remember(resumeTick) { mutableStateOf(Channels.canPost(context)) }
    val battery = remember(resumeTick) {
        context.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(context.packageName)
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { notifications = Channels.canPost(context) }

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Keep readings flowing", style = MaterialTheme.typography.headlineSmall)
        Hint("Phones put background apps to sleep. These settings keep uploads and alerts working.")
        ChecklistItem("Notifications", "Lets GlucoRAG warn you when a low or high is predicted.", notifications, null) {
            if (!notifications) {
                Button(onClick = {
                    val ask = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                    if (ask) {
                        permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
                    }
                }) { Text("Allow notifications") }
            }
        }
        ChecklistItem(
            "Never sleeping apps",
            "On Samsung phones, add GlucoRAG to Never sleeping apps so it keeps receiving readings.",
            sleeping,
            { sleeping = it; prefs.edit { putBoolean("never_sleeping", it) } },
        ) { OutlinedButton(onClick = { openNeverSleeping(context) }) { Text("Open battery settings") } }
        ChecklistItem("Battery: Unrestricted", "In this app's battery settings, choose Unrestricted.", battery, null) {
            if (!battery) OutlinedButton(onClick = { openAppDetails(context) }) { Text("Open app settings") }
        }
        ChecklistItem(
            "Watch notifications",
            "In Galaxy Wearable, open Notifications, then App notifications, and make sure GlucoRAG is on. Turn on Show while using phone so alerts reach the watch while you use the phone.",
            wearable,
            { wearable = it; prefs.edit { putBoolean("wearable_notifications", it) } },
        ) { OutlinedButton(onClick = { AlertNotifier(context).test() }) { Text("Send test alert") } }
        ChecklistItem(
            "Install on watch",
            "Install the GlucoRAG watch app from your computer (see the setup guide in android/README.md), then add the GlucoRAG complications to your watch face.",
            watch,
            { watch = it; prefs.edit { putBoolean("watch_installed", it) } },
        ) {}
        Button(onClick = onDone) { Text("Done") }
        ResearchNotice()
    }
}
