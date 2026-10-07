"""Retain bounded linkage inputs around every supervised scan and link.

Legacy calls are diagnostic-only. A source-bound capture can be consumed only
after symbol_visibility validates its compiler text and complete provenance.
Opaque archives are hashed/copied, never parsed or executed by this module.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat

from apply_patch import VerificationError, canonical_json
from bounded_process import MAX_LOG_BYTES
import rust_symbol_reader

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_STATUS_BYTES = 1024 * 1024
MAX_OPERATIONS = 12  # two visibility scans, two external scans, eight links
TARGETS = ("aarch64-apple-ios", "aarch64-apple-ios-sim")
OBSERVATION_FLAGS = ["--defined-only", "--format=darwin", "--print-file-name", "--quiet"]


def _regular(path: Path) -> None:
    if (not path.is_absolute() or ".." in path.parts
            or any(item.is_symlink() for item in (path, *path.parents))
            or not path.is_file()):
        raise VerificationError("linkage evidence input must be a canonical regular file")


def _canonical_file(path: Path) -> Path:
    # The runner supports a symlinked workspace parent. Resolve that parent,
    # never the input leaf: an archive/log itself must still be a regular file.
    if not path.is_absolute() or ".." in path.parts or path.is_symlink():
        raise VerificationError("linkage evidence input must be an absolute regular file")
    result = path.parent.resolve(strict=True) / path.name
    _regular(result)
    return result


def _stamp(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def file_identity(path: Path, limit: int, *, copy_to: Path | None = None, allow_empty: bool = False) -> dict:
    """Hash bounded bytes, detecting path/descriptor mutation during the read."""
    path = _canonical_file(path)
    before = path.stat()
    if not (0 if allow_empty else 1) <= before.st_size <= limit:
        raise VerificationError("linkage evidence file is empty or exceeds its byte bound")
    digest, size = hashlib.sha256(), 0
    output = None
    try:
        with path.open("rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode) or _stamp(os.fstat(source.fileno())) != _stamp(before):
                raise VerificationError("linkage evidence input changed before reading")
            if copy_to is not None:
                output = copy_to.open("xb")
            while block := source.read(min(1024 * 1024, limit - size + 1)):
                size += len(block)
                if size > limit:
                    raise VerificationError("linkage evidence file exceeds its byte bound")
                digest.update(block)
                if output is not None:
                    output.write(block)
            if _stamp(os.fstat(source.fileno())) != _stamp(before):
                raise VerificationError("linkage evidence input changed while reading")
        _regular(path)
        if size != before.st_size or _stamp(path.stat()) != _stamp(before):
            raise VerificationError("linkage evidence input changed after reading")
    finally:
        if output is not None:
            output.close()
    return {"bytes": size, "sha256": digest.hexdigest()}


def observation_command(reader: dict, archive: Path) -> list[str]:
    rust_symbol_reader.validate_receipt(reader)
    _canonical_file(archive)
    return [reader["llvm_nm"]["path"], *OBSERVATION_FLAGS, str(archive)]


class LinkageObservation:
    def __init__(self, root: Path, *, target: str, rust_archive: Path,
                 c_archive: Path, c_sha256: str, reader: dict, source_context: dict | None = None):
        if target not in TARGETS:
            raise VerificationError("unreviewed linkage observation target")
        if not root.is_absolute() or ".." in root.parts or root.exists() or root.is_symlink():
            raise VerificationError("linkage observation directory must be fresh and canonical")
        root = root.parent.resolve(strict=True) / root.name
        rust_symbol_reader.audit_local(reader)
        root.mkdir()
        self.root, self.reader, self.operations = root, reader, 0
        self.acceptance = source_context is not None
        self.argument_paths = {"rust": rust_archive, "c": c_archive}
        self.paths = {role: _canonical_file(path) for role, path in self.argument_paths.items()}
        self.copies = {"rust": root / "rust-staticlib.a", "c": root / "c-staticlib.a"}
        self.expected = {}
        for role in ("rust", "c"):
            self.expected[role] = file_identity(self.paths[role], MAX_ARCHIVE_BYTES,
                                                copy_to=self.copies[role])
            if file_identity(self.copies[role], MAX_ARCHIVE_BYTES) != self.expected[role]:
                raise VerificationError("retained linkage archive differs from its source")
        if self.expected["c"]["sha256"] != c_sha256:
            raise VerificationError("linkage C archive differs from the authenticated provider")
        if not self._unchanged(self._snapshot()):
            raise VerificationError("linkage archives changed during retention")
        (root / "inputs.json").write_bytes(canonical_json({
            "schema": 2 if self.acceptance else 1, "target": target, "diagnostic_only": not self.acceptance,
            "ownership_acceptance_changed": self.acceptance, "source_context": source_context, "native_payloads_executed": False,
            "archive_byte_limit_each": MAX_ARCHIVE_BYTES,
            "archives": {role: {**self.expected[role], "source": str(self.argument_paths[role]),
                                 "canonical_source": str(self.paths[role]),
                                 "retained": self.copies[role].name} for role in self.paths},
            "symbol_reader": reader, "observation_flags": OBSERVATION_FLAGS,
        }))

    def _snapshot(self) -> dict:
        observed = {}
        for role in ("rust", "c"):
            if _canonical_file(self.argument_paths[role]) != self.paths[role]:
                raise VerificationError("linkage archive argument changed its resolved identity")
            observed[role] = {"source": file_identity(self.paths[role], MAX_ARCHIVE_BYTES),
                              "retained": file_identity(self.copies[role], MAX_ARCHIVE_BYTES)}
        return observed

    def _unchanged(self, observed: dict) -> bool:
        return all(observed.get(role, {}).get(place) == self.expected[role]
                   for role in ("rust", "c") for place in ("source", "retained"))

    def run(self, command: list[str], *, log: Path, invoke, maps: tuple[Path, ...] = ()):
        """Bind all four scan and eight link operations, including failures."""
        if self.operations >= MAX_OPERATIONS or not re.fullmatch(r"[A-Za-z0-9_-]+\.txt", log.name):
            raise VerificationError("unreviewed linkage observation operation")
        self.operations += 1
        receipt = self.root / (f"{self.operations:02d}-" + log.stem + ".json")
        row = {"schema": 1, "diagnostic_only": not self.acceptance, "command": command,
               "log": str(log), "command_completed": False, "inputs_unchanged": False}
        primary = None
        retention_errors = []
        try:
            row["before"] = self._snapshot()
            if not self._unchanged(row["before"]):
                raise VerificationError("linkage archive changed before command")
            rust_symbol_reader.audit_local(self.reader)
            result = invoke()
            row["command_completed"] = True
            return result
        except BaseException as error:
            primary = error
            row["primary_error_type"] = type(error).__name__
            raise
        finally:
            try:
                row["after"] = self._snapshot()
                row["inputs_unchanged"] = self._unchanged(row.get("before", {})) and self._unchanged(row["after"])
                if not row["inputs_unchanged"]:
                    raise VerificationError("linkage archive changed across command")
                rust_symbol_reader.audit_local(self.reader)
            except (OSError, ValueError, VerificationError) as error:
                retention_errors.append(str(error))
            row["outputs"] = {}
            for path, limit in [(log, MAX_LOG_BYTES), (log.with_name(log.name + ".status.json"), MAX_STATUS_BYTES),
                                *[(path, MAX_LOG_BYTES) for path in maps]]:
                try:
                    # Zero-byte command logs are valid; use the same stable
                    # descriptor/path hashing as nonempty logs, maps/status.
                    identity = file_identity(path, limit, allow_empty=path == log)
                    row["outputs"][path.name] = {"path": str(path), **identity}
                except (OSError, ValueError, VerificationError) as error:
                    row["outputs"][path.name] = {"path": str(path), "retained": False, "error": str(error)}
                    retention_errors.append(str(error))
            row["retention_errors"] = retention_errors
            try:
                receipt.write_bytes(canonical_json(row))
            except OSError:
                if primary is None:
                    raise
            if retention_errors and primary is None:
                raise VerificationError("linkage observation retention failed: " + "; ".join(retention_errors))

    def audit(self) -> None:
        if not self._unchanged(self._snapshot()):
            raise VerificationError("linkage archive changed after observed operations")
        rust_symbol_reader.audit_local(self.reader)

    def scans(self, invoke) -> None:
        for role in ("rust", "c"):
            command = observation_command(self.reader, self.argument_paths[role])
            log = self.root / (role + "-defined-members.txt")
            self.run(command, log=log, invoke=lambda: invoke(command, log))
