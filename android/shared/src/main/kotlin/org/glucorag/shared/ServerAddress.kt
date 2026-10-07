package org.glucorag.shared

import java.net.Inet4Address
import java.net.Inet6Address
import java.net.InetAddress

sealed interface ServerUrlCheck {
    /** [base] is `scheme://host[:port]`, no trailing slash or path; IPv6 hosts keep brackets. */
    data class Ok(val base: String) : ServerUrlCheck
    data class Rejected(val reason: String) : ServerUrlCheck
}

const val REASON_NEEDS_HTTPS = "Use https:// for addresses outside your home network or Tailscale."
const val REASON_NO_SCHEME = "Start the address with http:// or https://"
const val REASON_INVALID = "That doesn't look like a server address."

private val SCHEME = Regex("^(https?)://([^/?#]*)", RegexOption.IGNORE_CASE)
private val IPV4 = Regex("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$")
private val IPV6_CHARS = Regex("^[0-9a-fA-F:.]+$")
private val HOSTNAME = Regex("^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$")
private val TAILSCALE_V6_PREFIX = byteArrayOf(0xfd.toByte(), 0x7a, 0x11, 0x5c, 0xa1.toByte(), 0xe0.toByte())

/**
 * Validates a user-entered server address. https is always allowed; plain http only for
 * home-network/Tailscale addresses. Never performs DNS: only IP literals are parsed.
 */
fun checkServerUrl(url: String): ServerUrlCheck {
    val match = SCHEME.find(url.trim()) ?: return ServerUrlCheck.Rejected(REASON_NO_SCHEME)
    val scheme = match.groupValues[1].lowercase()
    val authority = match.groupValues[2].substringAfterLast('@')

    val hostPart: String
    val portPart: String
    if (authority.startsWith("[")) {
        val close = authority.indexOf(']')
        if (close < 0) return ServerUrlCheck.Rejected(REASON_INVALID)
        hostPart = authority.substring(0, close + 1)
        val rest = authority.substring(close + 1)
        if (rest.isNotEmpty() && !rest.startsWith(":")) return ServerUrlCheck.Rejected(REASON_INVALID)
        portPart = rest.removePrefix(":")
    } else {
        if (authority.count { it == ':' } > 1) return ServerUrlCheck.Rejected(REASON_INVALID)
        hostPart = authority.substringBefore(':')
        portPart = authority.substringAfter(':', "")
    }
    if (authority.endsWith(":") || (portPart.isNotEmpty() && !validPort(portPart))) {
        return ServerUrlCheck.Rejected(REASON_INVALID)
    }

    val homeOrTailnet = when {
        hostPart.startsWith("[") -> ipv6Allowed(hostPart.substring(1, hostPart.length - 1))
            ?: return ServerUrlCheck.Rejected(REASON_INVALID)
        IPV4.matches(hostPart) -> ipv4Allowed(hostPart) ?: return ServerUrlCheck.Rejected(REASON_INVALID)
        HOSTNAME.matches(hostPart) -> hostPart.lowercase().let { it.endsWith(".local") || it.endsWith(".ts.net") }
        else -> return ServerUrlCheck.Rejected(REASON_INVALID)
    }
    if (scheme == "http" && !homeOrTailnet) return ServerUrlCheck.Rejected(REASON_NEEDS_HTTPS)

    val base = "$scheme://$hostPart" + if (portPart.isEmpty()) "" else ":$portPart"
    return ServerUrlCheck.Ok(base)
}

private fun validPort(p: String): Boolean =
    p.length <= 5 && p.all { it.isDigit() } && p.toInt() in 1..65535

/** Null when not a valid dotted-quad literal. */
private fun ipv4Allowed(host: String): Boolean? {
    val octets = IPV4.matchEntire(host)!!.groupValues.drop(1).map { it.toInt() }
    if (octets.any { it > 255 }) return null
    return ipv4BytesAllowed(octets)
}

private fun ipv4BytesAllowed(o: List<Int>): Boolean {
    val (a, b) = o
    return a == 10 ||
        (a == 172 && b in 16..31) ||
        (a == 192 && b == 168) ||
        (a == 169 && b == 254) ||
        a == 127 ||
        (a == 100 && b in 64..127)
}

/** Null when not a valid IPv6 literal. The character guard guarantees no DNS lookup. */
private fun ipv6Allowed(literal: String): Boolean? {
    val address = literal.substringBefore('%') // drop zone id ("%25wlan0" in URLs)
    if (!address.contains(':') || !IPV6_CHARS.matches(address)) return null
    val ip = try {
        InetAddress.getByName(address)
    } catch (e: Exception) {
        return null
    }
    val bytes = ip.address
    return when (ip) {
        is Inet4Address -> ipv4BytesAllowed(bytes.map { it.toInt() and 0xff }) // IPv4-mapped
        is Inet6Address -> ip.isLoopbackAddress ||
            (bytes[0] == 0xfe.toByte() && (bytes[1].toInt() and 0xc0) == 0x80) ||
            bytes.copyOfRange(0, 6).contentEquals(TAILSCALE_V6_PREFIX)
        else -> null
    }
}
