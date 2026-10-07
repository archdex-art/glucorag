package org.glucorag.app.ui

import org.glucorag.app.data.Session
import org.junit.Assert.assertEquals
import org.junit.Test

class AccountTest {
    /** Another account's markers would drop the new account's first readings and alert history. */
    @Test
    fun signingInStartsAFreshSession() {
        val next = signedIn(base = "http://10.0.2.2:8851", token = "tok", email = "noor@example.com", unit = "mg/dL")
        assertEquals(
            Session(server = "http://10.0.2.2:8851", token = "tok", email = "noor@example.com", unit = "mg/dL"),
            next,
        )
        assertEquals(null, next.lastQueuedT)
        assertEquals(null, next.lastAlertId)
        assertEquals(emptyList<String>(), next.notifiedAlerts)
    }
}
