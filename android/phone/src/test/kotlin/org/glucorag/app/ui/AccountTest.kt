package org.glucorag.app.ui

import org.glucorag.app.data.Session
import org.junit.Assert.assertEquals
import org.junit.Test

class AccountTest {
    private val base = "http://10.0.2.2:8851"

    /** Another account's thinning marker would drop the new account's first readings. */
    @Test
    fun signingInToAnotherAccountStartsAFreshSession() {
        val previous = Session(server = base, token = "old", email = "sam@example.com", lastStoredT = 7, simulated = true)
        val next = signedIn(previous, base, "tok", "noor@example.com", "mg/dL", otherAccount = true)
        assertEquals(Session(server = base, token = "tok", email = "noor@example.com", unit = "mg/dL"), next)
    }

    /** From this phone only, readings keep being stored one per 5 minutes without a gap. */
    @Test
    fun connectingFromThisPhoneOnlyKeepsTheThinningMarker() {
        val previous = Session(localOnly = true, lastStoredT = 7, unit = "mmol/L", simulated = true)
        val next = signedIn(previous, base, "tok", "noor@example.com", "mg/dL", otherAccount = false)
        assertEquals(Session(server = base, token = "tok", email = "noor@example.com", unit = "mg/dL", lastStoredT = 7), next)
    }

    @Test
    fun signingOutButKeepingDataGoesOnWithoutAServer() {
        val previous = Session(server = base, token = "tok", email = "noor@example.com", lastStoredT = 7, unit = "mmol/L", simulated = true)
        assertEquals(Session(localOnly = true, lastStoredT = 7, unit = "mmol/L", simulated = true), keptOnPhone(previous))
    }
}
