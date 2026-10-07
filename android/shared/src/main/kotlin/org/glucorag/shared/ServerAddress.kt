package org.glucorag.shared

sealed interface ServerUrlCheck {
    /** [base] is `scheme://host[:port]`, no trailing slash or path; IPv6 hosts keep brackets. */
    data class Ok(val base: String) : ServerUrlCheck
    data class Rejected(val reason: String) : ServerUrlCheck
}

const val REASON_NEEDS_HTTPS = "Use https:// for addresses outside your home network or Tailscale."
const val REASON_NO_SCHEME = "Start the address with http:// or https://"
const val REASON_INVALID = "That doesn't look like a server address."

private val SCHEME = Regex("^(https?)://([^/?#]*)", RegexOption.IGNORE_CASE)
private val IPV4 = Regex("^\\d{1,3}(\\.\\d{1,3}){3}$")
private val HEX_GROUP = Regex("^[0-9a-fA-F]{1,4}$")
private val HOSTNAME = Regex("^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$")
private val TAILSCALE_V6_PREFIX = intArrayOf(0xfd, 0x7a, 0x11, 0x5c, 0xa1, 0xe0)

/**
 * Validates a user-entered server address. https is always allowed; plain http only for
 * home-network/Tailscale addresses. Never performs DNS or calls a resolver: IP literals are
 * parsed by hand and hostnames are judged by suffix only.
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
        hostPart.startsWith("[") -> parseIpv6(hostPart.substring(1, hostPart.length - 1))
            ?.let(::ipv6Allowed) ?: return ServerUrlCheck.Rejected(REASON_INVALID)
        IPV4.matches(hostPart) -> parseIpv4(hostPart)?.let(::ipv4Allowed)
            ?: return ServerUrlCheck.Rejected(REASON_INVALID)
        HOSTNAME.matches(hostPart) -> hostPart.lowercase().let { it.endsWith(".local") || it.endsWith(".ts.net") }
        else -> return ServerUrlCheck.Rejected(REASON_INVALID)
    }
    if (scheme == "http" && !homeOrTailnet) return ServerUrlCheck.Rejected(REASON_NEEDS_HTTPS)

    val base = "$scheme://$hostPart" + if (portPart.isEmpty()) "" else ":$portPart"
    return ServerUrlCheck.Ok(base)
}

private fun validPort(p: String): Boolean =
    p.length <= 5 && p.all { it.isDigit() } && p.toInt() in 1..65535

/** Four octets of a dotted-quad literal, or null when malformed. */
private fun parseIpv4(s: String): IntArray? {
    if (!IPV4.matches(s)) return null
    val octets = s.split('.').map { it.toInt() }
    if (octets.any { it > 255 }) return null
    return octets.toIntArray()
}

private fun ipv4Allowed(o: IntArray): Boolean {
    val a = o[0]
    val b = o[1]
    return a == 10 ||
        (a == 172 && b in 16..31) ||
        (a == 192 && b == 168) ||
        (a == 169 && b == 254) ||
        a == 127 ||
        (a == 100 && b in 64..127)
}

/**
 * The 16 bytes of an IPv6 literal, or null when malformed. At most one `::`; 1–4 hex digits per
 * group; a trailing dotted quad counts as two groups. Zone ids (`%`) are rejected.
 */
private fun parseIpv6(s: String): IntArray? {
    val gap = s.indexOf("::")
    val groups: List<Int>
    if (gap < 0) {
        groups = parseHexGroups(s, allowIpv4Tail = true) ?: return null
        if (groups.size != 8) return null
    } else {
        val head = parseHexGroups(s.substring(0, gap), allowIpv4Tail = false) ?: return null
        val tail = parseHexGroups(s.substring(gap + 2), allowIpv4Tail = true) ?: return null
        if (head.size + tail.size > 7) return null
        groups = head + List(8 - head.size - tail.size) { 0 } + tail
    }
    return IntArray(16) { i -> if (i % 2 == 0) groups[i / 2] shr 8 else groups[i / 2] and 0xff }
}

/** 16-bit groups of a `:`-separated run; empty string → no groups. Null when malformed. */
private fun parseHexGroups(s: String, allowIpv4Tail: Boolean): List<Int>? {
    if (s.isEmpty()) return emptyList()
    val parts = s.split(':')
    val groups = ArrayList<Int>(parts.size + 1)
    for ((i, part) in parts.withIndex()) {
        if (HEX_GROUP.matches(part)) {
            groups += part.toInt(16)
        } else if (allowIpv4Tail && i == parts.lastIndex) {
            val o = parseIpv4(part) ?: return null
            groups += (o[0] shl 8) or o[1]
            groups += (o[2] shl 8) or o[3]
        } else {
            return null
        }
    }
    return groups
}

private fun ipv6Allowed(b: IntArray): Boolean {
    val ipv4Mapped = (0 until 10).all { b[it] == 0 } && b[10] == 0xff && b[11] == 0xff
    if (ipv4Mapped) return ipv4Allowed(b.copyOfRange(12, 16))
    val loopback = (0 until 15).all { b[it] == 0 } && b[15] == 1
    val linkLocal = b[0] == 0xfe && (b[1] and 0xc0) == 0x80
    val tailscale = (0 until 6).all { b[it] == TAILSCALE_V6_PREFIX[it] }
    return loopback || linkLocal || tailscale
}
