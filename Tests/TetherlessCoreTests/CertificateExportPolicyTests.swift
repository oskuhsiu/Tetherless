// SPDX-License-Identifier: AGPL-3.0-only
import Testing
@testable import TetherlessCore

@Suite("Explicit external signing backup password policy")
struct CertificateExportPolicyTests {
    @Test func newConfirmedPasswordAllowed() throws {
        try CertificateExportPolicy.validate(password: "synthetic separate password", confirmation: "synthetic separate password", serial: "ABCDEF0123456789")
    }
    @Test func emptyShortMismatchedSerialAndOversizedRejected() {
        for (password, confirmation) in [("", ""), ("too-short", "too-short"),
            ("long-but-different", "different-password"), ("abcdef0123456789", "abcdef0123456789"),
            (String(repeating: " ", count: 30), String(repeating: " ", count: 30)),
            (String(repeating: "a", count: 1025), String(repeating: "a", count: 1025))] {
            #expect(throws: CertificateExportFailure.passwordRequirements) {
                try CertificateExportPolicy.validate(password: password, confirmation: confirmation, serial: "ABCDEF0123456789")
            }
        }
    }
}
