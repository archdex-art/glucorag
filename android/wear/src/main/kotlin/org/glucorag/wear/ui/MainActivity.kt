package org.glucorag.wear.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import androidx.wear.ambient.AmbientLifecycleObserver
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.Typography
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import org.glucorag.wear.R
import org.glucorag.wear.data.AcknowledgementStore
import org.glucorag.wear.data.SnapshotStore

private const val REFRESH_MS = 30_000L

private val Atkinson = FontFamily(
    Font(R.font.atkinson_hyperlegible_next, FontWeight.Normal, variationSettings = FontVariation.Settings(FontVariation.weight(400))),
    Font(R.font.atkinson_hyperlegible_next, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
    Font(R.font.atkinson_hyperlegible_next, FontWeight.SemiBold, variationSettings = FontVariation.Settings(FontVariation.weight(600))),
    Font(R.font.atkinson_hyperlegible_next, FontWeight.Bold, variationSettings = FontVariation.Settings(FontVariation.weight(700))),
)

class MainActivity : ComponentActivity() {
    /** Wear OS 6 keeps the activity resumed in ambient; this tracks it so the UI can go ambient-safe. */
    private var ambient by mutableStateOf(false)

    /** Bumped by the system's once-a-minute ambient update, so ambient text stays roughly current. */
    private var ambientTick by mutableIntStateOf(0)

    private val ambientObserver = AmbientLifecycleObserver(
        this,
        object : AmbientLifecycleObserver.AmbientLifecycleCallback {
            override fun onEnterAmbient(ambientDetails: AmbientLifecycleObserver.AmbientDetails) {
                ambient = true
            }

            override fun onUpdateAmbient() {
                ambientTick++
            }

            override fun onExitAmbient() {
                ambient = false
            }
        },
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lifecycle.addObserver(ambientObserver)
        val snapshots = SnapshotStore(this)
        val acknowledgements = AcknowledgementStore(this)
        setContent {
            GlucoTheme {
                AppScaffold {
                    App(snapshots, acknowledgements, ambient, ambientTick)
                }
            }
        }
    }
}

@Composable
private fun GlucoTheme(content: @Composable () -> Unit) {
    MaterialTheme(typography = Typography(defaultFontFamily = Atkinson), content = content)
}

@Composable
private fun App(snapshots: SnapshotStore, acknowledgements: AcknowledgementStore, ambient: Boolean, ambientTick: Int) {
    val acknowledged by remember { acknowledgements.acknowledged }.collectAsState(initial = null)
    val scope = rememberCoroutineScope()
    when (acknowledged) {
        null -> Unit // Still loading; show nothing rather than flashing the notice.
        false -> AcknowledgeScreen(onAcknowledge = { scope.launch { acknowledgements.acknowledge() } })
        true -> {
            val snapshot by remember { snapshots.flow }.collectAsState(initial = null)
            val context = LocalContext.current
            var nowMs by remember { mutableLongStateOf(System.currentTimeMillis()) }
            var phoneConnected by remember { mutableStateOf<Boolean?>(null) }
            val lifecycleOwner = LocalLifecycleOwner.current

            // The 30 s clock: only while resumed and interactive; ambient pauses it.
            LaunchedEffect(ambient) {
                if (ambient) return@LaunchedEffect
                lifecycleOwner.repeatOnLifecycle(Lifecycle.State.RESUMED) {
                    while (true) {
                        nowMs = System.currentTimeMillis()
                        phoneConnected = try {
                            Wearable.getNodeClient(context).connectedNodes.await().isNotEmpty()
                        } catch (e: ApiException) {
                            // Play services unavailable or the API call failed: say nothing.
                            null
                        }
                        delay(REFRESH_MS)
                    }
                }
            }
            LaunchedEffect(ambientTick) { nowMs = System.currentTimeMillis() }

            HomeScreen(snapshot = snapshot, nowMs = nowMs, phoneConnected = phoneConnected, ambient = ambient)
        }
    }
}
