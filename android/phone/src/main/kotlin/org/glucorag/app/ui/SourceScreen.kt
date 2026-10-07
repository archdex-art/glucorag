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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import org.glucorag.app.data.LocalState
import org.glucorag.app.sync.AlertNotifier
import org.glucorag.app.sync.Channels
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.formatGlucose

const val APP_ID = "org.glucorag.app"

private fun installed(context: Context, pkg: String) = try {
    context.packageManager.getPackageInfo(pkg, 0)
    true
} catch (e: PackageManager.NameNotFoundException) {
    false
}

private fun copyAppId(context: Context) {
    context.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("GlucoRAG app ID", APP_ID))
}

@Composable
private fun SourceCard(name: String, pkg: String, steps: List<String>) {
    val context = LocalContext.current
    Sheet {
        SectionTitle(name)
        Hint(if (installed(context, pkg)) "Installed on this phone." else "Not installed on this phone.")
        steps.forEachIndexed { i, s -> Text("${i + 1}. $s", style = MaterialTheme.typography.bodyMedium) }
        OutlinedButton(onClick = { copyAppId(context) }) { Text("Copy app ID") }
    }
}

/** Which CGM app sends readings, and a live check that they arrive. */
@Composable
fun SourceScreen(unit: GlucoseUnit, onContinue: () -> Unit) {
    val context = LocalContext.current
    val reading by LocalState.get(context).reading.collectAsState()
    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Where your readings come from", style = MaterialTheme.typography.headlineSmall)
        Hint("GlucoRAG reads the readings that Juggluco or xDrip+ share with other apps. Using only the official Libre or Dexcom app? Add Juggluco or xDrip+; both read the same sensors.")
        SourceCard(
            "Juggluco", "tk.glucodata",
            listOf("Open Juggluco, then Settings.", "Under Glucodata broadcast, tick $APP_ID.", "Save."),
        )
        SourceCard(
            "xDrip+", "com.eveningoutpost.dexdrip",
            listOf(
                "Open xDrip+, then Settings, then Inter-app settings.",
                "Turn on Broadcast locally.",
                "Set Identify receiver to $APP_ID.",
                "Keep Compatible Broadcast on.",
            ),
        )
        Sheet {
            SectionTitle("Live check")
            val r = reading
            Text(
                if (r == null) "Waiting for the first reading…"
                else "Receiving: ${formatGlucose(r.mgdl, unit)} ${unit.label} at ${clockText(r.t)}",
                style = MaterialTheme.typography.bodyLarge,
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
