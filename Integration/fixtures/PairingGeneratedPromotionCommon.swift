// SPDX-License-Identifier: AGPL-3.0-only
// Synthetic external app/parser seam for the actual-manager fixture only.
// This does not exercise or model the real MinimuxerCommon parser.
import Foundation

public enum PairingProtocol: String, Sendable { case lockdown, rppairing, unknown }
public protocol PairingFile {}
private struct FixturePairingFile: PairingFile {}
public enum PairingFileParser {
    public static var onParse: ((String, PairingProtocol?) throws -> Void)?
    public static var calls = 0
    public static func parse(content: String, preferred: PairingProtocol?) throws -> any PairingFile {
        calls += 1
        try onParse?(content, preferred)
        return FixturePairingFile()
    }
}
public struct MinimuxerPairedDevice: Sendable {
    public let name: String
    public let model: String
    public let pairingFilePath: String
    public init(name: String, model: String, pairingFilePath: String) {
        self.name = name; self.model = model; self.pairingFilePath = pairingFilePath
    }
}
