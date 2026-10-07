package org.glucorag.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.glucorag.shared.ServerUrlCheck
import org.glucorag.shared.checkServerUrl

/** Server address, check, sign in. [onSignedIn] gets whether the account has a profile. */
@Composable
fun ConnectScreen(initialServer: String?, onSignedIn: (hasProfile: Boolean) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var server by remember { mutableStateOf(initialServer ?: "") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var serverMessage by remember { mutableStateOf<Account.Result?>(null) }
    var signInError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("GlucoRAG", style = MaterialTheme.typography.headlineSmall)
        Hint("Connect this phone to your GlucoRAG server. Readings from your CGM app upload here, and your watch shows the forecast.")
        Sheet {
            SectionTitle("Server")
            OutlinedTextField(
                value = server,
                onValueChange = { server = it; serverMessage = null },
                label = { Text("Server address") },
                placeholder = { Text("http://192.168.1.20:8000") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedButton(
                onClick = { scope.launch { serverMessage = Account.checkServer(server) } },
                enabled = server.isNotBlank(),
            ) { Text("Check server") }
            when (val m = serverMessage) {
                is Account.Result.Ok -> Text(m.message, color = LocalGr.current.zoneText.getValue(org.glucorag.shared.Zone.TARGET))
                is Account.Result.Error -> Text(m.message, color = MaterialTheme.colorScheme.error)
                null -> Unit
            }
        }
        Sheet {
            SectionTitle("Sign in")
            OutlinedTextField(
                value = email, onValueChange = { email = it; signInError = null }, label = { Text("Email") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = password, onValueChange = { password = it; signInError = null }, label = { Text("Password") },
                singleLine = true, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth(),
            )
            signInError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = {
                        busy = true
                        scope.launch {
                            when (val r = Account.signIn(context, server, email, password)) {
                                is Account.Result.Ok -> onSignedIn(r.hasProfile)
                                is Account.Result.Error -> signInError = r.message
                            }
                            busy = false
                        }
                    },
                    enabled = !busy && server.isNotBlank() && email.isNotBlank() && password.isNotEmpty(),
                ) { Text(if (busy) "Signing in" else "Sign in") }
            }
            TextButton(
                onClick = {
                    val base = (checkServerUrl(server.trim()) as? ServerUrlCheck.Ok)?.base
                    if (base == null) serverMessage = Account.Result.Error("Enter the server address first.")
                    else openUrl(context, "$base/ui/signup")
                },
            ) { Text("No account? Create one on the website") }
        }
        ResearchNotice()
    }
}

/** Shown after sign-in when the account has no profile yet. */
@Composable
fun FinishSetupScreen(server: String?, onReady: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var message by remember { mutableStateOf<String?>(null) }
    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Finish setup on the website", style = MaterialTheme.typography.headlineSmall)
        Hint("The forecast needs four facts about you: diabetes type, age, sex and BMI. Enter them on the website, then come back.")
        Button(onClick = { server?.let { openUrl(context, "$it/ui/setup") } }) { Text("Open the website") }
        OutlinedButton(
            onClick = {
                scope.launch {
                    when (Account.hasProfile(context)) {
                        true -> onReady()
                        false -> message = "Setup isn't finished yet."
                        null -> message = "Couldn't reach the server."
                    }
                }
            },
        ) { Text("I've finished setup") }
        message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        ResearchNotice()
    }
}
