package com.caspintunel.smsbridge

import java.net.URI
import java.net.URLDecoder

/**
 * The panel's setup QR (Apps page → "App setup QR code"; backend apps/payments_sms/device_url.py):
 *
 *     caspin-sms://<host>[:port]?token=<url-encoded device token>
 *
 * → server URL `https://<host>[:port]` + the device token. Nothing else is accepted, so a random QR
 * (a web link, a Wi-Fi code) can never re-point the app. Change the backend and this file together.
 * Plain JVM code (no android.net.Uri) so SetupQrTest runs as a unit test.
 */
object SetupQr {
    const val SCHEME = "caspin-sms"

    data class Setup(val serverUrl: String, val token: String)

    fun parse(raw: String?): Setup? {
        val uri = try {
            URI(raw?.trim().orEmpty())
        } catch (_: Exception) {
            return null
        }
        if (!SCHEME.equals(uri.scheme, ignoreCase = true)) return null
        val host = uri.host?.lowercase()?.takeIf { it.isNotBlank() } ?: return null
        if (!uri.rawPath.isNullOrEmpty() || uri.rawFragment != null || uri.rawUserInfo != null) return null
        val token = uri.rawQuery.orEmpty().split('&')
            .firstOrNull { it.startsWith("token=") }
            ?.let { URLDecoder.decode(it.removePrefix("token="), "UTF-8").trim() }
            ?.takeIf { it.isNotEmpty() && it.none(Char::isWhitespace) }
            ?: return null
        val port = if (uri.port > 0) ":${uri.port}" else ""
        return Setup("https://$host$port", token)
    }
}
