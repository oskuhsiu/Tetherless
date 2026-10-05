"""Exact observed Swift stream pair and controlled Apple orchestration only."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_pairing_apple as apple
from apply_patch import VerificationError
from test_pairing_apple import AppleFixture

# These literal bytes are the retained 127-byte successful command log from
# run37375339856/job111982471653, not output from a local native command.
STDOUT = ("Apple Swift version 6.2.4 (swiftlang-6.2.4.1.4 clang-1700.6.4.2)\n"
          "Target: arm64-apple-macosx15.0")
RAW = "swift-driver version: 1.127.15 " + STDOUT + "\n"


class SwiftStreamIdentityTests(unittest.TestCase):
    def test_exact_retained_merged_bytes_match_the_stdout_lock(self):
        self.assertEqual(len(RAW.encode()), 127)
        self.assertEqual(hashlib.sha256(RAW.encode()).hexdigest(),
                         "355986b284d60fc60e4b3c24d2bc54ff2562ee37b60ef688917cf2e531315105")
        apple.require_toolchain_observation(RAW.strip(), STDOUT, "swiftc")

    def test_existing_exact_identity_comparison_is_preserved(self):
        for label, value in (("swiftc", STDOUT), ("swiftc", "controlled swift observation"),
                             ("clang", "controlled clang observation")):
            with self.subTest(label=label, value=value):
                apple.require_toolchain_observation(value, value, label)

    def test_changed_driver_compiler_clang_target_or_extra_text_are_rejected(self):
        for changed in (RAW.replace("1.127.15", "1.127.16"), RAW.replace("6.2.4", "6.2.5"),
                        RAW.replace("1700.6.4.2", "1700.6.4.3"), RAW.replace("macosx15.0", "macosx16.0"),
                        "warning: unexpected\n" + RAW, RAW + "unexpected trailing output\n",
                        RAW.replace("1.127.15 ", "1.127.15\n"), RAW.replace("version: ", "version:")):
            with self.subTest(changed=changed), self.assertRaises(VerificationError):
                apple.require_toolchain_observation(changed.strip(), STDOUT, "swiftc")

    def test_changed_or_unset_lock_and_other_labels_reject_the_pair(self):
        for expected in ("", STDOUT.replace("6.2.4", "6.2.5"), STDOUT.replace("arm64", "x86_64")):
            with self.subTest(expected=expected), self.assertRaises(VerificationError):
                apple.require_toolchain_observation(RAW.strip(), expected, "swiftc")
        for label in ("clang", "xcode", "rustc"):
            with self.subTest(label=label), self.assertRaises(VerificationError):
                apple.require_toolchain_observation(RAW.strip(), STDOUT, label)

    def test_raw_merged_observation_and_log_are_retained(self):
        with tempfile.TemporaryDirectory(prefix="swift-stream-fixture-") as temporary:
            fixture = AppleFixture(Path(temporary) / "fixture")
            fixture.observations["swiftc"] = STDOUT
            evidence = fixture.root / "stream-evidence"
            evidence.mkdir()
            swift_command = apple.toolchain_commands(fixture.binaries)["swiftc"]
            def capture(argv, **kwargs):
                if argv == swift_command:
                    kwargs["log"].write_text(RAW)
                    return RAW
                return fixture.command(argv, **kwargs)
            with patch.object(apple, "capture_helper_command", side_effect=capture):
                observed = apple.bounded_toolchain(fixture.config, fixture.root, {}, fixture.binaries, evidence)
            self.assertEqual(observed["swiftc"], RAW.strip())
            self.assertEqual((evidence / "toolchain-swiftc.txt").read_bytes(), RAW.encode())
            self.assertEqual(fixture.config["observations"]["swiftc"], STDOUT)

    def test_unexpected_swift_output_stops_before_sysroot_or_build(self):
        with tempfile.TemporaryDirectory(prefix="swift-stream-fixture-") as temporary:
            fixture = AppleFixture(Path(temporary) / "fixture")
            fixture.observations["swiftc"] = STDOUT
            evidence = fixture.root / "stream-evidence"
            evidence.mkdir()
            swift_command = apple.toolchain_commands(fixture.binaries)["swiftc"]
            def capture(argv, **kwargs):
                if argv == swift_command:
                    return RAW + "unexpected output"
                return fixture.command(argv, **kwargs)
            with patch.object(apple, "capture_helper_command", side_effect=capture), self.assertRaises(VerificationError):
                apple.bounded_toolchain(fixture.config, fixture.root, {}, fixture.binaries, evidence)
            self.assertFalse(any("--print" in call["argv"] or "build" in call["argv"] for call in fixture.calls))


if __name__ == "__main__":
    unittest.main()
