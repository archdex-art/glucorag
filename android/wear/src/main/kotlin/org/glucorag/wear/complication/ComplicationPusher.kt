package org.glucorag.wear.complication

import android.content.Context
import androidx.core.content.edit
import org.glucorag.shared.StatusKind

/**
 * Push throttling (spec §1 update rates): complications at most once per 5 min unless the status
 * kind changes, the tile at most once per minute. Pure state; [load]/[save] persist it.
 */
class ComplicationPusher(
    private val clock: () -> Long,
    lastPush: Long?,
    lastKind: StatusKind?,
    lastTile: Long? = null,
) {
    /** What to update for one snapshot. */
    data class Decision(val complications: Boolean, val tile: Boolean)

    var lastPush: Long? = lastPush
        private set
    var lastKind: StatusKind? = lastKind
        private set
    var lastTile: Long? = lastTile
        private set

    /** True if the kind changed or ≥ [COMPLICATION_INTERVAL_MS] since the last push. */
    fun shouldPush(newKind: StatusKind, nowMs: Long = clock()): Boolean {
        val last = lastPush ?: return true
        return newKind != lastKind || nowMs - last >= COMPLICATION_INTERVAL_MS
    }

    fun markPushed(kind: StatusKind, nowMs: Long = clock()) {
        lastPush = nowMs
        lastKind = kind
    }

    /** True if ≥ [TILE_INTERVAL_MS] since the last tile update request. */
    fun shouldRequestTile(nowMs: Long = clock()): Boolean {
        val last = lastTile ?: return true
        return nowMs - last >= TILE_INTERVAL_MS
    }

    /**
     * Decides for a snapshot with status [kind] and records what it decided to push. The tile
     * follows every snapshot change, limited only by its own one-minute interval.
     */
    fun decide(kind: StatusKind, nowMs: Long = clock()): Decision {
        val complications = shouldPush(kind, nowMs)
        if (complications) markPushed(kind, nowMs)
        val tile = shouldRequestTile(nowMs)
        if (tile) lastTile = nowMs
        return Decision(complications, tile)
    }

    /** Persists the throttle state in [context]'s private preferences. */
    fun save(context: Context) {
        prefs(context).edit {
            lastPush?.let { putLong(KEY_PUSH, it) } ?: remove(KEY_PUSH)
            lastKind?.let { putString(KEY_KIND, it.name) } ?: remove(KEY_KIND)
            lastTile?.let { putLong(KEY_TILE, it) } ?: remove(KEY_TILE)
        }
    }

    companion object {
        const val COMPLICATION_INTERVAL_MS = 300_000L
        const val TILE_INTERVAL_MS = 60_000L

        private const val PREFS = "complication_pusher"
        private const val KEY_PUSH = "last_push"
        private const val KEY_KIND = "last_kind"
        private const val KEY_TILE = "last_tile"

        private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        /** The throttle state persisted by [save], with the wall clock. */
        fun load(context: Context, clock: () -> Long = System::currentTimeMillis): ComplicationPusher {
            val p = prefs(context)
            return ComplicationPusher(
                clock = clock,
                lastPush = if (p.contains(KEY_PUSH)) p.getLong(KEY_PUSH, 0L) else null,
                lastKind = p.getString(KEY_KIND, null)?.let { name -> StatusKind.entries.firstOrNull { it.name == name } },
                lastTile = if (p.contains(KEY_TILE)) p.getLong(KEY_TILE, 0L) else null,
            )
        }
    }
}
