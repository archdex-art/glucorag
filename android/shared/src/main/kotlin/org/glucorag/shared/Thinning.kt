package org.glucorag.shared

private const val MIN_GAP_MS = 270_000L

/** Keeps roughly one reading per 5 minutes (stored and uploaded); remembers the last kept time. */
class Thinner(var lastKeptT: Long?) {
    fun shouldKeep(t: Long): Boolean {
        val last = lastKeptT
        if (last != null && t - last < MIN_GAP_MS) return false
        lastKeptT = t
        return true
    }
}
