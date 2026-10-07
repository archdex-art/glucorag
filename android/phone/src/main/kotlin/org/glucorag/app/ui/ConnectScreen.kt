package org.glucorag.app.ui

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.launch
import org.glucorag.shared.ServerUrlCheck
import org.glucorag.shared.Zone
import org.glucorag.shared.checkServerUrl

/**
 * Google's code scanner: Play services shows the camera, so this app needs no camera permission.
 * [onScanned] gets the QR code's text; [onError] why the scanner couldn't run. Cancelling does nothing.
 */
private fun scanQrCode(context: Context, onScanned: (String) -> Unit, onError: (String) -> Unit) {
    val options = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
    GmsBarcodeScanning.getClient(context, options).startScan()
        .addOnSuccessListener { barcode -> barcode.rawValue?.let(onScanned) ?: onError(NOT_A_PAIRING_LINK) }
        .addOnFailureListener { onError("Couldn't open the scanner. Enter the pairing code instead.") }
}

/**
 * Pairing with the website (QR code or typed code), or sign-in with email and password.
 * [autoPair] is a pairing link that opened the app: it is redeemed at once, and [onAutoPairTaken]
 * tells the caller it has been taken. [onSignedIn] gets whether the account has a profile.
 */
@Composable
fun ConnectScreen(
    initialServer: String?,
    autoPair: PairLink.Ok?,
    onAutoPairTaken: () -> Unit,
    onSignedIn: (hasProfile: Boolean) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var server by rememberSaveable { mutableStateOf(initialServer ?: "") }
    var code by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var typeCode by rememberSaveable { mutableStateOf(false) }
    var useEmail by rememberSaveable { mutableStateOf(false) }
    var serverMessage by remember { mutableStateOf<Account.Result?>(null) }
    var pairMessage by remember { mutableStateOf<String?>(null) }
    var codeError by remember { mutableStateOf<String?>(null) }
    var signInError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf<String?>(null) }

    fun redeem(link: PairLink.Ok) {
        busy = "Pairing with ${link.server}…"
        pairMessage = null
        scope.launch {
            when (val r = Account.pair(context, link)) {
                is Account.Result.Ok -> onSignedIn(r.hasProfile)
                is Account.Result.Error -> pairMessage = r.message
            }
            busy = null
        }
    }

    fun redeemScanned(text: String) {
        when (val link = parsePairLink(text)) {
            is PairLink.Ok -> {
                server = link.server
                code = displayPairCode(link.code)
                redeem(link)
            }
            is PairLink.Invalid -> pairMessage = link.reason
        }
    }

    fun redeemTyped() {
        val base = when (val check = checkServerUrl(server.trim())) {
            is ServerUrlCheck.Ok -> check.base
            is ServerUrlCheck.Rejected -> {
                serverMessage = Account.Result.Error(check.reason)
                return
            }
        }
        val normalized = normalizePairCode(code)
        if (normalized == null) {
            codeError = PAIR_CODE_HINT
            return
        }
        redeem(PairLink.Ok(base, normalized))
    }

    LaunchedEffect(autoPair) {
        val link = autoPair ?: return@LaunchedEffect
        onAutoPairTaken()
        server = link.server
        code = displayPairCode(link.code)
        // On failure the typed-code fields show what the link held, ready to correct or retry.
        typeCode = true
        redeem(link)
    }

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("GlucoRAG", style = MaterialTheme.typography.headlineSmall)
        Hint("Connect this phone to your GlucoRAG server. Readings from your CGM app upload here, and your watch shows the forecast.")
        Sheet {
            SectionTitle("Pair with the website")
            Hint("On the GlucoRAG website, open Settings, then Connected devices, and choose Connect a phone. Scan the QR code it shows: the phone finds the server and signs in.")
            Button(
                onClick = { pairMessage = null; scanQrCode(context, ::redeemScanned) { pairMessage = it } },
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Scan QR code") }
            OutlinedButton(
                onClick = { typeCode = !typeCode },
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Enter pairing code") }
            busy?.let { Hint(it) }
            pairMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
        if (typeCode || useEmail) {
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
                    is Account.Result.Ok -> Text(m.message, color = LocalGr.current.zoneText.getValue(Zone.TARGET))
                    is Account.Result.Error -> Text(m.message, color = MaterialTheme.colorScheme.error)
                    null -> Unit
                }
            }
        }
        if (typeCode) {
            Sheet {
                SectionTitle("Pairing code")
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it; codeError = null; pairMessage = null },
                    label = { Text("Code from the website") },
                    placeholder = { Text("ABCD-EFGH") },
                    singleLine = true,
                    isError = codeError != null,
                    supportingText = codeError?.let { { Text(it) } },
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Characters,
                        autoCorrectEnabled = false,
                        keyboardType = KeyboardType.Ascii,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    onClick = ::redeemTyped,
                    enabled = busy == null && server.isNotBlank() && code.isNotBlank(),
                ) { Text(if (busy != null) "Pairing" else "Pair") }
            }
        }
        if (!useEmail) {
            TextButton(onClick = { useEmail = true }) { Text("Sign in with email instead") }
        } else {
            Sheet {
                SectionTitle("Sign in with email")
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
                Button(
                    onClick = {
                        busy = "Signing in…"
                        scope.launch {
                            when (val r = Account.signIn(context, server, email, password)) {
                                is Account.Result.Ok -> onSignedIn(r.hasProfile)
                                is Account.Result.Error -> signInError = r.message
                            }
                            busy = null
                        }
                    },
                    enabled = busy == null && server.isNotBlank() && email.isNotBlank() && password.isNotEmpty(),
                ) { Text(if (busy != null) "Signing in" else "Sign in") }
                TextButton(
                    onClick = {
                        val base = (checkServerUrl(server.trim()) as? ServerUrlCheck.Ok)?.base
                        if (base == null) serverMessage = Account.Result.Error("Enter the server address first.")
                        else openUrl(context, "$base/ui/signup")
                    },
                ) { Text("No account? Create one on the website") }
            }
        }
        ResearchNotice()
    }
}
