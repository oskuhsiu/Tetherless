#!/usr/bin/env python3
"""Run frozen macOS Swift source/registration-spy fixtures; no IDevice or ABI claim."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

EXPECTED = {'Package.swift': 'b4dabe30750779e31a2bf41da3e1a038fe225de9db348e134fc5e7a2e5f01798', 'Sources/TetherlessCore/PairingRecord.swift': 'c484453ca52d76219945d26de3a618b6e75bf4d7e7c4829892240b2e6b738602', 'Sources/TetherlessCore/PrivateFileStore.swift': 'ab506c18e2ae33e2f3a940337909435c86144caeabfdf1393f2813c664626fdb', 'Sources/TetherlessCore/NativeCallLifetime.swift': 'cda4970d622eaf7615a103b257b45b8a02bf37a5a89243ee3a20a90e3d0342d3', 'Sources/TetherlessCore/PairingPromotion.swift': '26a86c9bca1f8147c1d04db8d8f79a5045681672041fed96745b1592e842d6b4', 'Integration/Native/PairingBonjourListener.swift': '7ff0ef8f3c4ae4f5c9381e26cad2a1dccb36c36b8d2c58812f02d416376873d4', 'Tests/TetherlessCoreTests/NativeCallLifetimeTests.swift': '6b121085257e1e1cb074c46666141f59cb0bb7283e23903192deeb95e4c1f2b9', 'Tests/TetherlessCoreTests/PairingPromotionTests.swift': 'a75cd4adf4e5ebee6c28b01baacc4b610926e292c8c048db4b03849f3a7baf41', 'Integration/fixtures/PairingBonjourListenerTests.swift': '774bce87ce9e107047db7b9a307e8a77a8d7339d1bfcc180d5cf77c00b7c54bd', 'Integration/Dependencies/idevice/bounded_process.py': '7724f6c3eb7d624f49a2651b30f1d6e6bb2c47d356449cd495fad28b2dd144e4', 'Integration/Dependencies/idevice/apply_patch.py': '683ab3c727e6a3ccb0c322a38e8e67e3e91f88a54b443d7eb4c5fd667d6fe70d'}
EXPECTED_FIXTURES = ['NativeCallLifetimeTests.testClaimOwnsLifetimeUntilActualReturn', 'NativeCallLifetimeTests.testConcurrentReturnsRunCleanupExactlyOnceOutsideLock', 'NativeCallLifetimeTests.testQueuedHandshakeAndConcurrentCancellationBothJoinBeforeCleanup', 'PairingBonjourListenerTests.testAcceptedDescriptorWaitsForBothStopAcknowledgementsInEitherOrder', 'PairingBonjourListenerTests.testCancellationBeforeStartNeverCreatesPublisherOrListener', 'PairingBonjourListenerTests.testCancellationWhileStoppingClosesAcceptedSocketAndStillJoins', 'PairingBonjourListenerTests.testFailedPublicationStillCallsStopAndWaitsForItsAcknowledgement', 'PairingBonjourListenerTests.testSocketCanTransferOnlyOnceAndDuplicateDisposalCannotCloseActiveCall', 'PairingBonjourListenerTests.testStopAcknowledgementCannotOvertakeQueuedAcceptedDescriptorCleanup', 'PairingBonjourListenerTests.testTXTFailureRemovesBothDefaultAndExplicitScheduleWithoutPublishing', 'PairingPromotionTests.testCancellationWaitsForValidatorReturnAndRejectsStalePIN', 'PairingPromotionTests.testCancellationWhileReadingOriginalDoesNotEnterValidator', 'PairingPromotionTests.testCancelledBeforeStartAndNewGenerationCannotReuseOldPIN', 'PairingPromotionTests.testExactlyValidatedBytesAreCommittedOnceAndLateCancelCannotUndoCommit', 'PairingPromotionTests.testPostRenameFailureRequiresRecoveryAndPreRenameFailurePreservesOld', 'PairingPromotionTests.testProtectedStorePreservesOldBeforeRenameAndRequiresRecoveryAfterRename', 'PairingPromotionTests.testSwiftTaskCancellationThrownByValidatorIsReportedAsCancelled', 'PairingPromotionTests.testUnreadableReconciliationAndChangedTargetNeverClaimRollback', 'PairingPromotionTests.testValidationFailurePreservesOldRecordAndNeverCommits']
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_LOG_BYTES = 16 * 1024 * 1024


def sha(data): return hashlib.sha256(data).hexdigest()


def plain_directory(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in [path, *path.parents]) or not path.is_dir():
        raise ValueError("directory missing or has a symlink component")
    return path


def read_inputs(root):
    root = plain_directory(root)
    result = {}
    for relative, expected in EXPECTED.items():
        path = root
        for part in Path(relative).parts:
            path = path / part
            if path.is_symlink(): raise ValueError("source symlink")
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES:
            raise ValueError("source missing or oversized")
        with path.open("rb") as stream: data = stream.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES or sha(data) != expected:
            raise ValueError("source identity mismatch")
        result[relative] = data
    return result


def fixture_summary(text):
    # Darwin XCTest and SwiftPM's dot form both occur. Repeated aggregate suite
    # summaries are normal; repeated successful fixture lines are deduplicated.
    records = re.findall(r"Test Case '-\[(?:[A-Za-z0-9_]+\.)?([A-Za-z0-9_]+) ([A-Za-z0-9_]+)\]' (passed|failed|skipped)", text)
    records += re.findall(r"Test Case '(?:[A-Za-z0-9_]+\.)?([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)' (passed|failed|skipped)", text)
    passed = {c + "." + n for c, n, state in records if state == "passed"}
    bad = {c + "." + n for c, n, state in records if state != "passed"}
    totals = [(int(n), int(f)) for n, f in re.findall(r"Executed (\d+) tests?, with (\d+) failures", text)]
    suites = re.findall(r"Test Suite 'All tests' (passed|failed)", text)
    expected = set(EXPECTED_FIXTURES)
    return {"passed": passed == expected and not bad and bool(suites) and all(s == "passed" for s in suites)
                      and (len(expected), 0) in totals and all(f == 0 for _, f in totals),
            "unique_passed_fixtures": sorted(passed), "failed_or_skipped_fixtures": sorted(bad),
            "missing_fixtures": sorted(expected - passed), "unexpected_fixtures": sorted(passed - expected),
            "aggregate_summaries": [{"tests": n, "failures": f} for n, f in totals],
            "all_tests_suite_outcomes": suites}


def load_supervisor(directory):
    # The exact supervisor imports only VerificationError from the exact staging
    # module. Load both verified snapshots; never a same-named ambient module.
    previous = sys.modules.get("apply_patch")
    try:
        spec = importlib.util.spec_from_file_location("apply_patch", directory / "apply_patch.py")
        errors = importlib.util.module_from_spec(spec)
        sys.modules["apply_patch"] = errors
        spec.loader.exec_module(errors)
        spec = importlib.util.spec_from_file_location("pairing_swift_supervisor", directory / "bounded_process.py")
        supervisor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(supervisor)
        return supervisor.capture_helper_command
    finally:
        if previous is None: sys.modules.pop("apply_patch", None)
        else: sys.modules["apply_patch"] = previous


def verify(source_root, output_root, *, runner=None, platform=None):
    selected_platform = sys.platform if platform is None else platform
    output = Path(output_root).absolute()
    plain_directory(output.parent)
    if output.exists() or output.is_symlink(): raise ValueError("output directory must be new")
    output.mkdir(mode=0o700)
    report = {"schema_version": 1, "status": "pending", "evidence": "Swift source fixtures only; no FFI ABI or device proof",
              "runner": "selected_Apple_toolchain" if runner is None else "injected_test_double",
              "expected_unique_fixtures": EXPECTED_FIXTURES, "phases": {}, "source_hashes": EXPECTED}
    scratch = None
    safe_cleanup = True
    try:
        if selected_platform != "darwin":
            report["status"] = "unsupported_platform"
            return report
        inputs = read_inputs(source_root)
        scratch = Path(tempfile.mkdtemp(prefix="tetherless-host-app-swift-")).resolve()
        package, supervisor = scratch / "package", scratch / "supervisor"
        package.mkdir(); supervisor.mkdir()
        for relative, data in inputs.items():
            if relative.startswith("Integration/Dependencies/idevice/"):
                destination = supervisor / Path(relative).name
            elif relative == "Integration/Native/PairingBonjourListener.swift":
                destination = package / "Sources/TetherlessCore/PairingBonjourListener.swift"
            elif relative == "Integration/fixtures/PairingBonjourListenerTests.swift":
                destination = package / "Tests/TetherlessCoreTests/PairingBonjourListenerTests.swift"
            else: destination = package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        invoke = load_supervisor(supervisor) if runner is None else runner
        environment = os.environ.copy()

        def phase(name, command):
            nonlocal safe_cleanup
            read_inputs(source_root)
            log = output / (name + ".log")
            caught = None
            interrupted_exception = False
            # Until a final status proves quiescence, no scratch may be removed,
            # even if reading/parsing that status itself fails.
            safe_cleanup = False
            try:
                invoke(command, source=package, env=environment, log=log, timeout_seconds=60,
                       max_log_bytes=MAX_LOG_BYTES, tail_bytes=128 * 1024,
                       term_grace_seconds=5, kill_join_seconds=5)
            except BaseException as error:
                caught = type(error).__name__
                interrupted_exception = isinstance(error, (KeyboardInterrupt, SystemExit))
            status_path = log.with_name(log.name + ".status.json")
            status = json.loads(status_path.read_bytes()) if status_path.is_file() else {"outcome": "supervision_unavailable"}
            cleanup = status.get("cleanup") or {}
            joined = cleanup.get("direct_child_reaped") is True and cleanup.get("group_empty") is True
            # A missing PID is not proof that Popen never created a child. This
            # supervisor has no affirmative never-created field, so retain even
            # a launch-failure scratch tree unless joined evidence is present.
            safe_cleanup = joined
            raw = log.read_bytes() if log.is_file() else b""
            if len(raw) > MAX_LOG_BYTES: raise ValueError("supervisor log exceeds cap")
            item = {"command": command, "supervisor_status": status, "caught_exception_class": caught,
                    "interrupted_exception": interrupted_exception,
                    "log": {"file": log.name, "sha256": sha(raw)},
                    "status_file": status_path.name,
                    "tool_passed": caught is None and status.get("outcome") == "success" and
                        status.get("returncode") == 0 and cleanup.get("direct_child_reaped") is True and
                        cleanup.get("group_empty") is True and status.get("output_complete") is True}
            report["phases"][name] = item
            read_inputs(source_root)
            return raw.decode("utf-8", "replace"), item

        # First exercise the source. Metadata observation does not introduce a
        # new preflight barrier ahead of the actual fixture commands.
        all_passed = True
        for configuration in ["debug", "release"]:
            text, item = phase(configuration, ["/usr/bin/xcrun", "--sdk", "macosx", "swift", "test",
                "--package-path", str(package), "-c", configuration,
                "-Xswiftc", "-DTETHERLESS_BOUNDED_PAIRING_HOST"])
            item["fixtures"] = fixture_summary(text)
            item["passed"] = bool(item["tool_passed"] and item["fixtures"]["passed"])
            all_passed = all_passed and item["passed"]
            if not safe_cleanup or item["supervisor_status"].get("outcome") == "interrupted" or item["interrupted_exception"]:
                report["status"] = "cleanup_incomplete" if not safe_cleanup else "interrupted"
                return report
        for name, arguments in [("tool_path", ["--find", "swift"]), ("tool_version", ["swift", "--version"])]:
            text, item = phase(name, ["/usr/bin/xcrun", "--sdk", "macosx", *arguments])
            item["observed_metadata"] = text.strip()
            all_passed = all_passed and item["tool_passed"] and bool(text.strip())
            if not safe_cleanup or item["supervisor_status"].get("outcome") == "interrupted" or item["interrupted_exception"]:
                report["status"] = "cleanup_incomplete" if not safe_cleanup else "interrupted"
                return report
        read_inputs(source_root)
        report["status"] = "passed" if all_passed else "fixture_or_metadata_failure"
        return report
    except (KeyboardInterrupt, SystemExit):
        report["status"] = "interrupted" if safe_cleanup else "cleanup_incomplete"
        return report
    except (ValueError, OSError) as error:
        report["status"] = "input_or_output_failure" if safe_cleanup else "cleanup_incomplete"
        report["failure_class"] = type(error).__name__
        return report
    finally:
        if scratch is not None:
            if safe_cleanup:
                try:
                    shutil.rmtree(scratch)
                    report["scratch_removed_after_join"] = True
                except OSError as error:
                    report["scratch_removed_after_join"] = False
                    report["retained_scratch"] = str(scratch)
                    report["scratch_cleanup_failure"] = type(error).__name__
                    if report["status"] == "passed": report["status"] = "scratch_cleanup_failure"
            else:
                report["scratch_removed_after_join"] = False
                report["retained_scratch"] = str(scratch)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    report = verify(args.source_root, args.output_root)
    print(json.dumps({"status": report["status"], "report": str(args.output_root / "report.json")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__": raise SystemExit(main())
