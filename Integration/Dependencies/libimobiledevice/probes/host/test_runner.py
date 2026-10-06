"""Runner contract tests; fake compilers never launch a native process here."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("c_provider_host_tests", HERE.parents[1] / "host_tests.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)

SUCCESS = "\n".join([
    "CONTEXT_SIZES ed=208 glue=216 glue_num_qwords_offset=208 glue_num_qwords_size=4",
    *host.PASS_LINES,
]) + "\n"


class HostRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".test-output-unit-", dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "prepared"
        ed = self.source / "root" / "3rd_party" / "ed25519"
        glue = self.source / "glue" / "src"
        ed.mkdir(parents=True)
        glue.mkdir(parents=True)
        for name in host.ED_FILES:
            (ed / name).write_text("/* synthetic source for a mocked compiler */\n")
        (glue / "sha512.c").write_text("/* synthetic */\n")
        (glue / "common.h").write_text("/* synthetic */\n")
        self.calls = []
        self.failure_name = None
        self.failure_outcome = "nonzero_exit"
        self.incomplete_cleanup = False

    def capture(self, args, **kwargs):
        self.calls.append((args, kwargs))
        name = kwargs["log"].stem
        if name == self.failure_name:
            log = kwargs["log"]
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("synthetic supervised failure\n")
            log.with_name(log.name + ".status.json").write_text(json.dumps({
                "outcome": self.failure_outcome,
                "cleanup": {"direct_child_reaped": True, "group_empty": not self.incomplete_cleanup},
            }))
            raise host.VerificationError("synthetic supervised failure")
        if name == "compiler-version":
            return "gcc (mock identity, never executed)"
        if name in ("plain-run", "asan-run"):
            return SUCCESS
        return ""

    def run_mocked(self, sdk=None):
        with patch.object(host, "compiler_path", return_value=Path("/usr/bin/cc")), \
             patch.object(host, "capture_helper_command", side_effect=self.capture):
            return host.run_host_tests(self.source, self.root / "result", sdk=sdk)

    def test_passes_with_independent_compilation_and_bounded_commands(self):
        result = self.run_mocked()
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["plain"]["context_layout"]["ed_bytes"], 208)
        self.assertEqual(result["asan"]["outcome"], "passed")
        self.assertEqual(result["ubsan"]["outcome"], "not_run")
        compiles = [args for args, _ in self.calls if "-c" in args]
        self.assertEqual(len(compiles), 26)
        for args, kw in self.calls:
            self.assertIsInstance(args, list)
            self.assertNotIn("shell", kw)
            self.assertIn(kw["timeout_seconds"], (30, 120))
            self.assertEqual(kw["max_log_bytes"], 4 * 1024 * 1024)
            self.assertNotIn("CFLAGS", kw["env"])
            self.assertNotIn("DYLD_INSERT_LIBRARIES", kw["env"])
            self.assertNotIn("-isysroot", args)
        self.assertEqual(len(result["commands"]), len(self.calls))

    def test_explicit_sdk_applies_only_to_all_compile_link_commands(self):
        sdk = self.root / "SDK directory with spaces"
        sdk.mkdir()
        result = self.run_mocked(sdk)
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["sdk"], str(sdk.resolve()))
        compile_link_count = 0
        for args, kw in self.calls:
            if "-o" in args:
                compile_link_count += 1
                self.assertEqual(args.count("-isysroot"), 1)
                self.assertEqual(args[args.index("-isysroot") + 1], str(sdk.resolve()))
            else:
                self.assertNotIn("-isysroot", args)
            self.assertNotIn("SDKROOT", kw["env"])
            self.assertNotIn("DEVELOPER_DIR", kw["env"])
        self.assertEqual(compile_link_count, 29)

    def test_relative_sdk_is_rejected_before_launch(self):
        with self.assertRaises(host.VerificationError):
            self.run_mocked(Path("relative/sdk"))
        self.assertEqual(self.calls, [])

    def test_sdk_file_is_rejected_before_launch(self):
        sdk = self.root / "not-a-directory"
        sdk.write_text("synthetic")
        with self.assertRaises(host.VerificationError):
            self.run_mocked(sdk)
        self.assertEqual(self.calls, [])

    def test_missing_sdk_is_rejected_before_launch(self):
        with self.assertRaises(OSError):
            self.run_mocked(self.root / "missing-sdk")
        self.assertEqual(self.calls, [])

    def test_existing_output_is_rejected(self):
        output = self.root / "already"
        output.mkdir()
        with self.assertRaises(host.VerificationError):
            host.run_host_tests(self.source, output)

    def test_relative_compiler_is_rejected(self):
        with self.assertRaises(host.VerificationError):
            host.compiler_path("gcc")

    def test_missing_source_is_rejected(self):
        with self.assertRaises(OSError):
            host.run_host_tests(self.root / "missing", self.root / "out")

    def test_plain_failure_is_fatal(self):
        self.failure_name = "plain-run"
        result = self.run_mocked()
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["plain"]["outcome"], "failed")
        self.assertEqual(result["asan"]["outcome"], "not_run")

    def test_asan_fixture_failure_is_fatal(self):
        self.failure_name = "asan-run"
        result = self.run_mocked()
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["plain"]["outcome"], "passed")
        self.assertEqual(result["asan"]["outcome"], "failed")

    def test_unavailable_asan_probe_is_explicit(self):
        self.failure_name = "asan-probe-compile"
        result = self.run_mocked()
        self.assertEqual(result["outcome"], "passed_plain_asan_unavailable")
        self.assertEqual(result["asan"]["outcome"], "unavailable")

    def test_unavailable_asan_runtime_is_explicit(self):
        self.failure_name = "asan-probe-run"
        result = self.run_mocked()
        self.assertEqual(result["outcome"], "passed_plain_asan_unavailable")
        self.assertEqual(result["asan"]["stage"], "probe_run")

    def test_probe_timeout_is_not_downgraded_to_unavailable(self):
        self.failure_name = "asan-probe-run"
        self.failure_outcome = "timeout"
        result = self.run_mocked()
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["asan"]["outcome"], "failed")

    def test_probe_incomplete_cleanup_is_fatal(self):
        self.failure_name = "asan-probe-compile"
        self.incomplete_cleanup = True
        result = self.run_mocked()
        self.assertEqual(result["outcome"], "failed")

    def test_missing_or_duplicate_pass_line_is_rejected(self):
        with self.assertRaises(host.VerificationError):
            host.parse_success(SUCCESS.replace(host.PASS_LINES[-1], ""))
        with self.assertRaises(host.VerificationError):
            host.parse_success(SUCCESS + host.PASS_LINES[-1] + "\n")

    def test_context_alias_is_rejected(self):
        with self.assertRaises(host.VerificationError):
            host.parse_success(SUCCESS.replace("glue=216", "glue=208"))


if __name__ == "__main__":
    unittest.main()
