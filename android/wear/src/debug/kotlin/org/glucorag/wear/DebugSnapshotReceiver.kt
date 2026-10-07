package org.glucorag.wear

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.glucorag.wear.data.SnapshotSync

/**
 * Debug builds only: feeds a snapshot without a phone, through the same path as the Data Layer
 * listener.
 *
 * `adb shell am broadcast -a org.glucorag.wear.DEBUG_SNAPSHOT -p org.glucorag.app --es json '{...}'`
 */
class DebugSnapshotReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION) return
        val json = intent.getStringExtra(EXTRA_JSON) ?: return
        val pending = goAsync()
        scope.launch {
            try {
                val saved = SnapshotSync.receive(context, json.toByteArray())
                Log.i(TAG, if (saved != null) "Saved snapshot written=${saved.written}" else "Snapshot ignored (invalid or not newer)")
            } finally {
                pending.finish()
            }
        }
    }

    private companion object {
        const val ACTION = "org.glucorag.wear.DEBUG_SNAPSHOT"
        const val EXTRA_JSON = "json"
        const val TAG = "DebugSnapshot"
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    }
}
