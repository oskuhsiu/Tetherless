// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore

@Suite("ODA package integrity/admission, not publisher trust or real ADI loading")
struct AnisettePackageInputTests {
    @Test func requiresCompleteASCIIHexDigest() throws {
        #expect(throws: AnisettePackageFailure.missingDigest) { try AnisettePackageInput.digest(nil) }
        for value in ["", String(repeating: "a", count: 63), String(repeating: "g", count: 64),
                      String(repeating: "Ａ", count: 64), " " + String(repeating: "a", count: 64)] {
            #expect(throws: AnisettePackageFailure.invalidDigest) { try AnisettePackageInput.digest(value) }
        }
        #expect(try AnisettePackageInput.digest(String(repeating: "Ab", count: 32)) == String(repeating: "ab", count: 32))
    }
    @Test func rejectsMismatchInsteadOfContinuing() throws {
        let digest = String(repeating: "a", count: 64)
        try AnisettePackageInput.verify(expected: digest, actual: digest.uppercased())
        #expect(throws: AnisettePackageFailure.checksumMismatch) {
            try AnisettePackageInput.verify(expected: digest, actual: String(repeating: "b", count: 64))
        }
    }
    @Test func base64AllowsMIMEWhitespaceButNotUnknownData() throws {
        let bytes = Data([0x50, 0x4b, 0x03, 0x04, 0, 255, 1])
        let base64 = bytes.base64EncodedString()
        #expect(try AnisettePackageInput.decodeBase64("\n\t" + base64 + "\r\n") == bytes)
        #expect(try AnisettePackageInput.archive(from: bytes) == bytes)
        #expect(try AnisettePackageInput.archive(from: Data(base64.utf8)) == bytes)
        for input in [base64 + "!", "data:application/zip;base64," + base64, "", "   ", "%%"] {
            #expect(throws: AnisettePackageFailure.invalidPayload) { try AnisettePackageInput.decodeBase64(input) }
        }
    }
    @Test func payloadBudgetsAreBounded() throws {
        let tooLarge = Data(repeating: 0x50, count: AnisettePackageInput.maximumEncodedBytes + 1)
        #expect(throws: AnisettePackageFailure.payloadTooLarge) { try AnisettePackageInput.archive(from: tooLarge) }
        #expect(AnisettePackageInput.maximumMetadataBytes > AnisettePackageInput.maximumEncodedBytes)
    }
    @Test func aFailedOwnerDoesNotImplyAnotherCallSucceeded() throws {
        let gate = AnisettePackageAdmission()
        do {
            let first = try gate.acquire(); defer { first.release() }
            #expect(throws: AnisettePackageFailure.alreadyInProgress) { try gate.acquire() }
            throw AnisettePackageFailure.checksumMismatch
        } catch AnisettePackageFailure.checksumMismatch {}
        let next = try gate.acquire(); next.release()
    }
    @Test func oldLeaseCannotReleaseNewOwnerAndDeinitReleases() throws {
        let gate = AnisettePackageAdmission()
        let first = try gate.acquire(); first.release()
        var second: AnisettePackageAdmission.Lease? = try gate.acquire()
        first.release()
        #expect(throws: AnisettePackageFailure.alreadyInProgress) { try gate.acquire() }
        #expect(second != nil)
        second = nil
        let third = try gate.acquire(); third.release()
    }
    @Test func errorsContainOnlyFixedCategories() {
        let untrusted = "SYNTHETIC_TOKEN_SERVER_METADATA_18A7"
        do {
            _ = try AnisettePackageInput.digest(untrusted)
            Issue.record("Malformed server digest was accepted")
        } catch {
            #expect(error as? AnisettePackageFailure == .invalidDigest)
            #expect(!String(reflecting: error).contains(untrusted))
            #expect(!error.localizedDescription.contains(untrusted))
        }
    }
}
