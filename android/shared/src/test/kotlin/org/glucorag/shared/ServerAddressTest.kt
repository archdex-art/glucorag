package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Test

class ServerAddressTest {
    private val outside = "Use https:// for addresses outside your home network or Tailscale."
    private val noScheme = "Start the address with http:// or https://"

    private fun ok(base: String) = ServerUrlCheck.Ok(base)
    private val rejected = ServerUrlCheck.Rejected(outside)

    @Test
    fun privateIpv4Ranges() {
        assertEquals(ok("http://10.0.0.5:8000"), checkServerUrl("http://10.0.0.5:8000"))
        assertEquals(ok("http://192.168.1.20"), checkServerUrl("http://192.168.1.20/"))
        assertEquals(ok("http://169.254.3.4"), checkServerUrl("http://169.254.3.4"))
        assertEquals(ok("http://127.0.0.1:8000"), checkServerUrl("http://127.0.0.1:8000/api/v1"))
    }

    @Test
    fun range172() {
        assertEquals(rejected, checkServerUrl("http://172.15.0.1"))
        assertEquals(ok("http://172.16.0.1"), checkServerUrl("http://172.16.0.1"))
        assertEquals(ok("http://172.31.255.255"), checkServerUrl("http://172.31.255.255"))
        assertEquals(rejected, checkServerUrl("http://172.32.0.1"))
    }

    @Test
    fun cgnatRange() {
        assertEquals(rejected, checkServerUrl("http://100.63.255.255"))
        assertEquals(ok("http://100.64.0.1"), checkServerUrl("http://100.64.0.1"))
        assertEquals(ok("http://100.127.255.255"), checkServerUrl("http://100.127.255.255"))
        assertEquals(rejected, checkServerUrl("http://100.128.0.1"))
    }

    @Test
    fun publicIpv4Rejected() {
        assertEquals(rejected, checkServerUrl("http://8.8.8.8"))
    }

    @Test
    fun ipv6Literals() {
        assertEquals(ok("http://[::1]:8000"), checkServerUrl("http://[::1]:8000/"))
        assertEquals(ok("http://[fe80::1]"), checkServerUrl("http://[fe80::1]"))
        assertEquals(ok("http://[fd7a:115c:a1e0::abcd]:8000"), checkServerUrl("http://[fd7a:115c:a1e0::abcd]:8000"))
        assertEquals(rejected, checkServerUrl("http://[fd7a:115c:a1e1::1]"))
        assertEquals(rejected, checkServerUrl("http://[2001:db8::1]"))
    }

    @Test
    fun mdnsAndTailscaleNames() {
        assertEquals(ok("http://mac.local:8000"), checkServerUrl("http://mac.local:8000"))
        assertEquals(ok("http://mac.tail1234.ts.net"), checkServerUrl("http://mac.tail1234.ts.net/"))
        assertEquals(ok("http://MAC.LOCAL"), checkServerUrl("HTTP://MAC.LOCAL"))
    }

    @Test
    fun publicHostnameNeedsHttps() {
        assertEquals(rejected, checkServerUrl("http://example.com"))
        assertEquals(rejected, checkServerUrl("http://notlocal"))
        assertEquals(ok("https://example.com"), checkServerUrl("https://example.com"))
        assertEquals(ok("https://example.com:8443"), checkServerUrl("https://example.com:8443/path/x?q=1"))
    }

    @Test
    fun missingScheme() {
        assertEquals(ServerUrlCheck.Rejected(noScheme), checkServerUrl("mac.local:8000"))
        assertEquals(ServerUrlCheck.Rejected(noScheme), checkServerUrl("ftp://mac.local"))
        assertEquals(ServerUrlCheck.Rejected(noScheme), checkServerUrl(""))
    }

    @Test
    fun whitespaceTrimmed() {
        assertEquals(ok("http://10.0.0.5:8000"), checkServerUrl("  http://10.0.0.5:8000/  "))
    }
}
