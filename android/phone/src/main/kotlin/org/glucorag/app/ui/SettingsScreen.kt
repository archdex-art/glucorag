package org.glucorag.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.glucorag.app.data.LocalDb
import org.glucorag.app.data.LocalProfile
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.Session
import org.glucorag.app.source.Simulation
import org.glucorag.app.sync.AlertNotifier
import org.glucorag.app.sync.Channels

private fun typeLabel(type: String) = if (type == "T1D") "Type 1" else "Type 2"

private fun sexLabel(gender: String) = if (gender == "F") "female" else "male"

@Composable
fun SettingsScreen(
    session: Session,
    profile: LocalProfile?,
    onBack: () -> Unit,
    onChangeSource: () -> Unit,
    onEditDetails: () -> Unit,
    onConnect: () -> Unit,
    onSignedOut: (keptOnPhone: Boolean) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val reading by LocalState.get(context).reading.collectAsState()
    val waiting by LocalDb.get(context).queue().observeCount().collectAsState(initial = 0)
    val watch = rememberWatchConnected()
    var confirmSignOut by remember { mutableStateOf(false) }
    var showLicence by remember { mutableStateOf(false) }
    var testMessage by remember { mutableStateOf<String?>(null) }

    fun signOut(keep: Boolean) = scope.launch {
        Account.signOut(context, keep)
        onSignedOut(keep)
    }

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        TextButton(onClick = onBack) { Text("Back") }
        Text("Settings", style = MaterialTheme.typography.headlineSmall)
        Sheet {
            SectionTitle("Account")
            if (session.localOnly) {
                Text("On this phone only")
                Hint("Forecasts and alerts run on this phone. Your readings and details stay here.")
                Button(onClick = onConnect) { Text("Connect to a GlucoRAG server") }
                Hint("Your readings from this phone then upload to the account, and your details go to it if it has none.")
            } else {
                Text(session.email ?: "Not signed in")
                session.server?.let { Hint("Server: ${hostOf(it)}") }
                if (session.token == null) Button(onClick = onConnect) { Text("Sign in again") }
            }
        }
        Sheet {
            SectionTitle("About you")
            if (profile == null) {
                Hint("Not entered yet. The forecast needs your details.")
            } else {
                Text("${typeLabel(profile.diabetesType)}, ${profile.age} years, ${sexLabel(profile.gender)}, BMI ${bmiText(profile.bmi)}")
            }
            Hint("Glucose unit: ${session.unit ?: "mg/dL"}.")
            OutlinedButton(onClick = onEditDetails) { Text(if (profile == null) "Enter your details" else "Edit your details") }
        }
        Sheet {
            SectionTitle("Readings")
            Text("Source: ${sourceName(reading?.from)}")
            OutlinedButton(onClick = onChangeSource) { Text("Set up the source") }
            Row(
                Modifier
                    .fillMaxWidth()
                    .toggleable(
                        value = session.simulated,
                        role = Role.Switch,
                        onValueChange = { on -> scope.launch { if (on) Simulation.start(context) else Simulation.stop(context) } },
                    ),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Simulated readings", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                Switch(checked = session.simulated, onCheckedChange = null)
            }
            Hint(
                "Made-up readings, not from a sensor: the last 3 hours, then one every 5 minutes." +
                    if (session.localOnly || session.server == null) " They stay on this phone." else " They upload to your account like real ones.",
            )
        }
        Sheet {
            SectionTitle("Watch")
            Text(watchLine(watch))
            OutlinedButton(onClick = {
                testMessage = if (Channels.canPost(context)) {
                    AlertNotifier(context).test()
                    "Test alert sent. It should also appear on your watch."
                } else {
                    "Notifications are off for GlucoRAG. Allow them in Keep readings flowing."
                }
            }) { Text("Send test alert") }
            testMessage?.let { Hint(it) }
        }
        Sheet {
            SectionTitle("Licences")
            Hint("The Atkinson Hyperlegible Next font is licensed under the SIL Open Font License 1.1.")
            TextButton(onClick = { showLicence = true }) { Text("Read the licence") }
        }
        if (!session.localOnly && (session.token != null || session.server != null)) {
            Button(onClick = { confirmSignOut = true }) { Text("Sign out") }
        }
        ResearchNotice()
    }

    if (confirmSignOut) {
        val unsent = if (waiting > 0) " ${if (waiting == 1) "1 reading hasn't" else "$waiting readings haven't"} uploaded yet." else ""
        AlertDialog(
            onDismissRequest = { confirmSignOut = false },
            title = { Text("Sign out?") },
            text = {
                Text(
                    "Keep your readings and details on this phone to go on using GlucoRAG without a server, " +
                        "or delete them from this phone. They stay in your CGM app either way.$unsent",
                )
            },
            confirmButton = {
                Column(horizontalAlignment = Alignment.End) {
                    Button(onClick = { confirmSignOut = false; signOut(keep = true) }) { Text("Keep on this phone") }
                    TextButton(onClick = { confirmSignOut = false; signOut(keep = false) }) { Text("Delete from this phone") }
                }
            },
            dismissButton = { TextButton(onClick = { confirmSignOut = false }) { Text("Cancel") } },
        )
    }
    if (showLicence) {
        val text = remember { context.assets.open("licenses/OFL.txt").bufferedReader().use { it.readText() } }
        AlertDialog(
            onDismissRequest = { showLicence = false },
            title = { Text("SIL Open Font License 1.1") },
            text = {
                Column(Modifier.heightIn(max = 400.dp).verticalScroll(rememberScrollState())) {
                    Text(text, style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = { TextButton(onClick = { showLicence = false }) { Text("Close") } },
        )
    }
}
