"""Fixed test-only boundary observations; all original executable tokens remain."""
import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PREIMAGES = {
    "MutationScopeTests.swift": "34f045ce7dbc71b8b56fffdebbdde51997ea5f0ab394b973f58f525d48676b85",
    "ProcessLeaseScopeTests.swift": "77de33dc33d2452b93d4c71f583581906bfb2338f205b1e0c2b6556a03143fe0",
}

def source(name):
    return (ROOT / "Tests/TetherlessCoreTests" / name).read_text()

def original_tokens(text):
    text = re.sub(r"// BEGIN ASSERTION_BOUNDARY_TIMING_DECLARATIONS\n.*?// END ASSERTION_BOUNDARY_TIMING_DECLARATIONS\n", "", text, flags=re.S)
    text = "".join(line for line in text.splitlines(True) if "// ASSERTION_BOUNDARY_TIMING" not in line)
    text = text.replace("return try ProcessLease.acquire(at: url) // ASSERTION_BOUNDARY_RETURN", "try ProcessLease.acquire(at: url)")
    return "".join(text.split()).encode()

class CoreAssertionDiagnosticTests(unittest.TestCase):
    def test_original_executable_tokens_and_existing_observations_are_unchanged(self):
        for name, digest in PREIMAGES.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256(original_tokens(source(name))).hexdigest(), digest)

    def test_expected_error_bodies_emit_exit_even_when_the_original_call_throws(self):
        text = source("MutationScopeTests.swift")
        self.assertIn("defer { ScopeTimingTrace.emit(.admittedBusyBodyAfter) }", text)
        self.assertIn("defer { ScopeTimingTrace.emit(.lateAwaitBodyAfter) }", text)
        self.assertIn("defer { LeaseAssertionTimingTrace.emit(.busyBodyAfter) }", source("ProcessLeaseScopeTests.swift"))
        for name in ("admittedCountsAcquiredBefore", "admittedCountsAcquiredAfter", "admittedCountsReleasedBefore", "admittedCountsReleasedAfter", "admittedBusyExpectBefore", "admittedBusyExpectAfter", "admittedBusyBodyBefore", "admittedBusyBodyAfter", "lateAwaitBodyBefore", "lateAwaitBodyAfter"):
            self.assertEqual(text.count("case " + name + " // ASSERTION_BOUNDARY_TIMING"), 1)
            self.assertEqual(text.count("emit(." + name + ")"), 1)

    def test_original_process_lease_result_type_is_explicitly_returned(self):
        text = source("ProcessLeaseScopeTests.swift")
        self.assertEqual(text.count("return try ProcessLease.acquire(at: url) // ASSERTION_BOUNDARY_RETURN"), 1)

    def test_original_case_deadlines_and_test_counts_are_preserved(self):
        for name, count in (("MutationScopeTests.swift", 5), ("ProcessLeaseScopeTests.swift", 4)):
            text = source(name)
            self.assertEqual(text.count("@Test func"), count)
            self.assertEqual(text.count(".timeLimit(.minutes(1))"), 1)
            self.assertNotIn(".serialized", text)
            self.assertNotIn("Task.sleep", text)

    def test_new_trace_accepts_only_fixed_enum_events_and_clocks(self):
        text = source("ProcessLeaseScopeTests.swift")
        block = text.split("// BEGIN ASSERTION_BOUNDARY_TIMING_DECLARATIONS", 1)[1].split("// END ASSERTION_BOUNDARY_TIMING_DECLARATIONS", 1)[0]
        self.assertIn("emit(_ event: LeaseAssertionTimingEvent)", block)
        self.assertEqual(block.count("print("), 1)
        self.assertIn("DispatchTime.now().uptimeNanoseconds", block)
        for forbidden in ("url.path", "String(describing", "error", "contentsOf", "Data("):
            self.assertNotIn(forbidden, block)

if __name__ == "__main__": unittest.main()
