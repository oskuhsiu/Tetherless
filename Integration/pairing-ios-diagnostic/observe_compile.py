#!/usr/bin/env python3
"""New diagnostic observer: parse ordinary build evidence; never execute it.

This is newly authored source after loss of the previous implementation. It
does not inherit that implementation's review or test results. The caller must
authenticate the contract/binding and establish xcodebuild success separately.
Only text command evidence and opaque file hashes are inspected here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys

_HELPERS = Path(__file__).resolve().parents[1] / "Dependencies/idevice"
sys.path.insert(0, str(_HELPERS))
try:
    import retained_c_provider
    import symbol_visibility
finally:
    sys.path.pop(0)

MAX_LOG = 64 * 1024 * 1024
MAX_TEXT = 4 * 1024 * 1024
MAX_MAP = 32 * 1024 * 1024
MAX_LINE = 512 * 1024
MAX_TOKENS = 100_000
MAX_REFERENCES = 128
MAX_DEPTH = 8
MAX_OPAQUE = 1024 * 1024 * 1024
MAX_TEXT_READS = 512
MAX_TOTAL_TEXT = 64 * 1024 * 1024
MAX_INVENTORY = 2 * 1024 * 1024
SENTINEL_MARKER = b"// Tetherless diagnostic compile sentinel (new source, October 2026)."
REQUIRED_CONDITIONS = frozenset({
    "TETHERLESS_BOUNDED_PAIRING_HOST", "TETHERLESS_STAGED_PAIRING_VALIDATION",
    "TETHERLESS_PAIRING_COMPOSITION_COMPILE_CHECK",
})
REQUIRED_SOURCES = frozenset({
    "SideStore/TetherlessCore/NativeCallLifetime.swift",
    "SideStore/TetherlessCore/PairingCancellationController.swift",
    "SideStore/TetherlessCore/PairingNumericEndpoint.swift",
    "SideStore/TetherlessCore/PairingPromotion.swift",
    "SideStore/TetherlessCore/PairingValidationChallenge.swift",
    "SideStore/TetherlessCore/PairingValidationBudget.swift",
    "SideStore/TetherlessNative/BoundedPairingHostBridge.swift",
    "SideStore/TetherlessNative/NativeStagedPairingValidator.swift",
    "SideStore/TetherlessNative/PairingBonjourListener.swift",
    "SideStore/TetherlessNative/PairingEndpointResolver.swift",
    "SideStore/TetherlessNative/PairingSetupModel.swift",
    "SideStore/TetherlessNative/PairingSetupView.swift",
    "SideStore/Views/Onboarding/OnboardingView.swift",
    "SideStore/Views/Settings/Advanced/PairingFile/WirelessPair/WirelessPairView.swift",
})
GATEWAY_SOURCE = "Dependencies/minimuxer/DeviceGateway/idevice/IdeviceGateway.swift"

# Diagnostic-only -u roots keep these checks meaningful under Release dead
# stripping. All other C/Rust exports are checked only if actually live.
from diagnostic_link_project import APP_C_ROOTS, APP_RUST_ROOTS, C_SYSTEM_FRAMEWORKS


class ObservationError(ValueError):
    """Required concrete compilation/link evidence is absent or ambiguous."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ObservationError(message)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _expected(value: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "invalid expected opaque hash")
    return value


def _tokens(text: str) -> list[str]:
    _require(len(text) <= MAX_TEXT and "\x00" not in text, "command text bound exceeded")
    try:
        result = shlex.split(text, posix=True)
    except ValueError as error:
        raise ObservationError("malformed quoted build evidence") from error
    _require(len(result) <= MAX_TOKENS, "command token bound exceeded")
    _require(not any(t in {";", "&&", "||", "|", ">", ">>", "<", "&"}
                     or "$(" in t or "`" in t for t in result),
             "shell expressions are not command evidence")
    return result


def _option(args: list[str], flag: str, joined: bool = False) -> list[str]:
    values = []
    for index, arg in enumerate(args):
        if arg == flag:
            _require(index + 1 < len(args), "missing argument for " + flag)
            values.append(args[index + 1])
        elif joined and arg.startswith(flag) and len(arg) > len(flag):
            values.append(arg[len(flag):])
    return values


def _one(args: list[str], flag: str) -> str:
    values = _option(args, flag)
    _require(len(values) == 1, "expected one " + flag + " in actual command")
    return values[0]


class _Capture:
    """Append-only, bounded diagnostic input evidence, including failed parses."""
    def __init__(self, root: Path, input_roots: list[Path]):
        requested = Path(os.path.abspath(root))
        _require(not requested.is_symlink(), "compiler evidence directory is symlinked")
        # The caller explicitly owns this destination. Canonicalize only its
        # existing parent (e.g. macOS /var -> /private/var), then create a fresh
        # non-symlink leaf. Never resolve arbitrary paths learned from logs.
        self.root = requested.parent.resolve(strict=True) / requested.name
        _require(not any(self.root.is_relative_to(item) or item.is_relative_to(self.root)
                         for item in input_roots), "compiler evidence directory must be separate from build inputs")
        self._guard_parents()
        _require(self.root.parent.is_dir(), "compiler evidence parent directory is absent")
        _require(not self.root.exists(), "compiler evidence directory must be fresh")
        self.root.mkdir()
        self.root_identity = self._inode(self.root.lstat())
        self.inventory = self.root / "inventory.jsonl"
        with self.inventory.open("xb"):
            pass
        self.inventory_identity = self._inode(self.inventory.lstat())
        self.inventory_digest = hashlib.sha256()
        self.inventory_size = 0
        self.reads, self.read_bytes = 0, 0
        self.retained_files, self.retained_bytes = 0, 0
        self.records = []
        self._append({"schema": 1, "event": "started", "mode": "diagnostic-only"})

    @staticmethod
    def _inode(info):
        return info.st_dev, info.st_ino

    def _guard_parents(self):
        for path in (*reversed(self.root.parents), self.root):
            _require(not path.is_symlink(), "compiler evidence directory is symlinked")

    def _guard(self):
        self._guard_parents()
        _require(self.root.is_dir() and self._inode(self.root.lstat()) == self.root_identity,
                 "compiler evidence directory changed")
        info = self.inventory.lstat()
        _require(stat.S_ISREG(info.st_mode) and self._inode(info) == self.inventory_identity
                 and info.st_size == self.inventory_size, "compiler evidence inventory changed or obstructed")

    def _append(self, record: dict):
        self._guard()
        data = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        _require(self.inventory_size + len(data) <= MAX_INVENTORY, "compiler evidence inventory bound exceeded")
        flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.inventory, flags)
        try:
            info = os.fstat(descriptor)
            _require(stat.S_ISREG(info.st_mode) and self._inode(info) == self.inventory_identity
                     and info.st_size == self.inventory_size, "compiler evidence inventory changed before append")
            with os.fdopen(descriptor, "ab", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.inventory_digest.update(data)
        self.inventory_size += len(data)

    def reserve_read(self, size: int):
        _require(self.reads + 1 <= MAX_TEXT_READS, "compiler text read count bound exceeded")
        _require(self.read_bytes + size <= MAX_TOTAL_TEXT, "compiler text aggregate read-byte bound exceeded")
        self.reads += 1
        self.read_bytes += size

    def retain(self, source: Path, data: bytes, previous: str | None):
        self._guard()
        _require(self.retained_files + 1 <= MAX_TEXT_READS and self.retained_bytes + len(data) <= MAX_TOTAL_TEXT,
                 "compiler text aggregate retention bound exceeded")
        name = f"input-{self.retained_files + 1:04d}.raw"
        path = self.root / name
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        digest = _sha(data)
        record = {"event": "input", "source_path": str(source), "retained_path": name,
                  "sha256": digest, "size": len(data), "read": self.reads}
        if previous is not None:
            record["previous_sha256"] = previous
            record["changed"] = previous != digest
        self.retained_files += 1
        self.retained_bytes += len(data)
        self.records.append(record)
        self._append(record)

    def _verify_retained(self):
        for record in self.records:
            path = self.root / record["retained_path"]
            before = path.lstat()
            _require(stat.S_ISREG(before.st_mode) and before.st_size == record["size"]
                     and before.st_size <= MAX_MAP, "retained compiler input changed or obstructed")
            with path.open("rb") as stream:
                data = stream.read(MAX_MAP + 1)
            after = path.lstat()
            _require(stat.S_ISREG(after.st_mode) and self._inode(before) == self._inode(after)
                     and before.st_mtime_ns == after.st_mtime_ns and len(data) == record["size"]
                     and _sha(data) == record["sha256"], "retained compiler input identity differs")

    def finish(self, status: str, error: str | None = None) -> dict:
        self._guard()
        self._verify_retained()
        record = {"event": status, "reads": self.reads, "read_bytes": self.read_bytes,
                  "retained_files": self.retained_files, "retained_bytes": self.retained_bytes}
        if error is not None:
            record["error"] = error[:8192]
        self._append(record)
        self._guard()
        data = self.inventory.read_bytes()
        _require(len(data) <= MAX_INVENTORY and _sha(data) == self.inventory_digest.hexdigest(),
                 "compiler evidence inventory identity differs")
        return {"directory": str(self.root), "inventory": str(self.inventory), "inventory_sha256": _sha(data),
                "retained_files": self.retained_files, "retained_bytes": self.retained_bytes}


class _Files:
    def __init__(self, prepared: Path, derived: Path, evidence: Path):
        self.roots = []
        self.root_aliases = []
        for root in (prepared, derived):
            _require(not root.is_symlink() and root.is_dir(), "owned evidence root missing or symlinked")
            canonical = root.resolve(strict=True)
            self.roots.append(canonical)
            self.root_aliases.append((Path(os.path.abspath(root)), canonical))
        self.references: dict[str, str] = {}
        self.capture = _Capture(evidence, self.roots)

    def path(self, name: str | Path, cwd: Path) -> Path:
        value = Path(name)
        _require("\x00" not in str(value), "invalid evidence path")
        _require(".." not in value.parts, "parent traversal in evidence path")
        path = Path(os.path.abspath(value if value.is_absolute() else cwd / value))
        # Only caller-supplied owned-root aliases may be normalized. Descendant
        # symlinks are checked below and never become an escape mechanism.
        for alias, canonical in self.root_aliases:
            if path.is_relative_to(alias):
                path = canonical / path.relative_to(alias)
                break
        root = next((root for root in self.roots if path.is_relative_to(root)), None)
        _require(root is not None, "evidence path escapes diagnostic/DerivedData roots: " + str(path))
        cursor = root
        for part in path.relative_to(root).parts:
            cursor /= part
            _require(not cursor.is_symlink(), "symlinked evidence is not admissible: " + str(cursor))
        return path

    def search_directory(self, name: str, cwd: Path, sdk: str) -> Path:
        """Admit fixed-name search probes, never arbitrary external file reads."""
        value = Path(name)
        _require(".." not in value.parts and "\x00" not in name, "parent traversal or NUL in search directory")
        path = Path(os.path.abspath(value if value.is_absolute() else cwd / value))
        if any(path.is_relative_to(root) for root in self.roots) or any(
                path.is_relative_to(alias) for alias, _ in self.root_aliases):
            return self.path(path, cwd)
        sdk_path = Path(sdk)
        # These are ordinary Xcode/system search locations. We may test for
        # exact artifact basenames there; selecting one still fails the owned
        # input rule before its bytes can be read.
        developer = next((parent for parent in reversed(sdk_path.parents) if parent.name == "Developer"), None)
        trusted = [sdk_path, Path("/usr/lib/swift")]
        if developer is not None:
            trusted.append(developer)
        _require(any(path.is_relative_to(root) for root in trusted),
                 "unowned non-toolchain search directory: " + str(path))
        return path

    def read(self, path: Path, limit: int = MAX_TEXT, *, compiler_text: bool = False) -> bytes:
        path = self.path(path, self.roots[0])
        try:
            with path.open("rb") as stream:
                info = os.fstat(stream.fileno())
                _require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
                         "evidence file type or size is unsupported: " + str(path))
                if compiler_text:
                    self.capture.reserve_read(info.st_size)
                data = stream.read(limit + 1)
                after = os.fstat(stream.fileno())
            _require(len(data) <= limit and (info.st_size, info.st_mtime_ns) ==
                     (after.st_size, after.st_mtime_ns), "evidence changed while reading")
            return data
        except OSError as error:
            raise ObservationError("required evidence file is unavailable: " + str(path)) from error

    def recorded_bytes(self, path: Path, limit: int) -> bytes:
        data = self.read(path, limit, compiler_text=True)
        previous = self.references.get(str(path))
        # Persist bytes before any decoding or parsing so a failing input can
        # be inspected. A changed reread retains both versions and fails closed.
        self.capture.retain(path, data, previous)
        digest = _sha(data)
        _require(previous is None or previous == digest, "compiler text changed between reads: " + str(path))
        self.references[str(path)] = digest
        _require(len(self.references) <= MAX_REFERENCES, "filelist/response reference bound exceeded")
        return data

    def text(self, path: Path, limit: int = MAX_TEXT) -> str:
        data = self.recorded_bytes(path, limit)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ObservationError("build text evidence is not UTF-8") from error
        _require("\x00" not in text, "NUL in text evidence")
        return text

    def opaque_identity(self, path: Path) -> dict:
        path = self.path(path, self.roots[0])
        try:
            _require(stat.S_ISREG(path.lstat().st_mode), "opaque artifact is not a regular file")
            with path.open("rb") as stream:
                before = os.fstat(stream.fileno())
                _require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_OPAQUE,
                         "opaque artifact type or size is unsupported")
                digest, total = hashlib.sha256(), 0
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    total += len(block)
                    _require(total <= MAX_OPAQUE, "opaque artifact size bound exceeded")
                    digest.update(block)
                after = os.fstat(stream.fileno())
            current = path.lstat()
            identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            _require(total == before.st_size and stat.S_ISREG(current.st_mode)
                     and identity(before) == identity(after) == identity(current),
                     "opaque artifact changed while hashing")
            return {"sha256": digest.hexdigest(), "size": total}
        except OSError as error:
            raise ObservationError("opaque artifact unavailable: " + str(path)) from error

    def opaque_hash(self, path: Path) -> str:
        return self.opaque_identity(path)["sha256"]

    def expand(self, args: list[str], cwd: Path, stack: tuple[Path, ...] = (), *,
               link: bool = False) -> tuple[list[str], set[Path]]:
        _require(len(stack) <= MAX_DEPTH, "response recursion bound exceeded")
        expanded, members = [], set()
        index = 0
        while index < len(args):
            arg = args[index]
            dyld_value = (link and expanded and expanded[-1] in {"-rpath", "-install_name", "-dylib_install_name"}
                          and re.fullmatch(r"@(?:executable_path|loader_path|rpath)(?:/.*)?", arg) is not None)
            if dyld_value:
                # dyld placeholders are values of these linker options. They
                # are not response files and never grant access to any file.
                expanded.append(arg)
            elif arg.startswith("@"):
                path = self.path(arg[1:], cwd)
                _require(path not in stack, "cyclic response evidence")
                nested, seen = self.expand(_tokens(self.text(path)), cwd, (*stack, path), link=link)
                expanded.extend(nested)
                members.update(seen)
                # Xcode's @SwiftFileList is a source-only response. An option
                # value ending in .swift is not a compiler source input. Mixed
                # argument responses may contain nested source-only lists, but
                # arbitrary option values never acquire source membership.
                if nested and all(token.endswith(".swift") and not token.startswith("-") for token in nested):
                    members.update(self.path(token, cwd) for token in nested)
            elif arg in {"-filelist", "-primary-filelist"}:
                index += 1
                _require(index < len(args), "missing filelist path")
                path = self.path(args[index], cwd)
                rows = self.text(path).splitlines()
                _require(len(rows) <= MAX_TOKENS, "filelist entry bound exceeded")
                for row in rows:
                    if not row.strip():
                        continue
                    _require(len(row) <= MAX_LINE, "filelist line bound exceeded")
                    # Xcode filelists contain one path per line, possibly quoted.
                    entry = _tokens(row) if row.lstrip().startswith(('"', "'")) else [row.strip()]
                    _require(len(entry) == 1 and not entry[0].startswith(("@", "-")), "invalid filelist member")
                    member = self.path(entry[0], cwd)
                    expanded.append(str(member))
                    members.add(member)
            else:
                expanded.append(arg)
            _require(len(expanded) <= MAX_TOKENS, "expanded command token bound exceeded")
            index += 1
        return expanded, members


def _commands(log: str, files: _Files) -> list[dict]:
    commands, context, cwd = [], None, None
    for line_number, line in enumerate(log.splitlines(), 1):
        _require(len(line) <= MAX_LINE, "build log line bound exceeded")
        if not line.strip():
            continue
        if not line[0].isspace():
            context, cwd = None, None
            match = re.fullmatch(r"SwiftDriver (SideStore|IdeviceGateway) normal arm64 com\.apple\.xcode\.tools\.swift\.compiler \(in target '([^']+)' from project '[^']+'\)", line)
            if match and match[1] == match[2]:
                context = ("swift", match[1])
            elif re.fullmatch(r"Ld .+ normal(?: arm64)? \(in target 'SideStore' from project '[^']+'\)", line):
                context = ("link", "SideStore")
            continue
        if context is None:
            continue
        args = _tokens(line.strip())
        if args and args[0] == "cd":
            _require(len(args) == 2 and cwd is None, "invalid build working directory evidence")
            cwd = files.path(args[1], files.roots[0])
            _require(cwd.is_dir(), "build working directory is absent")
            continue
        if not args:
            continue
        kind, module = context
        if kind == "swift" and args[:2] == ["builtin-SwiftDriver", "--"]:
            args = args[2:]
        executable = Path(args[0])
        allowed = {"swiftc"} if kind == "swift" else {"clang", "clang++"}
        if executable.name not in allowed or not executable.is_absolute():
            continue
        _require(cwd is not None, "command has no observed working directory")
        raw_args = _link_args(args[1:]) if kind == "link" else args[1:]
        expanded, members = files.expand(raw_args, cwd, link=kind == "link")
        commands.append({"kind": kind, "module": module, "args": expanded,
                         "members": members, "cwd": cwd, "line": line_number,
                         "command_sha256": _sha(line.encode()), "executable": str(executable)})
        context, cwd = None, None
    return commands


def _device_identity(command: dict, sdk: str) -> str:
    args = command["args"]
    triple = _one(args, "-target")
    _require(re.fullmatch(r"arm64-apple-ios[0-9]+(?:\.[0-9]+){0,2}", triple) is not None,
             "actual command does not target arm64 iOS device")
    flag = "-sdk" if command["kind"] == "swift" else "-isysroot"
    _require(_one(args, flag) == sdk, "actual command SDK differs from selected iPhoneOS SDK")
    return triple


def _include_directories(args: list[str]) -> list[str]:
    """Keep Swift and forwarded Clang include-option spellings distinct."""
    swift, clang = [], []
    index = 0
    while index < len(args):
        if args[index] == "-Xcc":
            index += 1
            _require(index < len(args), "missing forwarded Clang argument")
            clang.append(args[index])
        else:
            swift.append(args[index])
        index += 1

    def extract(values: list[str], system_option: str) -> list[str]:
        result, index = [], 0
        while index < len(values):
            token = values[index]
            if token in {"-I", system_option}:
                index += 1
                _require(index < len(values), "missing include directory")
                result.append(values[index])
            elif token.startswith("-I"):
                result.append(token[2:])
            elif system_option == "-isystem" and token.startswith("-isystem"):
                result.append(token[len("-isystem"):])
            index += 1
        return result

    return extract(swift, "-Isystem") + extract(clang, "-isystem")


def _module_evidence(command: dict, files: _Files, header_hash: str, map_hash: str, sdk: str) -> dict:
    args, cwd = command["args"], command["cwd"]
    explicit = []
    for index, arg in enumerate(args):
        if arg.startswith("-fmodule-map-file="):
            explicit.append(arg.split("=", 1)[1])
        elif arg == "-fmodule-map-file":
            _require(index + 1 < len(args), "missing explicit module-map path")
            explicit.append(args[index + 1])
    maps = set()
    for value in explicit:
        path = files.path(value, cwd)
        text = files.text(path)
        if re.search(r"\bmodule\s+IDevice\s*\{", text):
            maps.add(path)
    for value in _include_directories(args):
        candidate = files.search_directory(value, cwd, sdk) / "module.modulemap"
        if candidate.is_file():
            text = files.text(candidate)
            if re.search(r"\bmodule\s+IDevice\s*\{", text):
                maps.add(candidate)
    _require(len(maps) == 1, "IDevice module selection is absent or ambiguous")
    module_map = maps.pop()
    _require(files.opaque_hash(module_map) == map_hash, "selected IDevice module-map identity differs")
    # The exact reviewed map supplies one local idevice.h, with no umbrella or
    # additional headers. Reject ambiguity rather than interpret arbitrary Clang.
    text = files.text(module_map)
    headers = re.findall(r'\bheader\s+"([^"]+)"', text)
    _require(headers == ["idevice.h"] and "umbrella" not in text,
             "selected IDevice module does not name the bound local header")
    header = files.path(module_map.parent / "idevice.h", cwd)
    _require(files.opaque_hash(header) == header_hash, "selected IDevice header identity differs")
    return {"module_map": str(module_map), "module_map_sha256": map_hash,
            "header": str(header), "header_sha256": header_hash}


def _link_args(args: list[str]) -> list[str]:
    result, index = [], 0
    while index < len(args):
        arg = args[index]
        if arg == "-Xlinker":
            index += 1
            _require(index < len(args), "missing -Xlinker argument")
            result.append(args[index])
        elif arg.startswith("-Wl,"):
            result.extend(arg[4:].split(","))
        else:
            result.append(arg)
        index += 1
    return result


def _c_module_evidence(command: dict, files: _Files, expected: dict, sdk: str) -> dict:
    maps = set()
    args = [arg for arg in command["args"] if arg != "-Xcc"]
    explicit = []
    for index, arg in enumerate(args):
        if arg.startswith("-fmodule-map-file="):
            explicit.append(arg.split("=", 1)[1])
        elif arg == "-fmodule-map-file":
            _require(index + 1 < len(args), "missing explicit C module-map path")
            explicit.append(args[index + 1])
    pattern = r"\bmodule\s+libimobiledevice(?:\s+\[system\])?\s*\{"
    for value in explicit:
        path = files.path(value, command["cwd"])
        if re.search(pattern, files.text(path)):
            maps.add(path)
    for value in _include_directories(command["args"]):
        directory = files.search_directory(value, command["cwd"], sdk)
        for path in (directory / "module.modulemap", directory / "libimobiledevice/module.modulemap"):
            if path.is_file() and re.search(pattern, files.text(path)):
                maps.add(path)
    _require(len(maps) == 1, "C provider module selection is absent or ambiguous")
    module_map = maps.pop()
    header_root = files.path(module_map.parent.parent, command["cwd"])
    inventory = expected.get("header_inventory")
    _require(isinstance(inventory, dict) and inventory, "complete C header/module inventory is missing")
    actual = {}
    # A compiler include root may also contain unrelated package headers.
    # Every selected C namespace, however, must have exactly its full inventory.
    prefixes = {Path(name).parts[0] for name in inventory}
    for prefix in prefixes:
        subtree = files.path(header_root / prefix, command["cwd"])
        _require(subtree.exists(), "C header namespace is absent")
        paths = [subtree] if subtree.is_file() else sorted(subtree.rglob("*"))
        for path in paths:
            files.path(path, command["cwd"])
            if path.is_file():
                identity = files.opaque_identity(path)
                actual[path.relative_to(header_root).as_posix()] = {
                    "sha256": identity["sha256"], "bytes": identity["size"]}
    for value in _include_directories(command["args"]):
        directory = files.search_directory(value, command["cwd"], sdk)
        for name in inventory:
            candidate = directory / name
            if candidate.is_file():
                _require(files.path(candidate, command["cwd"]) == header_root / name,
                         "alternate C public header search input")
    header = files.path(header_root / "plist/plist.h", command["cwd"])
    _require(actual == inventory and files.opaque_hash(module_map) == _expected(expected["module_map_sha256"])
             and files.opaque_hash(header) == _expected(expected["header_sha256"]),
             "C provider full header/module inventory differs from the retained proof")
    return {"c_provider_module_map": str(module_map), "c_provider_header": str(header),
            "c_provider_module_map_sha256": expected["module_map_sha256"], "c_provider_header_sha256": expected["header_sha256"],
            "c_provider_header_inventory": actual}


def _live_map_ownership(raw: bytes, c_archive: Path, c_symbols: list[str], rust_archive: Path,
                        rust_symbols: list[str], visibility: dict) -> dict:
    """Check actual live known exports; dead-stripped rows never satisfy roots."""
    _require(isinstance(c_symbols, list) and c_symbols == sorted(set(c_symbols))
             and isinstance(rust_symbols, list) and rust_symbols == sorted(set(rust_symbols))
             and not set(c_symbols) & set(rust_symbols), "full Rust/C export identities differ")
    try:
        _objects, rows = retained_c_provider.parse_link_map(raw)
    except ValueError as error:
        raise ObservationError("App live map ownership differs: " + str(error)) from error
    live = {name for _owner, name in rows}
    c_live, rust_live = live & set(c_symbols), live & set(rust_symbols)
    _require(APP_C_ROOTS <= c_live and APP_RUST_ROOTS <= rust_live,
             "required diagnostic C/Rust roots are absent from live App map")
    try:
        proof = retained_c_provider.link_ownership(raw, c_archive, c_live, rust_archive, rust_live, visibility=visibility)
    except ValueError as error:
        raise ObservationError("App live map ownership differs: " + str(error)) from error
    return dict(proof, c_live_symbols=sorted(c_live), rust_live_symbols=sorted(rust_live),
                dead_stripped_symbols_used=False)


def _link_evidence(command: dict, files: _Files, archive: Path, archive_hash: str,
                   provider_hash: str, configuration: str, sdk: str, c_provider: dict, rust_symbols: list[str], visibility: dict) -> dict:
    args, cwd = _link_args(command["args"]), command["cwd"]
    c_provider_hash = _expected(c_provider["library_sha256"])
    output = files.path(_one(args, "-o"), cwd)
    _require(output.name == "SideStore" and output.parent.name == "SideStore.app"
             and output.is_relative_to(files.roots[1])
             and configuration + "-iphoneos" in output.parts,
             "Ld is not the selected final SideStore device executable")
    libraries = _option(args, "-l", joined=True)
    _require(not any(value.lower() in {"ssl", "crypto", "openssl"} for value in libraries),
             "extra OpenSSL static/dynamic library provider in final link")
    _require(not any(re.fullmatch(r"(?:lib)?(?:ssl|crypto|openssl)\.(?:a|dylib|tbd)", Path(arg).name.lower())
                     or re.fullmatch(r"-(?:weak|reexport|upward)-l(?:ssl|crypto|openssl)", arg.lower())
                     for arg in args), "extra OpenSSL library provider in final link")
    direct = {files.path(arg, cwd) for arg in args if arg.endswith(".a") and not arg.startswith("-")}
    _require(not any(path.name.lower() in {"libssl.a", "libcrypto.a", "libopenssl.a"} for path in direct),
             "extra OpenSSL archive provider in final link")
    archive_name = archive.name
    library_name = archive_name[3:-2] if archive_name.startswith("lib") and archive_name.endswith(".a") else ""
    _require(not any("idevice" in value.lower() and value != library_name for value in libraries)
             and not any("idevice" in path.name.lower() and path.name != archive_name for path in direct),
             "alternate IDevice library in final link")
    candidates = {path for path in direct if path.name == archive_name}
    if library_name in libraries:
        searched = []
        for value in _option(args, "-L", joined=True):
            directory = files.search_directory(value, cwd, sdk)
            for suffix in (".dylib", ".tbd", ".a"):
                path = directory / ("lib" + library_name + suffix)
                if path.exists():
                    searched.append(path)
        _require(len(set(searched)) == 1 and searched[0].suffix == ".a",
                 "native library search selection is absent or ambiguous")
        candidates.update(searched)
    _require(len(candidates) == 1, "final Ld does not select one bound native archive")
    processed = candidates.pop()
    _require(processed.is_relative_to(files.roots[1]) and processed != archive,
             "final Ld archive is not an actual processed DerivedData copy")
    processed_identity = files.opaque_identity(processed)
    _require(processed_identity["sha256"] == archive_hash, "processed native archive identity differs")
    c_candidates = {path for path in direct if path.name == "libimobiledevice.a"}
    c_provider_name = re.compile(r"(?:lib)?(?:plist|imobiledevice|usbmuxd)(?:[-_.A-Za-z0-9]*)", re.I)
    framework_names = [name for flag in ("-framework", "-weak_framework", "-reexport_framework",
                                         "-upward_framework", "-lazy_framework") for name in _option(args, flag)]
    _require(not any(c_provider_name.fullmatch(name) for name in framework_names)
             and not any(c_provider_name.fullmatch(part[:-len(".framework")])
                         for arg in args for part in Path(arg).parts if part.lower().endswith(".framework")),
             "alternate C framework provider in final link")
    _require(not any(re.fullmatch(r"(?:lib)?(?:plist|imobiledevice|usbmuxd)(?:[-_.A-Za-z0-9]*)\.(?:dylib|tbd)", Path(arg).name.lower())
                     or re.fullmatch(r"-(?:weak|reexport|upward)-l(?:plist|imobiledevice|usbmuxd)(?:[-_.A-Za-z0-9]*)", arg.lower())
                     for arg in args), "alternate C dynamic/weak provider in final link")
    _require(not any(("imobiledevice" in value.lower() or "plist" in value.lower() or "usbmuxd" in value.lower()) and value != "imobiledevice"
                     for value in libraries)
             and not any(("imobiledevice" in path.name.lower() or "plist" in path.name.lower() or "usbmuxd" in path.name.lower())
                         and path.name != "libimobiledevice.a" for path in direct),
             "alternate C plist provider in final link")
    if "imobiledevice" in libraries:
        searched = []
        for value in _option(args, "-L", joined=True):
            directory = files.search_directory(value, cwd, sdk)
            searched.extend(directory / ("libimobiledevice" + suffix) for suffix in (".dylib", ".tbd", ".a")
                            if (directory / ("libimobiledevice" + suffix)).exists())
        _require(len(set(searched)) == 1 and searched[0].suffix == ".a",
                 "C provider search selection is absent or ambiguous")
        c_candidates.update(searched)
    _require(len(c_candidates) == 1, "final Ld does not select one verified C provider")
    c_archive = c_candidates.pop()
    c_archive_identity = files.opaque_identity(c_archive)
    _require(c_archive.is_relative_to(files.roots[1]) and c_archive_identity["sha256"] == c_provider_hash,
             "processed C provider archive differs from the mixed-provider proof")
    _require(C_SYSTEM_FRAMEWORKS <= set(_option(args, "-framework"))
             and not C_SYSTEM_FRAMEWORKS & set(_option(args, "-weak_framework")),
             "final Ld lacks strong C system frameworks")
    _require(APP_C_ROOTS | APP_RUST_ROOTS <= set(_option(args, "-u")),
             "final Ld lacks diagnostic C/Rust live roots")
    map_path = files.path(_one(args, "-map"), cwd)
    _require(map_path.is_relative_to(files.roots[1]), "App linker map must be inside owned DerivedData")
    # These exact DerivedData bytes match the producer's opaque archives. Only
    # their filesystem locations change; member/name visibility stays bound.
    try:
        rebound = symbol_visibility.rebind(visibility, archives={
            "rust": {"source": str(processed), "sha256": archive_hash, "bytes": processed_identity["size"]},
            "c": {"source": str(c_archive), "sha256": c_provider_hash, "bytes": c_archive_identity["size"]}})
    except ValueError as error:
        raise ObservationError("App symbol visibility identity differs: " + str(error)) from error
    ownership = _live_map_ownership(files.recorded_bytes(map_path, MAX_MAP), c_archive,
                                    c_provider["symbols"], processed, rust_symbols, rebound)
    _require("OpenSSL" in _option(args, "-framework"), "final Ld lacks selected OpenSSL framework")
    _require("OpenSSL" not in _option(args, "-weak_framework"), "weak OpenSSL provider is unsupported")
    providers = set()
    for value in _option(args, "-F", joined=True):
        directory = files.search_directory(value, cwd, sdk)
        candidate = directory / "OpenSSL.framework" / "OpenSSL"
        if candidate.exists():
            providers.add(candidate)
    direct_providers = {files.path(arg, cwd) for arg in args
                        if arg.endswith("/OpenSSL.framework/OpenSSL")}
    providers.update(direct_providers)
    _require(len(providers) == 1, "OpenSSL framework provider selection is absent or ambiguous")
    provider = providers.pop()
    xcframework = next((parent for parent in archive.parents if parent.name == "IDevice.xcframework"), None)
    _require(xcframework is not None and not provider.is_relative_to(xcframework),
             "OpenSSL provider is bundled inside local IDevice artifact")
    _require(files.opaque_hash(provider) == provider_hash, "selected external OpenSSL framework identity differs")
    output_identity = files.opaque_identity(output)
    _require(output_identity["size"] > 0, "final SideStore output is empty")
    return {"output": str(output), "output_sha256": output_identity["sha256"], "output_size": output_identity["size"],
            "processed_archive": str(processed), "archive_sha256": archive_hash,
            "c_provider_archive": str(c_archive), "c_provider_archive_sha256": c_provider_hash,
            "openssl_framework_binary": str(provider), "openssl_framework_binary_sha256": provider_hash,
            "link_map": str(map_path), "live_map_ownership": ownership,
            "binary_format_inspected": False}


def observe_compile(log_path: Path, prepared_root: Path, derived_data: Path,
                    contract: dict, native_binding: dict, configuration: str, *, evidence_directory: Path) -> dict:
    """Observe one successful build's evidence, without running build commands.

    native_binding is prepare_binding.bind()'s receipt plus ``sdk_path`` from
    the runner's selected xcrun iPhoneOS SDK. SDK selection, process success and
    authentication of the receipt/contract remain the caller's responsibility.
    SwiftDriver app/gateway deployment versions need not be equal. Every app
    composition input must occur in a real response/filelist, not loose log text.
    evidence_directory must be a fresh child of an existing owned directory,
    separate from prepared_root/derived_data. Raw text reads and a bounded
    append-only inventory remain there after both successful and failed parses.
    """
    files = None
    try:
        files = _Files(Path(prepared_root), Path(derived_data), Path(evidence_directory))
        _require(configuration in {"Debug", "Release"}, "unsupported diagnostic configuration")
        _require(set(contract["prepared_composition_sources"]) == REQUIRED_SOURCES,
                 "contract must retain all fourteen composition inputs")
        _require(set(contract["required_conditions"]) == REQUIRED_CONDITIONS
                 and len(contract["required_conditions"]) == 3, "contract required conditions differ")
        sdk = native_binding["sdk_path"]
        _require(isinstance(sdk, str) and Path(sdk).is_absolute()
                 and re.fullmatch(r"iPhoneOS[0-9.]*\.sdk", Path(sdk).name) is not None,
                 "selected SDK is not an absolute iPhoneOS SDK identity")
        bound = native_binding["bound_files"]
        source_hashes = {}
        for name, item in contract["prepared_composition_sources"].items():
            path = files.path(name, files.roots[0])
            expected = _expected(bound[name])
            actual = files.opaque_hash(path)
            _require(actual == expected, "bound composition source identity differs: " + name)
            if name == contract["sentinel"]["prepared_path"]:
                data = files.read(path)
                _require(data.count(SENTINEL_MARKER) == 1, "new compile sentinel is absent or repeated")
                original, sentinel = data.split(SENTINEL_MARKER)
                _require(original.endswith(b"\n") and _sha(original[:-1]) == _expected(item["sha256"])
                         and _sha(SENTINEL_MARKER + sentinel) == _expected(contract["sentinel"]["sha256"]),
                         "onboarding source/sentinel identity differs from contract")
            else:
                _require(actual == _expected(item["sha256"]), "composition source differs from reviewed contract")
            source_hashes[str(path)] = actual
        gateway = files.path(GATEWAY_SOURCE, files.roots[0])
        _require(files.opaque_hash(gateway) == _expected(bound[GATEWAY_SOURCE]), "gateway source identity differs")
        local = {key: files.path(native_binding["local_device_files"][key], files.roots[0])
                 for key in ("archive", "header", "module_map")}
        package = Path(contract["gateway"]["prepared_path"])
        xcframework = files.path(package.parent / contract["gateway"]["local_binary_path"], files.roots[0])
        _require(xcframework.name == "IDevice.xcframework" and all(path.is_relative_to(xcframework) for path in local.values()),
                 "bound native files are outside the selected local XCFramework")
        hashes = {key: _expected(bound[str(path.relative_to(files.roots[0]))]) for key, path in local.items()}
        _require(all(files.opaque_hash(path) == hashes[key] for key, path in local.items()), "bound local native identity differs")
        provider_hash = _expected(native_binding["native_artifact"]["targets"]["aarch64-apple-ios"]
                                  ["provider_receipt"]["framework_binary_sha256"])
        c_provider = native_binding["native_artifact"]["targets"]["aarch64-apple-ios"]["mixed_provider"]
        c_local = {key: files.path(native_binding["local_c_device_files"][key], files.roots[0])
                   for key in ("archive", "header", "module_map")}
        c_xcframework = files.path(package.parent / contract["gateway"]["local_c_binary_path"], files.roots[0])
        _require(c_xcframework.name == "libimobiledevice.xcframework"
                 and all(path.is_relative_to(c_xcframework) for path in c_local.values()),
                 "bound C files are outside the selected local XCFramework")
        for key, path in c_local.items():
            expected = _expected(c_provider[{"archive": "library_sha256", "header": "header_sha256",
                                             "module_map": "module_map_sha256"}[key]])
            _require(bound[path.relative_to(files.roots[0]).as_posix()] == expected
                     and files.opaque_hash(path) == expected, "bound local C identity differs")
        header_root = c_local["module_map"].parent.parent
        for name, entry in c_provider["header_inventory"].items():
            path = files.path(header_root / name, files.roots[0])
            _require(bound[path.relative_to(files.roots[0]).as_posix()] == _expected(entry["sha256"])
                     and files.opaque_identity(path) == {"sha256": entry["sha256"], "size": entry["bytes"]},
                     "bound complete C header inventory differs")
        rust_symbols = native_binding["native_artifact"]["rust_symbols"]["aarch64-apple-ios"]
        log_path = Path(log_path)
        _require(not log_path.is_symlink(), "build log must not be symlinked")
        with log_path.open("rb") as stream:
            raw_log = stream.read(MAX_LOG + 1)
        _require(len(raw_log) <= MAX_LOG, "build log size bound exceeded")
        log = raw_log.decode("utf-8")
        _require("\x00" not in log, "NUL in build log")
        commands = _commands(log, files)
        observations = {}
        for module in ("SideStore", "IdeviceGateway"):
            selected = [command for command in commands if command["kind"] == "swift" and command["module"] == module]
            _require(len(selected) == 1, "expected one actual SwiftDriver command for " + module)
            command = selected[0]
            _require(_one(command["args"], "-module-name") == module, "SwiftDriver module identity differs")
            triple = _device_identity(command, sdk)
            conditions = set(_option(command["args"], "-D", joined=True))
            if module == "SideStore":
                _require(REQUIRED_CONDITIONS <= conditions, "actual app compiler lacks required diagnostic conditions")
                required = {Path(name) for name in source_hashes}
            else:
                required = {gateway}
            _require(required <= command["members"], "actual " + module + " compiler filelists lack required inputs")
            module_info = _module_evidence(command, files, hashes["header"], hashes["module_map"], sdk)
            if module == "SideStore":
                module_info.update(_c_module_evidence(command, files, c_provider, sdk))
            observations[module] = {"line": command["line"], "command_sha256": command["command_sha256"],
                                    "compiler": command["executable"], "target": triple, "sdk": sdk,
                                    "conditions": sorted(conditions), "required_inputs": sorted(map(str, required)),
                                    **module_info}
        links = [command for command in commands if command["kind"] == "link"]
        _require(len(links) == 1, "expected one actual final SideStore Ld command")
        link = links[0]
        target = _device_identity(link, sdk)
        link_info = _link_evidence(link, files, local["archive"], hashes["archive"], provider_hash, configuration, sdk, c_provider, rust_symbols,
                                   native_binding["native_artifact"]["symbol_visibility"]["aarch64-apple-ios"])
        result = {"schema": 1, "observer_source": "new-after-workspace-reset", "configuration": configuration,
                "log_sha256": _sha(raw_log), "compile": observations,
                "link": {"line": link["line"], "command_sha256": link["command_sha256"],
                         "target": target, "sdk": sdk, **link_info},
                "composition_source_hashes": source_hashes, "text_input_hashes": dict(sorted(files.references.items())),
                "binary_format_inspected": False, "ios_binaries_executed": False,
                "consumer_or_product_activation": False}
        result["compiler_input_evidence"] = files.capture.finish("complete")
        return result
    except (ObservationError, KeyError, TypeError, UnicodeError, OSError) as error:
        if files is not None:
            try:
                files.capture.finish("failed", str(error))
            except (ObservationError, OSError) as capture_error:
                raise ObservationError("compiler input capture failed: " + str(capture_error) + "; observation: " + str(error)) from error
        if isinstance(error, ObservationError):
            raise
        raise ObservationError("incomplete or unreadable compile observation inputs: " + str(error)) from error
