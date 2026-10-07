package org.glucorag.app.ui

import org.glucorag.shared.ServerUrlCheck
import org.glucorag.shared.checkServerUrl
import java.net.URI
import java.net.URISyntaxException
import java.net.URLDecoder

/** The pairing link the website shows as a QR code: `glucorag://pair?server=<url-encoded>&code=ABCDEFGH`. */
sealed interface PairLink {
    /** [server] is a `checkServerUrl` Ok base; [code] is normalized (see [normalizePairCode]). */
    data class Ok(val server: String, val code: String) : PairLink
    data class Invalid(val reason: String) : PairLink
}

const val NOT_A_PAIRING_LINK = "That isn't a GlucoRAG pairing code. On the website, make a new pairing code and scan it."
const val PAIR_CODE_HINT = "Enter the 8-character code from the website, like ABCD-EFGH."

/** The alphabet the server draws codes from: no 0/O or 1/I, so they can't be misread. */
private val CODE = Regex("^[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{8}$")

/** "abcd-efgh" / "ABCD EFGH" → "ABCDEFGH"; null when it isn't a possible pairing code. */
fun normalizePairCode(input: String): String? {
    val code = input.filterNot { it == '-' || it.isWhitespace() }.uppercase()
    return code.takeIf { CODE.matches(it) }
}

/** "ABCDEFGH" → "ABCD-EFGH", as the website shows it. */
fun displayPairCode(code: String): String = if (code.length == 8) "${code.take(4)}-${code.drop(4)}" else code

/** Parses a scanned or tapped pairing link; the server address must pass the same rule as a typed one. */
fun parsePairLink(text: String): PairLink {
    val uri = try {
        URI(text.trim())
    } catch (e: URISyntaxException) {
        return PairLink.Invalid(NOT_A_PAIRING_LINK)
    }
    if (!uri.scheme.equals("glucorag", ignoreCase = true) || !uri.host.equals("pair", ignoreCase = true)) {
        return PairLink.Invalid(NOT_A_PAIRING_LINK)
    }
    val params = uri.rawQuery.orEmpty().split('&').filter { it.isNotEmpty() }.associate { part ->
        val key = part.substringBefore('=')
        val value = part.substringAfter('=', "")
        decode(key) to decode(value)
    }
    val server = params["server"]?.takeIf { it.isNotBlank() } ?: return PairLink.Invalid(NOT_A_PAIRING_LINK)
    val code = params["code"]?.let(::normalizePairCode) ?: return PairLink.Invalid(NOT_A_PAIRING_LINK)
    return when (val check = checkServerUrl(server)) {
        is ServerUrlCheck.Ok -> PairLink.Ok(check.base, code)
        is ServerUrlCheck.Rejected -> PairLink.Invalid(check.reason)
    }
}

private fun decode(s: String): String = try {
    URLDecoder.decode(s, "UTF-8")
} catch (e: IllegalArgumentException) {
    s
}
