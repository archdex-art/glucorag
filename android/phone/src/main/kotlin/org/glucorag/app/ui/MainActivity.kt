package org.glucorag.app.ui

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.SessionStore
import org.glucorag.shared.GlucoseUnit

enum class Screen { CONNECT, PROFILE, SOURCE, CHECKLIST, TODAY, SETTINGS }

class MainActivity : ComponentActivity() {
    /** Bumped on every resume, so screens re-read settings the user may have changed elsewhere. */
    private val resumeTick = mutableIntStateOf(0)

    /** A `glucorag://pair` link that opened the app and hasn't been handled yet. */
    private val pairLink = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // After recreation, the link in the intent was already taken (or is kept in the saved state).
        pairLink.value = if (savedInstanceState == null) pairLinkOf(intent) else savedInstanceState.getString(KEY_PAIR_LINK)
        setContent {
            GlucoTheme {
                Surface(Modifier.fillMaxSize()) {
                    App(resumeTick.intValue, pairLink.value) { pairLink.value = null }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        pairLinkOf(intent)?.let { pairLink.value = it }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        pairLink.value?.let { outState.putString(KEY_PAIR_LINK, it) }
    }

    override fun onResume() {
        super.onResume()
        resumeTick.intValue++
    }

    private fun pairLinkOf(intent: Intent?): String? =
        intent?.takeIf { it.action == Intent.ACTION_VIEW }?.dataString

    private companion object {
        const val KEY_PAIR_LINK = "pair_link"
    }
}

/**
 * Navigation: no token → Connect; no reading yet → Source; then Today. A pairing link goes to
 * Connect, which redeems it; when another account is signed in, the person confirms first.
 */
@Composable
private fun App(resumeTick: Int, pairLink: String?, onPairLinkTaken: () -> Unit) {
    val context = LocalContext.current
    val store = remember { SessionStore(context) }
    val session by store.session.collectAsState(initial = null)
    val local = LocalState.get(context)
    val reading by local.reading.collectAsState()
    val sync by local.sync.collectAsState()
    // Saveable: the screen survives rotation and dark-mode switches (activity recreation).
    var screen by rememberSaveable { mutableStateOf<Screen?>(null) }
    // The confirmed link Connect should redeem; kept as text so it survives recreation.
    var autoPair by rememberSaveable { mutableStateOf<String?>(null) }

    val s = session ?: return
    val current = screen ?: when {
        s.token == null && sync == null -> Screen.CONNECT
        s.token == null -> Screen.TODAY // revoked on the server: Today says so and offers sign-in
        reading == null -> Screen.SOURCE
        else -> Screen.TODAY
    }
    val unit = s.unit?.let(GlucoseUnit::parse) ?: GlucoseUnit.MG_DL

    BackHandler(enabled = current == Screen.SETTINGS || current == Screen.CHECKLIST) { screen = Screen.TODAY }
    // Connect opened by a pairing link while signed in: back returns to the signed-in app.
    BackHandler(enabled = current == Screen.CONNECT && s.token != null) { screen = Screen.TODAY }

    fun pairNow(link: String) {
        autoPair = link
        screen = Screen.CONNECT
        onPairLinkTaken()
    }

    Box(Modifier.safeDrawingPadding()) {
        when (current) {
            Screen.CONNECT -> ConnectScreen(
                initialServer = s.server,
                autoPair = autoPair?.let(::parsePairLink) as? PairLink.Ok,
                onAutoPairTaken = { autoPair = null },
            ) { hasProfile -> screen = if (hasProfile) Screen.SOURCE else Screen.PROFILE }
            Screen.PROFILE -> ProfileScreen { screen = Screen.SOURCE }
            Screen.SOURCE -> SourceScreen(unit, s.simulated, resumeTick) { screen = Screen.CHECKLIST }
            Screen.CHECKLIST -> ChecklistScreen(onDone = { screen = Screen.TODAY }, resumeTick = resumeTick)
            Screen.TODAY -> TodayScreen(
                s.server,
                s.simulated,
                onSettings = { screen = Screen.SETTINGS },
                onSignIn = { screen = Screen.CONNECT },
                onEnterDetails = { screen = Screen.PROFILE },
            )
            Screen.SETTINGS -> SettingsScreen(
                s,
                onBack = { screen = Screen.TODAY },
                onChangeSource = { screen = Screen.SOURCE },
                onSignedOut = { screen = Screen.CONNECT },
            )
        }
    }

    val link = pairLink ?: return
    when (val parsed = parsePairLink(link)) {
        is PairLink.Invalid -> AlertDialog(
            onDismissRequest = onPairLinkTaken,
            title = { Text("Can't pair this phone") },
            text = { Text(parsed.reason) },
            confirmButton = { TextButton(onClick = onPairLinkTaken) { Text("OK") } },
        )
        is PairLink.Ok -> if (s.token == null) {
            LaunchedEffect(link) { pairNow(link) }
        } else {
            AlertDialog(
                onDismissRequest = onPairLinkTaken,
                title = { Text("Switch account?") },
                text = {
                    Text(
                        "This phone is signed in as ${s.email ?: "another account"}. Pairing signs it in to the account " +
                            "that made the code on ${parsed.server} instead. If that is another account, readings that " +
                            "haven't uploaded yet are deleted from this phone; they stay in your CGM app.",
                    )
                },
                confirmButton = { Button(onClick = { pairNow(link) }) { Text("Switch") } },
                dismissButton = { TextButton(onClick = onPairLinkTaken) { Text("Cancel") } },
            )
        }
    }
}
