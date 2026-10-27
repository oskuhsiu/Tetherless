"""Portable packaging contracts for the owned signing test fixture only."""
import hashlib
import json
from pathlib import Path
import plistlib
import re
import stat
import tarfile
import zipfile

LABEL = "Signing test app, not Tetherless"
APP_NAME = "SigningTest.app"
EXECUTABLE = "SigningTest"
BUNDLE_PREFIX = "org.tetherless.signingtest.r"
SOURCE_PATHS = ("Tools/WebSigningTestApp", ".github/workflows/web-signing-test-app.yml", "LICENSE")
MAX_FILE_BYTES = 20 * 1024 * 1024
FILES = {"Info.plist", "BuildIdentity.json", EXECUTABLE}
ALLOWED_REFS = {"refs/heads/develop", "refs/heads/verify/staged-pairing-native"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def build_identity(env):
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[1-9][0-9]{0,19}", env.get(key, "")), f"invalid {key}")
    require(re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", "")), "invalid full source commit")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", env.get("GITHUB_REPOSITORY", "")), "invalid repository")
    require(env.get("GITHUB_SERVER_URL") == "https://github.com", "unexpected GitHub server")
    require(env.get("GITHUB_REF") in ALLOWED_REFS, "unapproved branch")
    require(env.get("GITHUB_EVENT_NAME") in {"push", "workflow_dispatch"}, "unapproved event")
    expected_workflow = f"{env['GITHUB_REPOSITORY']}/.github/workflows/web-signing-test-app.yml@{env['GITHUB_REF']}"
    require(env.get("GITHUB_WORKFLOW_REF") == expected_workflow, "unexpected workflow identity")
    require(env.get("GITHUB_WORKFLOW_SHA") == env["GITHUB_SHA"], "workflow/source SHA mismatch")
    return {
        "label": LABEL,
        "source_commit": env["GITHUB_SHA"],
        "repository": env["GITHUB_REPOSITORY"],
        "source_ref": env["GITHUB_REF"],
        "event": env["GITHUB_EVENT_NAME"],
        "workflow_ref": env["GITHUB_WORKFLOW_REF"],
        "workflow_commit": env["GITHUB_WORKFLOW_SHA"],
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": env["GITHUB_RUN_ATTEMPT"],
        "run_url": f"https://github.com/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}/attempts/{env['GITHUB_RUN_ATTEMPT']}",
        "bundle_identifier": BUNDLE_PREFIX + env["GITHUB_RUN_ID"],
    }


def info_plist(identity, sdk_version, sdk_build):
    require(re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", sdk_version), "invalid SDK version")
    require(re.fullmatch(r"[A-Za-z0-9]+", sdk_build), "invalid SDK build")
    return {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": LABEL,
        "CFBundleExecutable": EXECUTABLE,
        "CFBundleIdentifier": identity["bundle_identifier"],
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "SigningTest",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "DTPlatformName": "iphoneos",
        "DTSDKName": "iphoneos" + sdk_version,
        "DTSDKBuild": sdk_build,
        "MinimumOSVersion": "17.0",
        "LSRequiresIPhoneOS": True,
        "UIDeviceFamily": [1, 2],
        "UIRequiredDeviceCapabilities": ["arm64"],
        "UILaunchScreen": {},
        "UIApplicationSceneManifest": {"UIApplicationSupportsMultipleScenes": False},
        "UISupportedInterfaceOrientations": ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
    }


def app_inventory(app, identity, expected_plist):
    app = Path(app)
    require(app.is_dir() and not app.is_symlink() and app.name == APP_NAME, "invalid app directory")
    require({p.name for p in app.iterdir()} == FILES, "unexpected or missing app content; no profiles, entitlements, resources, or nested code allowed")
    manifest = []
    for name in sorted(FILES):
        path = app / name
        st = path.lstat()
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, f"not a unique regular file: {name}")
        require(0 < st.st_size <= MAX_FILE_BYTES, f"invalid file size: {name}")
        expected_mode = 0o755 if name == EXECUTABLE else 0o644
        require(stat.S_IMODE(st.st_mode) == expected_mode, f"unexpected mode: {name}")
        data = path.read_bytes()
        manifest.append({"path": name, "size_bytes": len(data), "sha256": sha256(data), "mode": f"{expected_mode:04o}"})
    require(plistlib.loads((app / "Info.plist").read_bytes()) == expected_plist, "Info.plist differs from exact build contract")
    require(json.loads((app / "BuildIdentity.json").read_bytes()) == identity, "embedded identity mismatch")
    return manifest


def package_ipa(app, output, identity, expected_plist):
    manifest = app_inventory(app, identity, expected_plist)
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), "refusing to replace IPA")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in manifest:
            entry = zipfile.ZipInfo(f"Payload/{APP_NAME}/{item['path']}", date_time=(2001, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | int(item["mode"], 8)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, (Path(app) / item["path"]).read_bytes())
    verify_ipa(output, manifest)
    return manifest


def verify_ipa(path, manifest):
    expected = {f"Payload/{APP_NAME}/{item['path']}": item for item in manifest}
    require(len(expected) == len(FILES), "invalid manifest")
    with zipfile.ZipFile(path) as archive:
        require(len(archive.infolist()) == len(expected) and set(archive.namelist()) == set(expected), "IPA entry mismatch")
        for entry in archive.infolist():
            item = expected[entry.filename]
            require(entry.file_size == item["size_bytes"] and 0 < entry.file_size <= MAX_FILE_BYTES, "IPA size mismatch")
            require(entry.external_attr >> 16 == stat.S_IFREG | int(item["mode"], 8), "IPA mode mismatch")
            require(not entry.flag_bits & 1, "encrypted IPA entry")
            require(sha256(archive.read(entry)) == item["sha256"], "IPA digest mismatch")


def classify_signature(returncode, output):
    """Classify standard codesign output; never treats ad hoc as Apple-signed."""
    require("Authority=" not in output, "unexpected signing authority")
    teams = re.findall(r"^TeamIdentifier=(.*)$", output, flags=re.MULTILINE)
    require(all(team == "not set" for team in teams), "unexpected Apple team")
    if returncode == 0:
        require(re.search(r"^Signature=adhoc$", output, re.MULTILINE), "expected linker ad-hoc signature")
        require(re.search(r"^CodeDirectory .*flags=0x[0-9a-f]+\([^\n]*adhoc[^\n]*\)", output, re.MULTILINE), "missing ad-hoc code-directory flag")
        require(re.search(r"^CodeDirectory .*\([^\n]*\blinker-signed\b[^\n]*\)", output, re.MULTILINE), "ad-hoc signature is not linker-labeled")
        return "linker-ad-hoc; no Apple identity or provisioning"
    require(returncode == 1 and "code object is not signed at all" in output, "codesign inspection failed unexpectedly")
    return "no-code-signature; no Apple identity or provisioning"


def validate_platform(architectures, header, load_commands):
    require(architectures.strip() == "arm64", "expected one device arm64 slice")
    require(re.search(r"\bEXECUTE\b", header), "expected MH_EXECUTE")
    blocks = re.findall(r"\bcmd LC_BUILD_VERSION\n(.*?)(?=Load command |\Z)", load_commands, re.DOTALL)
    require(len(blocks) == 1, "expected one modern platform load command")
    require(re.search(r"^\s*platform (?:2|IOS)\s*$", blocks[0], re.MULTILINE), "expected iOS device platform")
    require(re.search(r"^\s*minos 17\.0(?:\.0)?\s*$", blocks[0], re.MULTILINE), "unexpected deployment target")
    cryptids = re.findall(r"^\s*cryptid (\d+)\s*$", load_commands, re.MULTILINE)
    require(all(value == "0" for value in cryptids), "encrypted binary")
    require("LC_ENCRYPTION_INFO" not in load_commands or cryptids, "missing encryption identity")


def verify_source_snapshot(path, manifest):
    require(0 < Path(path).stat().st_size <= 4 * 1024 * 1024, "source snapshot is not bounded")
    expected = {}
    for item in manifest:
        relative = item["path"]
        require(relative in SOURCE_PATHS[1:] or relative.startswith(SOURCE_PATHS[0] + "/"), "unexpected source path")
        require(".." not in relative.split("/") and "\\" not in relative and not relative.startswith("/"), "unsafe source path")
        require(relative not in expected, "duplicate source manifest path")
        require(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) and 0 < item["size_bytes"] <= 1024 * 1024, "invalid source entry")
        expected[relative] = item
    require(all(path in expected for path in SOURCE_PATHS[1:]) and SOURCE_PATHS[0] + "/SigningTest.swift" in expected, "missing owned app/workflow/license source")
    observed = set()
    with tarfile.open(path, mode="r:") as archive:
        for member in archive:
            if member.isdir():
                require(any(name.startswith(member.name.rstrip("/") + "/") for name in expected), "unexpected source directory")
                continue
            require(member.isfile() and member.name in expected and member.name not in observed, "unexpected source archive member")
            item = expected[member.name]
            require(member.size == item["size_bytes"], "source member size mismatch")
            require(sha256(archive.extractfile(member).read()) == item["sha256"], "source member digest mismatch")
            observed.add(member.name)
    require(observed == set(expected), "source snapshot missing files")


def validate_provenance(provenance, complete):
    """Cross-check retained package identity and hashes; not native execution proof."""
    complete = Path(complete)
    require(provenance["schema_version"] == 1 and provenance["label"] == LABEL, "provenance schema/label mismatch")
    identity = provenance["identity"]
    identity_env = {
        "GITHUB_RUN_ID": identity["run_id"], "GITHUB_RUN_ATTEMPT": identity["run_attempt"],
        "GITHUB_SHA": identity["source_commit"], "GITHUB_REPOSITORY": identity["repository"],
        "GITHUB_SERVER_URL": "https://github.com", "GITHUB_REF": identity["source_ref"],
        "GITHUB_EVENT_NAME": identity["event"], "GITHUB_WORKFLOW_REF": identity["workflow_ref"],
        "GITHUB_WORKFLOW_SHA": identity["workflow_commit"],
    }
    require(identity == build_identity(identity_env), "retained CI identity mismatch")
    require(identity["label"] == LABEL, "identity label mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", identity["source_commit"]), "full commit missing")
    require(re.fullmatch(r"[1-9][0-9]{0,19}", identity["run_id"]), "run identity missing")
    require(re.fullmatch(r"[1-9][0-9]{0,19}", identity["run_attempt"]), "run attempt missing")
    require(identity["bundle_identifier"] == BUNDLE_PREFIX + identity["run_id"], "bundle/run mismatch")
    require(identity["workflow_commit"] == identity["source_commit"], "workflow/source mismatch")
    for key in ("ipa", "source_snapshot"):
        descriptor = provenance[key]
        require(Path(descriptor["filename"]).name == descriptor["filename"], "unsafe artifact filename")
        file = complete / descriptor["filename"]
        require(file.is_file() and not file.is_symlink(), "artifact missing")
        require(file.stat().st_size == descriptor["size_bytes"] and sha256(file.read_bytes()) == descriptor["sha256"], "artifact hash/size mismatch")
    manifest = provenance["app_manifest"]
    require({item["path"] for item in manifest} == FILES and len(manifest) == len(FILES), "unexpected app manifest")
    require(provenance["source_snapshot"]["scope"] == list(SOURCE_PATHS), "source scope mismatch")
    require(provenance["source_manifest"] == json.loads((complete / "source-manifest.json").read_bytes()), "source manifest mismatch")
    verify_source_snapshot(complete / provenance["source_snapshot"]["filename"], provenance["source_manifest"])
    require(manifest == json.loads((complete / "app-manifest.json").read_bytes()), "app manifest mismatch")
    toolchain = provenance["toolchain"]
    for key in ("xcode", "compiler", "compiler_version", "sdk_path", "sdk_version", "sdk_build", "runner_arch", "resolved_developer_dir", "resolved_compiler", "resolved_sdk_path"):
        require(isinstance(toolchain[key], str) and toolchain[key], f"missing toolchain identity: {key}")
    require(toolchain["target"] == "arm64-apple-ios17.0" and toolchain["runner_arch"] == "arm64", "target/runner mismatch")
    require(re.fullmatch(r"[0-9a-f]{64}", toolchain.get("compiler_sha256", "")), "missing compiler digest")
    expected_developer = "/Applications/Xcode_26.3.app/Contents/Developer"
    require(toolchain["developer_dir"] == expected_developer, "developer directory mismatch")
    require(toolchain["xcode"].splitlines()[0] == "Xcode 26.3", "Xcode identity mismatch")
    resolved_developer = Path(toolchain["resolved_developer_dir"])
    require(resolved_developer.is_absolute() and ".." not in resolved_developer.parts and resolved_developer.parts[-2:] == ("Contents", "Developer"), "resolved developer path mismatch")
    for key in ("compiler", "sdk_path", "resolved_compiler", "resolved_sdk_path"):
        path = Path(toolchain[key])
        require(path.is_absolute() and ".." not in path.parts, "toolchain path mismatch")
        if key.startswith("resolved_"):
            require(path.is_relative_to(resolved_developer) and path != resolved_developer, "toolchain outside resolved selected Xcode")
    signing = provenance["signing"]
    require(signing["label"] == LABEL and signing["apple_developer_signed"] is False and signing["provisioning_profile_present"] is False
            and signing["embedded_entitlements_present"] is False, "unexpected signing claim")
    require(signing["signature_classification"] in {"linker-ad-hoc; no Apple identity or provisioning", "no-code-signature; no Apple identity or provisioning"}, "unexpected signature classification")
    require(signing["binary"] == next(item for item in manifest if item["path"] == EXECUTABLE), "binary digest mismatch")
    require(signing == json.loads((complete / "binary-inspection.json").read_bytes()), "binary inspection mismatch")
    ipa = complete / provenance["ipa"]["filename"]
    verify_ipa(ipa, manifest)
    with zipfile.ZipFile(ipa) as archive:
        require(json.loads(archive.read(f"Payload/{APP_NAME}/BuildIdentity.json")) == identity, "IPA embedded identity mismatch")
        expected_info = info_plist(identity, toolchain["sdk_version"], toolchain["sdk_build"])
        require(plistlib.loads(archive.read(f"Payload/{APP_NAME}/Info.plist")) == expected_info, "IPA Info.plist mismatch")
