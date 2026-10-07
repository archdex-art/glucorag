package org.glucorag.app.source

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import org.glucorag.app.sync.Pipeline
import org.glucorag.shared.parseCgm

/**
 * Receives Juggluco's `glucodata.Minute` and xDrip+'s `BgEstimate` broadcasts. Both apps send them
 * only to package names the user entered, so the user must register `org.glucorag.app` there.
 */
class GlucoseReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val extras = intent.extras ?: return
        @Suppress("DEPRECATION") // Bundle.get: the extras' types differ between the two apps.
        val map = extras.keySet().associateWith { extras.get(it) }
        val reading = parseCgm(intent.action, map, System.currentTimeMillis()) ?: return
        val pending = goAsync()
        scope.launch {
            try {
                // Stay inside the receiver's 10 s budget; the reading is kept locally either way.
                withTimeoutOrNull(BUDGET_MS) { Pipeline.receive(context, reading) }
            } finally {
                pending.finish()
            }
        }
    }

    private companion object {
        const val BUDGET_MS = 8_000L
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    }
}
