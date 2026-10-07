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
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.QueueDb
import org.glucorag.app.data.Session
import org.glucorag.app.source.Simulation
import org.glucorag.app.sync.AlertNotifier
import org.glucorag.app.sync.Channels

@Composable
fun SettingsScreen(session: Session, onBack: () -> Unit, onChangeSource: () -> Unit, onSignedOut: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val reading by LocalState.get(context).reading.collectAsState()
    val waiting by QueueDb.get(context).queue().observeCount().collectAsState(initial = 0)
    val watch = rememberWatchConnected()
    var confirmSignOut by remember { mutableStateOf(false) }
    var showLicence by remember { mutableStateOf(false) }
    var testMessage by remember { mutableStateOf<String?>(null) }

    fun signOut() = scope.launch {
        Account.signOut(context)
        onSignedOut()
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
            Text(session.email ?: "Not signed in")
            Hint("Server: ${session.server ?: "not set"}")
            Hint("Unit: ${session.unit ?: "mg/dL"}. Change it in Settings on the website.")
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
            Hint("Made-up readings, not from a sensor: the last 3 hours, then one every 5 minutes. They upload to your account like real ones.")
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
        Button(onClick = { if (waiting > 0) confirmSignOut = true else signOut() }) { Text("Sign out") }
        ResearchNotice()
    }

    if (confirmSignOut) {
        AlertDialog(
            onDismissRequest = { confirmSignOut = false },
            title = { Text("Sign out?") },
            text = { Text("$waiting ${if (waiting == 1) "reading hasn't" else "readings haven't"} uploaded yet and will be deleted from this phone. They stay in your CGM app.") },
            confirmButton = { Button(onClick = { confirmSignOut = false; signOut() }) { Text("Sign out") } },
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
