package dev.privateflow

import org.junit.Assert.assertThrows
import org.junit.Test

class BridgeEndpointTest {
    @Test fun rejectsCgnatLookingDnsNames() {
        listOf(
            "100.64.1.2.example.com",
            "example.100.64.1.2",
            "100.example.64.1.2",
            "100.64.1.2.",
        ).forEach { host ->
            assertThrows("HTTP DNS name must not bypass the CGNAT gate: $host", RuntimeException::class.java) {
                Bridge.validateEndpoint("http://$host:8767")
            }
        }
    }

    @Test fun acceptsLiteralCgnatBoundariesAndDocumentedLocalEndpoints() {
        listOf("100.64.0.0", "100.64.1.2", "100.127.255.255", "127.0.0.1", "localhost", "10.0.2.2").forEach { host ->
            Bridge.validateEndpoint("http://$host:8767")
            Bridge.validateEndpoint("http://$host:8767/")
        }
    }

    @Test fun rejectsNonCgnatAndMalformedNumericHttpHosts() {
        listOf("100.63.255.255", "100.128.0.0", "192.168.1.2", "8.8.8.8", "100.64.1.256", "100.64.1", "100.64.1.2.3", "100.064.1.2", "100.64.01.2").forEach { host ->
            assertThrows("Invalid HTTP address must be rejected: $host", RuntimeException::class.java) {
                Bridge.validateEndpoint("http://$host:8767")
            }
        }
    }

    @Test fun preservesHttpsSupport() {
        listOf("https://example.com", "https://100.64.1.2.example.com:8767", "https://192.168.1.2/", "https://[::1]:8767").forEach(Bridge::validateEndpoint)
    }

    @Test fun rejectsUnsupportedSchemesAndExtraUrlComponents() {
        listOf("ftp://100.64.1.2", "http://user@100.64.1.2", "https://example.com/path", "https://example.com?query=1", "https://example.com#fragment").forEach { url ->
            assertThrows(IllegalArgumentException::class.java) { Bridge.validateEndpoint(url) }
        }
    }
}
