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

/** "192.168.1.20:8000" for a server base, as a person recognises it. */
internal fun hostOf(server: String): String = try {
    java.net.URI(server).authority ?: server
} catch (e: java.net.URISyntaxException) {
    server
}

/**
 * The first screen: [onUseOnPhone] (null once the phone is set up) uses GlucoRAG without a
 * server; otherwise pairing with the website (QR code or typed code), or sign-in with email and
 * password. [autoPair] is a pairing link that opened the app: it is redeemed at once with only
 * "Pairing with <host>…" on screen, and [onAutoPairTaken] tells the caller it has been taken.
 * [onSignedIn] gets whether the account (or the phone) has About you.
 */
@Composable
fun ConnectScreen(
    initialServer: String?,
    autoPair: PairLink.Ok?,
    onAutoPairTaken: () -> Unit,
    onUseOnPhone: (() -> Unit)?,
    onSignedIn: (hasProfile: Boolean) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var server by rememberSaveable { mutableStateOf(initialServer ?: "") }
    var code by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var connect by rememberSaveable { mutableStateOf(onUseOnPhone == null) }
    var typeCode by rememberSaveable { mutableStateOf(false) }
    var useEmail by rememberSaveable { mutableStateOf(false) }
    // While a link from the website's QR code is being redeemed: only "Pairing with <host>…".
    var fromLink by rememberSaveable { mutableStateOf(false) }
    var serverMessage by remember { mutableStateOf<Account.Result?>(null) }
    var pairMessage by remember { mutableStateOf<String?>(null) }
    var codeError by remember { mutableStateOf<String?>(null) }
    var signInError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf<String?>(null) }

    fun redeem(link: PairLink.Ok) {
        busy = "Pairing with ${hostOf(link.server)}…"
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

    fun typedLink(): PairLink.Ok? {
        val base = when (val check = checkServerUrl(server.trim())) {
            is ServerUrlCheck.Ok -> check.base
            is ServerUrlCheck.Rejected -> {
                serverMessage = Account.Result.Error(check.reason)
                return null
            }
        }
        val normalized = normalizePairCode(code)
        if (normalized == null) {
            codeError = PAIR_CODE_HINT
            return null
        }
        return PairLink.Ok(base, normalized)
    }

    LaunchedEffect(autoPair) {
        val link = autoPair ?: return@LaunchedEffect
        onAutoPairTaken()
        server = link.server
        code = displayPairCode(link.code)
        fromLink = true
        connect = true
        redeem(link)
    }

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("GlucoRAG", style = MaterialTheme.typography.headlineSmall)
        if (fromLink) {
            Sheet {
                SectionTitle("Pairing this phone")
                busy?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
                pairMessage?.let { message ->
                    Text(message, color = MaterialTheme.colorScheme.error)
                    Button(onClick = { typedLink()?.let(::redeem) }, enabled = busy == null) { Text("Try again") }
                    // On failure the typed-code fields show what the link held, ready to correct.
                    TextButton(onClick = { fromLink = false; typeCode = true }) { Text("Other ways to connect") }
                }
            }
            ResearchNotice()
            return@Column
        }
        Hint("GlucoRAG forecasts your glucose for the next hour from your CGM readings, and warns you before a likely low or high.")
        if (onUseOnPhone != null) {
            Sheet {
                SectionTitle("How do you want to use GlucoRAG?")
                Button(onClick = onUseOnPhone, enabled = busy == null, modifier = Modifier.fillMaxWidth()) { Text("Use on this phone only") }
                Hint("No account needed. Forecasts and alerts run on this phone, and your readings stay on it.")
                OutlinedButton(onClick = { connect = true }, enabled = busy == null, modifier = Modifier.fillMaxWidth()) {
                    Text("Connect to a GlucoRAG server")
                }
                Hint("If you or your clinic run a GlucoRAG server: your readings are kept there too, and you can see them on its website. You can also connect later in Settings.")
            }
        }
        if (connect) {
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
        }
        if (connect && (typeCode || useEmail)) {
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
        if (connect && typeCode) {
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
                    onClick = { typedLink()?.let(::redeem) },
                    enabled = busy == null && server.isNotBlank() && code.isNotBlank(),
                ) { Text(if (busy != null) "Pairing" else "Pair") }
            }
        }
        if (connect && !useEmail) {
            TextButton(onClick = { useEmail = true }) { Text("Sign in with email instead") }
        } else if (connect) {
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
