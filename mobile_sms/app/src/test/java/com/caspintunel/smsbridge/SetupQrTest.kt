package com.caspintunel.smsbridge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Same cases as backend apps/adminpanel/tests/test_apps.py (what the panel's QR encodes). */
class SetupQrTest {
    private val token = "Ab3_x-Z9kQ0pL7mN2vR5tY8wE1uI4oP6sD0fG3hJ5kM"

    @Test fun ourDomain() {
        assertEquals(SetupQr.Setup("https://caspin.example", token),
            SetupQr.parse("caspin-sms://caspin.example?token=$token"))
    }

    @Test fun storeDomainWithPortAndEncodedToken() {
        assertEquals(SetupQr.Setup("https://shop-qr.example:8443", "a+b/c="),
            SetupQr.parse("caspin-sms://Shop-QR.example:8443?token=a%2Bb%2Fc%3D"))
    }

    @Test fun punycodeStoreDomain() {
        assertEquals("https://xn--mgbh0fb.example", SetupQr.parse("caspin-sms://xn--mgbh0fb.example?token=t1")?.serverUrl)
    }

    @Test fun refusesAnythingElse() {
        listOf(
            null, "", "hello", "https://caspin.example?token=t1", "caspin-sms://caspin.example",
            "caspin-sms://caspin.example?token=", "caspin-sms://caspin.example/path?token=t1",
            "caspin-sms://caspin.example?token=t1#x", "caspin-sms://user@caspin.example?token=t1",
            "caspin-sms://?token=t1", "caspin-sms://caspin.example?token=a%20b",
        ).forEach { assertNull(it, SetupQr.parse(it)) }
    }
}
