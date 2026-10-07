package org.glucorag.app.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.SessionStore
import org.glucorag.shared.GlucoseUnit

enum class Screen { CONNECT, FINISH_SETUP, SOURCE, CHECKLIST, TODAY, SETTINGS }

class MainActivity : ComponentActivity() {
    /** Bumped on every resume, so screens re-read settings the user may have changed elsewhere. */
    private val resumeTick = mutableIntStateOf(0)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            GlucoTheme {
                Surface(Modifier.fillMaxSize()) { App(resumeTick.intValue) }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        resumeTick.intValue++
    }
}

/** Navigation: no token → Connect; no reading yet → Source; then Today. */
@Composable
private fun App(resumeTick: Int) {
    val context = LocalContext.current
    val store = remember { SessionStore(context) }
    val session by store.session.collectAsState(initial = null)
    val local = LocalState.get(context)
    val reading by local.reading.collectAsState()
    val sync by local.sync.collectAsState()
    var screen by remember { mutableStateOf<Screen?>(null) }

    val s = session ?: return
    val current = screen ?: when {
        s.token == null && sync == null -> Screen.CONNECT
        s.token == null -> Screen.TODAY // revoked on the server: Today says so and offers sign-in
        reading == null -> Screen.SOURCE
        else -> Screen.TODAY
    }
    val unit = s.unit?.let(GlucoseUnit::parse) ?: GlucoseUnit.MG_DL

    BackHandler(enabled = current == Screen.SETTINGS || current == Screen.CHECKLIST) { screen = Screen.TODAY }

    androidx.compose.foundation.layout.Box(Modifier.safeDrawingPadding()) {
        when (current) {
            Screen.CONNECT -> ConnectScreen(s.server) { hasProfile -> screen = if (hasProfile) Screen.SOURCE else Screen.FINISH_SETUP }
            Screen.FINISH_SETUP -> FinishSetupScreen(s.server) { screen = Screen.SOURCE }
            Screen.SOURCE -> SourceScreen(unit) { screen = Screen.CHECKLIST }
            Screen.CHECKLIST -> ChecklistScreen(onDone = { screen = Screen.TODAY }, resumeTick = resumeTick)
            Screen.TODAY -> TodayScreen(s.server, onSettings = { screen = Screen.SETTINGS }, onSignIn = { screen = Screen.CONNECT })
            Screen.SETTINGS -> SettingsScreen(
                s,
                onBack = { screen = Screen.TODAY },
                onChangeSource = { screen = Screen.SOURCE },
                onSignedOut = { screen = Screen.CONNECT },
            )
        }
    }
}
