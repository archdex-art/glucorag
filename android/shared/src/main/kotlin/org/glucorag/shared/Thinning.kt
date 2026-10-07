package org.glucorag.shared

private const val MIN_GAP_MS = 270_000L

/** Keeps roughly one reading per 5 minutes for upload; remembers the last queued time. */
class Thinner(var lastQueuedT: Long?) {
    fun shouldQueue(t: Long): Boolean {
        val last = lastQueuedT
        if (last != null && t - last < MIN_GAP_MS) return false
        lastQueuedT = t
        return true
    }
}
