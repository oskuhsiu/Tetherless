"""Synthetic-byte contract tests. These never claim to build or run an iOS app."""
import copy
import json
import io
import os
from pathlib import Path
import plistlib
import sys
import subprocess
import tempfile
import tarfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contract import (APP_NAME, BUNDLE_PREFIX, EXECUTABLE, LABEL, SOURCE_PATHS,
                      app_inventory, build_identity, classify_signature, info_plist,
                      json_bytes, package_ipa, sha256, validate_platform,
                      validate_provenance, verify_ipa, verify_source_snapshot)

ENV = {
    "GITHUB_RUN_ID": "123456789", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "a" * 40,
    "GITHUB_REPOSITORY": "owned/repository", "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REF": "refs/heads/verify/staged-pairing-native", "GITHUB_EVENT_NAME": "push",
    "GITHUB_WORKFLOW_REF": "owned/repository/.github/workflows/web-signing-test-app.yml@refs/heads/verify/staged-pairing-native",
    "GITHUB_WORKFLOW_SHA": "a" * 40,
}
ADHOC = "CodeDirectory v=20400 size=300 flags=0x20002(adhoc,linker-signed) hashes=4+0 location=embedded\nSignature=adhoc\nTeamIdentifier=not set\n"
LOADS = "Load command 1\n      cmd LC_BUILD_VERSION\n  cmdsize 32\n platform IOS\n    minos 17.0\n      sdk 26.3\nLoad command 2\n cmd LC_MAIN\n"


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.identity = build_identity(ENV)
        self.info = info_plist(self.identity, "26.3", "23D123")
        self.app = self.root / APP_NAME
        self.app.mkdir()
        (self.app / "Info.plist").write_bytes(plistlib.dumps(self.info))
        (self.app / "BuildIdentity.json").write_bytes(json_bytes(self.identity))
        (self.app / EXECUTABLE).write_bytes(b"SYNTHETIC CONTRACT FIXTURE; NOT MACH-O; NOT AN IOS APP")
        for path in self.app.iterdir():
            path.chmod(0o755 if path.name == EXECUTABLE else 0o644)

    def package(self):
        ipa = self.root / "test.ipa"
        return ipa, package_ipa(self.app, ipa, self.identity, self.info)

    def provenance(self):
        ipa, manifest = self.package()
        source = self.root / "source.tar"
        source_manifest = []
        with tarfile.open(source, "w") as archive:
            for relative in (SOURCE_PATHS[1], SOURCE_PATHS[2], SOURCE_PATHS[0] + "/SigningTest.swift"):
                data = b"synthetic source contract fixture"
                member = tarfile.TarInfo(relative)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
                source_manifest.append({"path": relative, "size_bytes": len(data), "sha256": sha256(data)})
        (self.root / "app-manifest.json").write_bytes(json_bytes(manifest))
        (self.root / "source-manifest.json").write_bytes(json_bytes(source_manifest))
        signing = {"label": LABEL, "apple_developer_signed": False, "provisioning_profile_present": False,
                   "embedded_entitlements_present": False, "signature_classification": classify_signature(0, ADHOC),
                   "binary": next(item for item in manifest if item["path"] == EXECUTABLE)}
        (self.root / "binary-inspection.json").write_bytes(json_bytes(signing))
        return {"schema_version": 1, "label": LABEL, "identity": self.identity, "signing": signing,
                "toolchain": {"xcode": "Xcode 26.3\nBuild version FIXTURE", "compiler": "/Applications/Xcode_26.3.app/Contents/Developer/Toolchains/fixture/swiftc",
                              "compiler_version": "synthetic fixture", "compiler_sha256": "c" * 64,
                              "developer_dir": "/Applications/Xcode_26.3.app/Contents/Developer",
                              "resolved_developer_dir": "/Applications/Xcode_26.3.app/Contents/Developer",
                              "resolved_compiler": "/Applications/Xcode_26.3.app/Contents/Developer/Toolchains/fixture/swiftc",
                              "resolved_sdk_path": "/Applications/Xcode_26.3.app/Contents/Developer/Platforms/fixture.sdk",
                              "sdk_path": "/Applications/Xcode_26.3.app/Contents/Developer/Platforms/fixture.sdk",
                              "sdk_version": "26.3", "sdk_build": "23D123", "target": "arm64-apple-ios17.0", "runner_arch": "arm64"},
                "ipa": {"filename": ipa.name, "sha256": sha256(ipa.read_bytes()), "size_bytes": ipa.stat().st_size},
                "source_snapshot": {"filename": source.name, "sha256": sha256(source.read_bytes()), "size_bytes": source.stat().st_size, "scope": list(SOURCE_PATHS)},
                "source_manifest": source_manifest, "app_manifest": manifest}

    def test_identity_is_run_unique_and_attempt_stable(self):
        self.assertEqual(self.identity["bundle_identifier"], BUNDLE_PREFIX + ENV["GITHUB_RUN_ID"])
        other = build_identity(dict(ENV, GITHUB_RUN_ID="123456790"))
        self.assertNotEqual(other["bundle_identifier"], self.identity["bundle_identifier"])
        retry = build_identity(dict(ENV, GITHUB_RUN_ATTEMPT="3"))
        self.assertEqual(retry["bundle_identifier"], self.identity["bundle_identifier"])
        self.assertEqual(retry["run_attempt"], "3")

    def test_rejects_invalid_numeric_ids(self):
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
            for value in ("", "0", "01", "-1", "1.0", "1/evil", " 1", "1\n", "9" * 21):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    build_identity(dict(ENV, **{key: value}))

    def test_rejects_wrong_source_workflow_branch_and_server(self):
        for key, value in (("GITHUB_SHA", "abc"), ("GITHUB_SHA", "A" * 40), ("GITHUB_WORKFLOW_SHA", "b" * 40),
                           ("GITHUB_WORKFLOW_REF", "unrelated"), ("GITHUB_REF", "refs/heads/main"),
                           ("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REPOSITORY", "owner/../repo"),
                           ("GITHUB_SERVER_URL", "https://elsewhere.invalid")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_identity(dict(ENV, **{key: value}))

    def test_minimal_plist_has_no_permissions_or_entitlements(self):
        self.assertEqual(self.info["CFBundleDisplayName"], LABEL)
        self.assertEqual(self.info["MinimumOSVersion"], "17.0")
        self.assertEqual(self.info["CFBundleSupportedPlatforms"], ["iPhoneOS"])
        self.assertFalse(any("UsageDescription" in key or "Entitlement" in key or "Background" in key for key in self.info))

    def test_exact_payload_and_deterministic_zip(self):
        ipa, manifest = self.package()
        second = self.root / "second.ipa"
        package_ipa(self.app, second, self.identity, self.info)
        self.assertEqual(ipa.read_bytes(), second.read_bytes())
        verify_ipa(ipa, manifest)
        with zipfile.ZipFile(ipa) as archive:
            self.assertEqual(len(archive.namelist()), 3)
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.getinfo(f"Payload/{APP_NAME}/{EXECUTABLE}").external_attr >> 16, 0o100755)

    def test_refuses_overwrite(self):
        ipa, _ = self.package()
        with self.assertRaises(ValueError):
            package_ipa(self.app, ipa, self.identity, self.info)

    def test_rejects_profile_signature_folder_entitlements_and_extra_file(self):
        for name in ("embedded.mobileprovision", "_CodeSignature", "Entitlements.plist", "extra.txt"):
            with self.subTest(name=name):
                path = self.app / name
                path.write_bytes(b"forbidden")
                with self.assertRaises(ValueError):
                    app_inventory(self.app, self.identity, self.info)
                path.unlink()

    def test_rejects_symlink_and_wrong_executable_mode(self):
        path = self.app / EXECUTABLE
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            app_inventory(self.app, self.identity, self.info)
        path.unlink()
        path.symlink_to("Info.plist")
        with self.assertRaises(ValueError):
            app_inventory(self.app, self.identity, self.info)

    def test_rejects_embedded_identity_or_plist_mismatch(self):
        (self.app / "BuildIdentity.json").write_bytes(json_bytes(dict(self.identity, source_commit="b" * 40)))
        with self.assertRaises(ValueError):
            app_inventory(self.app, self.identity, self.info)
        (self.app / "BuildIdentity.json").write_bytes(json_bytes(self.identity))
        (self.app / "Info.plist").write_bytes(plistlib.dumps(dict(self.info, CFBundleIdentifier="org.other")))
        with self.assertRaises(ValueError):
            app_inventory(self.app, self.identity, self.info)

    def test_rejects_zip_extras_and_tampered_bytes(self):
        ipa, manifest = self.package()
        pristine = ipa.read_bytes()
        with zipfile.ZipFile(ipa, "a") as archive:
            archive.writestr("Payload/Other.app/file", b"extra")
        with self.assertRaises(ValueError):
            verify_ipa(ipa, manifest)
        ipa.write_bytes(pristine)
        bad_manifest = copy.deepcopy(manifest)
        bad_manifest[0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_ipa(ipa, bad_manifest)

    def test_ad_hoc_is_explicitly_not_developer_signed(self):
        self.assertEqual(classify_signature(0, ADHOC), "linker-ad-hoc; no Apple identity or provisioning")
        self.assertEqual(classify_signature(1, "SigningTest: code object is not signed at all\n"), "no-code-signature; no Apple identity or provisioning")

    def test_rejects_apple_signatures_and_ambiguous_tool_failure(self):
        for code, text in ((0, ADHOC + "Authority=Apple Development\n"), (0, ADHOC.replace("not set", "TEAM123456")),
                           (0, "Signature=adhoc\n"), (0, ADHOC.replace(",linker-signed", "")), (1, "resource envelope invalid"), (2, "code object is not signed at all")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                classify_signature(code, text)

    def test_device_platform_only(self):
        validate_platform("arm64\n", "MH_MAGIC_64 ARM64 ALL EXECUTE", LOADS)
        validate_platform("arm64", "EXECUTE", LOADS.replace("platform IOS", "platform 2"))
        for arch, header, loads in (("arm64 x86_64", "EXECUTE", LOADS), ("arm64", "DYLIB", LOADS),
                                    ("arm64", "EXECUTE", LOADS.replace("platform IOS", "platform IOSSIMULATOR")),
                                    ("arm64", "EXECUTE", LOADS.replace("17.0", "16.0")),
                                    ("arm64", "EXECUTE", LOADS + "cmd LC_ENCRYPTION_INFO_64\n cryptid 1\n")):
            with self.subTest(arch=arch, loads=loads), self.assertRaises(ValueError):
                validate_platform(arch, header, loads)

    def test_provenance_cross_checks_package_and_source(self):
        provenance = self.provenance()
        validate_provenance(provenance, self.root)
        for section, key, value in (("identity", "run_id", "99"), ("identity", "source_commit", "short"),
                                    ("ipa", "sha256", "0" * 64), ("source_snapshot", "size_bytes", 0),
                                    ("toolchain", "compiler_version", ""), ("toolchain", "compiler_sha256", ""),
                                    ("toolchain", "resolved_compiler", "/tmp/swiftc"), ("toolchain", "resolved_sdk_path", "/tmp/SDK"),
                                    ("toolchain", "xcode", "Xcode 99.0"), ("toolchain", "runner_arch", "x86_64"),
                                    ("identity", "repository", "owned/../repository"), ("identity", "source_ref", "refs/heads/main"),
                                    ("identity", "workflow_ref", "other/workflow"), ("identity", "run_url", "https://elsewhere.invalid"),
                                    ("signing", "apple_developer_signed", True)):
            changed = copy.deepcopy(provenance)
            changed[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                validate_provenance(changed, self.root)

    def test_source_snapshot_exact_bytes_and_member_types(self):
        provenance = self.provenance()
        source = self.root / provenance["source_snapshot"]["filename"]
        verify_source_snapshot(source, provenance["source_manifest"])
        wrong = copy.deepcopy(provenance["source_manifest"])
        wrong[0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_source_snapshot(source, wrong)
        with tarfile.open(source, "w") as archive:
            member = tarfile.TarInfo(provenance["source_manifest"][0]["path"])
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            archive.addfile(member)
        with self.assertRaises(ValueError):
            verify_source_snapshot(source, provenance["source_manifest"])

    def test_rejects_zip_duplicate_entries(self):
        import warnings
        ipa, manifest = self.package()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(ipa, "a") as archive:
                archive.writestr(f"Payload/{APP_NAME}/{EXECUTABLE}", b"duplicate")
        with self.assertRaises(ValueError):
            verify_ipa(ipa, manifest)

    def test_rejects_hardlink_empty_and_oversized_binary(self):
        executable = self.app / EXECUTABLE
        link = self.root / "second-link"
        os.link(executable, link)
        with self.assertRaises(ValueError):
            app_inventory(self.app, self.identity, self.info)
        link.unlink()
        executable.write_bytes(b"")
        with self.assertRaises(ValueError):
            app_inventory(self.app, self.identity, self.info)
        with executable.open("wb") as stream:
            stream.truncate(21 * 1024 * 1024)
        with self.assertRaises(ValueError):
            app_inventory(self.app, self.identity, self.info)

    def test_native_build_fails_closed_before_tools_on_wrong_host(self):
        from build import NativeBuild
        checkout = self.root / "checkout"
        checkout.mkdir()
        build = NativeBuild(checkout, self.root / "native-output")
        with mock.patch.dict(os.environ, ENV, clear=True), mock.patch("build.platform.system", return_value="Linux"), mock.patch.object(build, "run") as run:
            with self.assertRaisesRegex(ValueError, "macOS arm64"):
                build.execute()
            run.assert_not_called()
        with self.assertRaisesRegex(ValueError, "outside source checkout"):
            NativeBuild(checkout, checkout / "output")

    def test_source_snapshot_requires_unchanged_root_license(self):
        provenance = self.provenance()
        self.assertIn("LICENSE", [item["path"] for item in provenance["source_manifest"]])
        without_license = [item for item in provenance["source_manifest"] if item["path"] != "LICENSE"]
        with self.assertRaisesRegex(ValueError, "license source"):
            verify_source_snapshot(self.root / provenance["source_snapshot"]["filename"], without_license)

    def test_selected_xcode_alias_preserves_logical_and_resolved_identity(self):
        provenance = self.provenance()
        toolchain = provenance["toolchain"]
        logical = "/Applications/Xcode_26.3.app/Contents/Developer"
        resolved = "/Applications/Xcode_26.3.0.app/Contents/Developer"
        for key in ("resolved_developer_dir", "resolved_compiler", "resolved_sdk_path"):
            toolchain[key] = toolchain[key].replace(logical, resolved)
        validate_provenance(provenance, self.root)
        self.assertEqual(toolchain["developer_dir"], logical)
        toolchain["resolved_sdk_path"] = "/Applications/Xcode_99.app/Contents/Developer/SDK"
        with self.assertRaisesRegex(ValueError, "outside resolved selected Xcode"):
            validate_provenance(provenance, self.root)

    def test_retained_provenance_rejects_absent_compiler_digest(self):
        provenance = self.provenance()
        del provenance["toolchain"]["compiler_sha256"]
        with self.assertRaisesRegex(ValueError, "compiler digest"):
            validate_provenance(provenance, self.root)

    def test_timeout_preserves_partial_logs_and_pending_receipt(self):
        from build import NativeBuild
        checkout = self.root / "checkout"
        checkout.mkdir()
        build = NativeBuild(checkout, self.root / "timeout-output")
        def timeout(*args, **kwargs):
            pending = json.loads((build.evidence / "commands.json").read_bytes())
            self.assertEqual(pending[0]["status"], "running")
            self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
            raise subprocess.TimeoutExpired(args[0], 1, output=b"partial compiler output", stderr=b"partial compiler error")
        with mock.patch("build.subprocess.run", side_effect=timeout), self.assertRaises(subprocess.TimeoutExpired):
            build.run("fixture-timeout", ["fixture-compiler"], timeout=1)
        receipt = json.loads((build.evidence / "commands.json").read_bytes())[0]
        self.assertEqual(receipt["status"], "timeout")
        self.assertIsNone(receipt["returncode"])
        for stream, expected in (("stdout", b"partial compiler output"), ("stderr", b"partial compiler error")):
            self.assertEqual((build.evidence / receipt[stream]["file"]).read_bytes(), expected)
            self.assertEqual(receipt[stream]["sha256"], sha256(expected))
            self.assertEqual(receipt[stream]["size_bytes"], len(expected))

    def test_spawn_error_preserves_failure_receipt(self):
        from build import NativeBuild
        checkout = self.root / "checkout"
        checkout.mkdir()
        build = NativeBuild(checkout, self.root / "spawn-error-output")
        with mock.patch("build.subprocess.run", side_effect=FileNotFoundError(2, "fixture missing")), self.assertRaises(FileNotFoundError):
            build.run("fixture-spawn-error", ["fixture-missing-tool"])
        receipt = json.loads((build.evidence / "commands.json").read_bytes())[0]
        self.assertEqual(receipt["status"], "spawn-error")
        self.assertEqual(receipt["errno"], 2)
        self.assertEqual(receipt["stdout"]["size_bytes"], 0)
        self.assertEqual(receipt["stderr"]["size_bytes"], 0)

    def test_workflow_is_isolated_and_bounded(self):
        workflow = (Path(__file__).resolve().parents[3] / ".github/workflows/web-signing-test-app.yml").read_text()
        self.assertIn("runs-on: macos-15", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("submodules: false", workflow)
        self.assertEqual(workflow.count("python3 Tools/WebSigningTestApp/build.py"), 1)
        for forbidden in ("secrets.", "brew ", "curl ", "sudo ", "simctl", "pull_request:", "release:"):
            self.assertNotIn(forbidden, workflow)
        self.assertIn("'Tools/WebSigningTestApp/**'", workflow)
        self.assertIn("'.github/workflows/web-signing-test-app.yml'", workflow)


if __name__ == "__main__":
    unittest.main()
