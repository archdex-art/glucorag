package org.glucorag.app.ui

import org.glucorag.shared.REASON_NEEDS_HTTPS
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PairingTest {
    @Test
    fun validLinkWithEncodedServer() {
        assertEquals(
            PairLink.Ok("http://192.168.1.20:8851", "ABCDEFGH"),
            parsePairLink("glucorag://pair?server=http%3A%2F%2F192.168.1.20%3A8851&code=ABCDEFGH"),
        )
    }

    @Test
    fun serverIsNormalizedLikeATypedOne() {
        assertEquals(
            PairLink.Ok("https://glucorag.example.ts.net", "ABCDEFGH"),
            parsePairLink("glucorag://pair?code=abcd-efgh&server=https%3A%2F%2Fglucorag.example.ts.net%2F"),
        )
    }

    @Test
    fun schemeAndHostAreCaseInsensitive() {
        assertEquals(
            PairLink.Ok("http://10.0.0.5:8000", "ABCDEFGH"),
            parsePairLink("GlucoRAG://PAIR?server=http%3A%2F%2F10.0.0.5%3A8000&code=ABCDEFGH"),
        )
    }

    @Test
    fun missingParametersAreRejected() {
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("glucorag://pair?code=ABCDEFGH"))
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("glucorag://pair?server=http%3A%2F%2F10.0.0.5"))
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("glucorag://pair"))
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("glucorag://pair?server=&code="))
    }

    @Test
    fun otherSchemesHostsAndJunkAreRejected() {
        val query = "server=http%3A%2F%2F10.0.0.5&code=ABCDEFGH"
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("https://pair?$query"))
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("glucorag://login?$query"))
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("hello world"))
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink(""))
    }

    @Test
    fun badCodeIsRejected() {
        // 0, O, 1 and I are not in the code alphabet; 7 characters is too short.
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("glucorag://pair?server=http%3A%2F%2F10.0.0.5&code=ABCD0FGH"))
        assertEquals(PairLink.Invalid(NOT_A_PAIRING_LINK), parsePairLink("glucorag://pair?server=http%3A%2F%2F10.0.0.5&code=ABCDEFG"))
    }

    @Test
    fun serverFollowsTheCleartextRule() {
        assertEquals(
            PairLink.Invalid(REASON_NEEDS_HTTPS),
            parsePairLink("glucorag://pair?server=http%3A%2F%2Fglucorag.example.com&code=ABCDEFGH"),
        )
    }

    @Test
    fun codesNormalizeAndDisplayWithADash() {
        assertEquals("ABCDEFGH", normalizePairCode("abcd-efgh"))
        assertEquals("ABCDEFGH", normalizePairCode(" ABCD EFGH "))
        assertNull(normalizePairCode("ABCD-EFG"))
        assertNull(normalizePairCode("IOIO-1010"))
        assertEquals("ABCD-EFGH", displayPairCode("ABCDEFGH"))
    }

    /** A pairing link shows only "Pairing with <host>…": the address as people recognise it. */
    @Test
    fun hostShowsAddressAndPortOnly() {
        assertEquals("192.168.1.20:8000", hostOf("http://192.168.1.20:8000"))
        assertEquals("glucorag.example.ts.net", hostOf("https://glucorag.example.ts.net"))
    }
}
