#!/usr/bin/env python3
"""One offline native arm64 build. Requires the approved GitHub macOS runner."""
import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys

from contract import (APP_NAME, EXECUTABLE, LABEL, SOURCE_PATHS, app_inventory,
                      build_identity, classify_signature, info_plist, json_bytes,
                      package_ipa, require, sha256, validate_platform, validate_provenance)

DEVELOPER_DIR = "/Applications/Xcode_26.3.app/Contents/Developer"


class NativeBuild:
    def __init__(self, repository, output):
        self.repository = repository.resolve(strict=True)
        require(not output.exists() and not output.is_symlink(), "output must be new")
        self.output = output.resolve()
        require(not self.output.is_relative_to(self.repository), "output must be outside source checkout")
        self.output.mkdir(parents=True)
        self.evidence = self.output / "evidence"
        self.evidence.mkdir()
        self.work = self.output / "work"
        for name in ("home", "tmp", "module-cache"):
            (self.work / name).mkdir(parents=True)
        self.env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.work / "home"),
            "TMPDIR": str(self.work / "tmp"),
            "DEVELOPER_DIR": DEVELOPER_DIR,
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
        }
        self.commands = []

    def save_commands(self):
        temporary = self.evidence / "commands.json.pending"
        with temporary.open("wb") as stream:
            stream.write(json_bytes(self.commands))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.evidence / "commands.json")

    def retain_streams(self, receipt, stdout, stderr):
        for stream, data in (("stdout", stdout or b""), ("stderr", stderr or b"")):
            path = self.evidence / f"{len(self.commands):02d}-{receipt['name']}.{stream}"
            path.write_bytes(data)
            receipt[stream] = {"file": path.name, "size_bytes": len(data), "sha256": sha256(data)}

    def run(self, name, argv, *, allow_failure=False, timeout=60, binary=False):
        receipt = {"name": name, "argv": [str(arg) for arg in argv], "timeout_seconds": timeout, "status": "running"}
        self.commands.append(receipt)
        self.save_commands()  # A later runner/step kill still identifies the pending command.
        try:
            result = subprocess.run(receipt["argv"], cwd=self.repository, env=self.env,
                                    capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            receipt.update(status="timeout", returncode=None)
            self.retain_streams(receipt, error.stdout, error.stderr)
            self.save_commands()
            raise
        except OSError as error:
            receipt.update(status="spawn-error", returncode=None, errno=error.errno, error=str(error))
            self.retain_streams(receipt, b"", b"")
            self.save_commands()
            raise
        self.retain_streams(receipt, result.stdout, result.stderr)
        receipt.update(returncode=result.returncode, status="passed" if result.returncode == 0 else "failed")
        self.save_commands()
        if not allow_failure:
            require(result.returncode == 0, f"{name} failed (see retained evidence)")
        return result if binary else (result.returncode, result.stdout.decode("utf-8", errors="strict"), result.stderr.decode("utf-8", errors="strict"))

    def execute(self):
        identity = build_identity(os.environ)
        (self.evidence / "build-identity.json").write_bytes(json_bytes(identity))
        require(platform.system() == "Darwin" and platform.machine() == "arm64", "requires macOS arm64 runner")
        require(os.environ.get("DEVELOPER_DIR") == DEVELOPER_DIR and Path(DEVELOPER_DIR).is_dir(), "expected installed Xcode 26.3")
        require(os.environ.get("GITHUB_ACTIONS") == "true", "native evidence requires GitHub Actions")
        resolved_developer = Path(DEVELOPER_DIR).resolve(strict=True)
        _, head, _ = self.run("git-head", ["/usr/bin/git", "rev-parse", "HEAD"])
        require(head.strip() == identity["source_commit"], "checked-out commit mismatch")
        _, status, _ = self.run("git-status", ["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"])
        require(not status, "source checkout must be clean")
        _, tracked, _ = self.run("source-paths", ["/usr/bin/git", "ls-files", "-z", "--", *SOURCE_PATHS])
        paths = sorted(path for path in tracked.split("\0") if path)
        require(paths and SOURCE_PATHS[1] in paths, "missing tracked source/workflow")
        source_manifest = []
        for relative in paths:
            path = self.repository / relative
            require(path.is_file() and not path.is_symlink(), "source must be regular files")
            data = path.read_bytes()
            source_manifest.append({"path": relative, "size_bytes": len(data), "sha256": sha256(data)})
        snapshot = self.run("source-snapshot", ["/usr/bin/git", "archive", "--format=tar", "HEAD", *SOURCE_PATHS], binary=True).stdout

        _, xcode, _ = self.run("xcode-version", ["/usr/bin/xcodebuild", "-version"])
        require(xcode.splitlines()[0] == "Xcode 26.3", "unexpected Xcode version")
        _, compiler, _ = self.run("compiler-path", ["/usr/bin/xcrun", "--sdk", "iphoneos", "--find", "swiftc"])
        compiler = compiler.strip()
        resolved_compiler = Path(compiler).resolve(strict=True)
        require(resolved_compiler.is_relative_to(resolved_developer), "compiler outside selected Xcode")
        _, compiler_version, _ = self.run("compiler-version", [compiler, "--version"])
        _, sdk_path, _ = self.run("sdk-path", ["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-path"])
        sdk_path = sdk_path.strip()
        resolved_sdk = Path(sdk_path).resolve(strict=True)
        require(resolved_sdk.is_relative_to(resolved_developer), "SDK outside selected Xcode")
        _, sdk_version, _ = self.run("sdk-version", ["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-version"])
        _, sdk_build, _ = self.run("sdk-build", ["/usr/bin/xcrun", "--sdk", "iphoneos", "--show-sdk-build-version"])
        sdk_version, sdk_build = sdk_version.strip(), sdk_build.strip()
        expected_plist = info_plist(identity, sdk_version, sdk_build)
        app = self.work / APP_NAME
        app.mkdir()
        (app / "Info.plist").write_bytes(plistlib.dumps(expected_plist, fmt=plistlib.FMT_XML, sort_keys=True))
        (app / "BuildIdentity.json").write_bytes(json_bytes(identity))
        binary = app / EXECUTABLE
        self.run("compile-one-device-app", [compiler, "-target", "arm64-apple-ios17.0", "-sdk", sdk_path,
                 "-parse-as-library", "-emit-executable", "-module-name", "WebSigningTestApp", "-O",
                 "-module-cache-path", self.work / "module-cache", "-framework", "UIKit", "-framework", "Foundation",
                 "-Xlinker", "-rpath", "-Xlinker", "/usr/lib/swift",
                 self.repository / "Tools/WebSigningTestApp/SigningTest.swift", "-o", binary], timeout=180)
        binary.chmod(0o755)
        for name in ("Info.plist", "BuildIdentity.json"):
            (app / name).chmod(0o644)
        _, architectures, _ = self.run("architectures", ["/usr/bin/xcrun", "lipo", "-archs", binary])
        _, header, _ = self.run("mach-header", ["/usr/bin/xcrun", "otool", "-hv", binary])
        _, loads, _ = self.run("load-commands", ["/usr/bin/xcrun", "otool", "-l", binary])
        _, libraries, _ = self.run("linked-libraries", ["/usr/bin/xcrun", "otool", "-L", binary])
        validate_platform(architectures, header, loads)
        code, stdout, stderr = self.run("signature-display", ["/usr/bin/codesign", "-d", "--verbose=4", binary], allow_failure=True)
        signature = classify_signature(code, stdout + stderr)
        if code == 0:
            self.run("ad-hoc-integrity", ["/usr/bin/codesign", "--verify", "--strict", binary])
            _, entitlements, _ = self.run("entitlements", ["/usr/bin/codesign", "-d", "--entitlements", ":-", binary])
            require(not entitlements.strip() or plistlib.loads(entitlements.encode()) == {}, "unexpected embedded entitlements")
        manifest = app_inventory(app, identity, expected_plist)
        _, final_status, _ = self.run("final-source-status", ["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"])
        require(not final_status, "source changed during build")
        complete = self.output / "complete"
        complete.mkdir()
        ipa = complete / "Signing-test-app-not-Tetherless.ipa"
        require(package_ipa(app, ipa, identity, expected_plist) == manifest, "app changed while packaging")
        snapshot_name = "signing-test-source.tar"
        (complete / snapshot_name).write_bytes(snapshot)
        (complete / "source-manifest.json").write_bytes(json_bytes(source_manifest))
        (complete / "app-manifest.json").write_bytes(json_bytes(manifest))
        native_evidence = {
            "label": LABEL, "architectures": architectures.strip(), "platform": "iOS device", "deployment_target": "17.0",
            "signature_classification": signature, "apple_developer_signed": False, "provisioning_profile_present": False,
            "embedded_entitlements_present": False, "linked_libraries": libraries,
            "binary": next(item for item in manifest if item["path"] == EXECUTABLE),
            "introspection": "Apple lipo, otool, codesign; no custom Mach-O parser",
        }
        (complete / "binary-inspection.json").write_bytes(json_bytes(native_evidence))
        provenance = {
            "schema_version": 1, "label": LABEL, "identity": identity,
            "scope": "owned custom-IPA web signing fixture only",
            "evidence_level": "unsigned device-target compile and package; never installed or launched",
            "limitations": ["Not the Tetherless application", "No product, pairing, renewal, unattended-operation, or install-readiness claim",
                            "Portable tests use synthetic bytes and do not validate native compilation"],
            "signing": native_evidence,
            "authorization_gate": "Owner must approve exact Apple Team, device, App ID, certificate action, and provisioning profile before any provisioning or signing mutation",
            "toolchain": {"developer_dir": DEVELOPER_DIR, "resolved_developer_dir": str(resolved_developer),
                          "resolved_compiler": str(resolved_compiler), "resolved_sdk_path": str(resolved_sdk),
                          "xcode": xcode.strip(), "compiler": compiler,
                          "compiler_version": compiler_version.strip(), "compiler_sha256": sha256(Path(compiler).read_bytes()), "sdk_path": sdk_path, "sdk_version": sdk_version,
                          "sdk_build": sdk_build, "target": "arm64-apple-ios17.0", "runner_os": platform.platform(),
                          "runner_arch": platform.machine(), "python_version": platform.python_version(), "python_executable": sys.executable, "image_os": os.environ.get("ImageOS"), "image_version": os.environ.get("ImageVersion")},
            "ipa": {"filename": ipa.name, "size_bytes": ipa.stat().st_size, "sha256": sha256(ipa.read_bytes())},
            "source_snapshot": {"filename": snapshot_name, "scope": list(SOURCE_PATHS), "sha256": sha256(snapshot), "size_bytes": len(snapshot)},
            "source_manifest": source_manifest, "app_manifest": manifest,
        }
        validate_provenance(provenance, complete)
        (complete / "provenance.json").write_bytes(json_bytes(provenance))
        checksums = "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sorted(complete.iterdir()))
        (complete / "SHA256SUMS").write_text(checksums)
        return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build = NativeBuild(args.repository, args.output)
    status = {"label": LABEL, "status": "running", "native_compile_and_package_passed": False}
    (build.evidence / "status.json").write_bytes(json_bytes(status))
    try:
        status["identity"] = build.execute()
        status.update(status="passed", native_compile_and_package_passed=True)
    except Exception as error:
        status.update(status="failed", error=str(error))
        raise
    finally:
        build.save_commands()
        (build.evidence / "status.json").write_bytes(json_bytes(status))


if __name__ == "__main__":
    main()
