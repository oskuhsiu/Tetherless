# SPDX-License-Identifier: AGPL-3.0-only
"""Offline source-only checks; no native ABI/runtime or device acceptance claim."""
from collections import Counter
import hashlib
import importlib.util
from pathlib import Path
import re
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures/namespace_gateway"
spec = importlib.util.spec_from_file_location("namespace_gateway_under_test", HERE / "namespace_gateway.py")
namespace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(namespace)


def sha(data):
    return hashlib.sha256(data).hexdigest()


# Independent lexer used only to verify the frozen span manifest. The production
# helper never interprets arbitrary Swift or accepts any non-pinned preimage.
def code_only(source):
    out = list(source)
    def blank(a, b):
        for n in range(a, b):
            if out[n] != '\n':
                out[n] = ' '
    def string(i):
        start = i
        hashes = 0
        while source[i] == '#':
            hashes += 1
            i += 1
        mark = '"""' if source.startswith('"""', i) else '"'
        closing = mark + '#' * hashes
        escape = '\\' + '#' * hashes
        i += len(mark)
        blank(start, i)
        while i < len(source):
            if source.startswith(closing, i):
                blank(i, i + len(closing))
                return i + len(closing)
            if source.startswith(escape + '(', i):
                blank(i, i + len(escape) + 1)
                i = code(i + len(escape) + 1, 1)
                continue
            if source.startswith(escape, i):
                n = min(len(source), i + len(escape) + 1)
                blank(i, n)
                i = n
                continue
            blank(i, i + 1)
            i += 1
        raise ValueError('Unterminated string')
    def code(i, depth=0):
        while i < len(source):
            if source.startswith('//', i):
                end = source.find('\n', i)
                end = len(source) if end == -1 else end
                blank(i, end)
                i = end
            elif source.startswith('/*', i):
                start, count = i, 1
                i += 2
                while count:
                    if i >= len(source):
                        raise ValueError('Unterminated comment')
                    if source.startswith('/*', i):
                        count += 1
                        i += 2
                    elif source.startswith('*/', i):
                        count -= 1
                        i += 2
                    else:
                        i += 1
                blank(start, i)
            elif source[i] == '"' or re.match(r'#+"', source[i:i+12]):
                i = string(i)
            elif depth and source[i] == '(':
                depth += 1
                i += 1
            elif depth and source[i] == ')':
                depth -= 1
                if not depth:
                    blank(i, i + 1)
                    return i + 1
                i += 1
            else:
                i += 1
        if depth:
            raise ValueError('Unterminated interpolation')
        return i
    code(0)
    return ''.join(out)



class NamespaceGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = (FIXTURES / "IdeviceGateway.privacy-prepared.swift").read_bytes()
        cls.c_gateway = (FIXTURES / "LibimobiledeviceGateway.upstream.swift").read_bytes()
        cls.output = namespace.transform_gateway(cls.prepared)

    def test_exact_preimage_postimage_and_namespace_identities(self):
        self.assertEqual(sha(self.prepared), "1b66301e4ae70268ca3966639feed46271858265aa16a687dc4b144cf5179fb0")
        self.assertEqual(sha(self.output), "33cf02fbaf234a43e983dc590a5cf54fcaf24328e7e107593614dc2a20a6c08f")
        self.assertEqual(namespace.NAMESPACE_MAP_SHA256, "af7b427e402a76a3cfd3e3522a57e483ced59ce520b8338a84592b0ecff4f615")
        self.assertEqual(namespace.GATEWAY_PATH, "Dependencies/minimuxer/DeviceGateway/idevice/IdeviceGateway.swift")

    def test_exact_244_spans_and_102_distinct_identifiers(self):
        counts = Counter(name for _, name in namespace.TOKEN_SPANS)
        self.assertEqual(len(namespace.TOKEN_SPANS), 244)
        self.assertEqual(len(namespace.RENAMES), 102)
        self.assertEqual(set(counts), set(namespace.RENAMES))
        self.assertEqual(counts["plist_t"], 8)
        self.assertEqual(counts["PLIST_ERR_SUCCESS"], 1)
        self.assertEqual(counts["idevice_error_free"], 48)
        for old, new in namespace.RENAMES.items():
            prefix = "TETHERLESS_NATIVE_" if old.isupper() else "tetherless_native_"
            self.assertEqual(new, prefix + old)

    def test_span_manifest_exactly_matches_independent_executable_tokens(self):
        source = self.prepared.decode("utf-8")
        code = code_only(source)
        found = [(len(source[:m.start()].encode("utf-8")), m[0])
                 for m in re.finditer(r"\b[A-Za-z_][A-Za-z_0-9]*\b", code)
                 if m[0] in namespace.RENAMES]
        self.assertEqual(tuple(found), namespace.TOKEN_SPANS)
        raw_mentions = sum(len(re.findall(r"\b" + re.escape(name) + r"\b", source)) for name in namespace.RENAMES)
        self.assertGreater(raw_mentions, len(found))

    def test_function_values_as_well_as_direct_calls_are_renamed(self):
        source = self.prepared.decode()
        code = code_only(source)
        references = [m for m in re.finditer(r"\b[A-Za-z_][A-Za-z_0-9]*\b", code)
                      if m[0] in namespace.RENAMES and m[0] not in ("plist_t", "PLIST_ERR_SUCCESS")]
        calls = [m for m in references if re.match(r"\s*\(", code[m.end():])]
        self.assertEqual(len(references), 235)
        self.assertEqual(len(calls), 184)
        self.assertEqual(len(references) - len(calls), 51)
        self.assertIn(b"connectRP: tetherless_native_lockdownd_connect_rsd", self.output)
        self.assertIn(b"cleanup: tetherless_native_misagent_client_free", self.output)

    def test_every_unaffected_byte_is_preserved_and_inverse_is_exact(self):
        source_cursor = output_cursor = 0
        inverse = []
        for offset, name in namespace.TOKEN_SPANS:
            old, new = name.encode("ascii"), namespace.RENAMES[name].encode("ascii")
            gap_length = offset - source_cursor
            gap = self.output[output_cursor:output_cursor + gap_length]
            self.assertEqual(gap, self.prepared[source_cursor:offset])
            inverse.append(gap)
            output_cursor += gap_length
            self.assertEqual(self.output[output_cursor:output_cursor + len(new)], new)
            inverse.append(old)
            output_cursor += len(new)
            source_cursor = offset + len(old)
        self.assertEqual(self.output[output_cursor:], self.prepared[source_cursor:])
        inverse.append(self.output[output_cursor:])
        self.assertEqual(b"".join(inverse), self.prepared)

    def test_no_old_mapped_executable_identifiers_or_runtime_aliases_remain(self):
        code = code_only(self.output.decode())
        tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z_0-9]*\b", code))
        self.assertFalse(tokens.intersection(namespace.RENAMES))
        self.assertTrue(set(namespace.RENAMES.values()).issubset(tokens))
        self.assertNotIn("typealias", code)
        self.assertNotIn("_silgen_name", code)
        self.assertIn("import IDevice", code)

    def test_comments_and_log_string_text_are_unchanged(self):
        # These are native symbol spellings in non-executable text, not aliases.
        for line in self.prepared.splitlines():
            if line.lstrip().startswith((b"//", b"debugLog(", b"verboseLog(")):
                self.assertEqual(self.output.splitlines().count(line), self.prepared.splitlines().count(line))
        self.assertIn(b"// Native payload logging is disabled for the lifetime of this process.", self.output)
        self.assertIn(rb'getLockdownValue calling lockdownd_get_value for \(key)', self.output)
        self.assertNotIn(b"received pin:", self.output)
        self.assertNotIn(b"user entered PIN:", self.output)

    def test_interpolation_lexer_preserves_code_but_skips_nested_literal_text(self):
        sample = (r'let value = "plist_free \(plist_free(node)) \(other("plist_free"))" // plist_free' + '\n'
                  '/* plist_free */ plist_free(node)')
        names = re.findall(r"\bplist_free\b", code_only(sample))
        self.assertEqual(names, ["plist_free", "plist_free"])
        self.assertEqual(len(code_only(sample)), len(sample))
        raw = r'let value = #"plist_free \#(plist_free(node))"#'
        self.assertEqual(re.findall(r"\bplist_free\b", code_only(raw)), ["plist_free"])
        multiline = 'let value = """plist_free\n' + r'\(plist_free(node))' + '\n"""'
        self.assertEqual(re.findall(r"\bplist_free\b", code_only(multiline)), ["plist_free"])

    def test_each_executable_span_mutation_is_rejected(self):
        for offset, name in namespace.TOKEN_SPANS:
            with self.subTest(offset=offset, name=name):
                damaged = self.prepared[:offset] + bytes([self.prepared[offset] ^ 1]) + self.prepared[offset+1:]
                with self.assertRaisesRegex(ValueError, "preimage"):
                    namespace.transform_gateway(damaged)

    def test_mutations_in_each_unaffected_gap_are_rejected(self):
        cursor = 0
        gaps = []
        for offset, name in namespace.TOKEN_SPANS:
            if cursor < offset:
                gaps.append((cursor + offset) // 2)
            cursor = offset + len(name)
        gaps.append(len(self.prepared) - 1)
        for offset in gaps:
            with self.subTest(offset=offset):
                damaged = self.prepared[:offset] + bytes([self.prepared[offset] ^ 1]) + self.prepared[offset+1:]
                with self.assertRaisesRegex(ValueError, "preimage"):
                    namespace.transform_gateway(damaged)

    def test_wrong_type_empty_truncated_extended_crlf_and_double_application_fail(self):
        for value in (None, self.prepared.decode(), bytearray(self.prepared), b"", self.prepared[:-1],
                      self.prepared + b"\n", self.prepared.replace(b"\n", b"\r\n"), self.output):
            with self.subTest(kind=type(value).__name__, size=len(value) if value is not None else None):
                with self.assertRaises(ValueError):
                    namespace.transform_gateway(value)
        self.assertNotEqual(self.prepared, self.output)

    def test_determinism_and_no_input_or_fixture_mutation(self):
        before = self.prepared
        self.assertEqual(namespace.transform_gateway(before), self.output)
        self.assertEqual(namespace.transform_gateway(before), self.output)
        self.assertEqual(before, (FIXTURES / "IdeviceGateway.privacy-prepared.swift").read_bytes())

    def test_unchanged_c_gateway_has_exact_upstream_hash_and_is_rejected(self):
        before = self.c_gateway
        self.assertEqual(sha(before), "32964c92c48c8f6e5b115edee1afa109606c9221c0ab5381f9e3c3bd54f4aef1")
        blob = hashlib.sha1(b"blob " + str(len(before)).encode() + b"\0" + before).hexdigest()
        self.assertEqual(blob, "44de5253a53d05d85dd99a2e32e96fbf13531f0e")
        with self.assertRaisesRegex(ValueError, "preimage"):
            namespace.transform_gateway(before)
        self.assertEqual(before, (FIXTURES / "LibimobiledeviceGateway.upstream.swift").read_bytes())
        c_code = code_only(before.decode())
        overlaps = [m[0] for m in re.finditer(r"\b[A-Za-z_][A-Za-z_0-9]*\b", c_code) if m[0] in namespace.RENAMES]
        # This helper includes only the 102 actually used Rust identifiers;
        # the complete producer namespace map overlaps 77 C uses / 31 names.
        self.assertEqual(len(overlaps), 66)
        self.assertEqual(len(set(overlaps)), 26)
        self.assertIn("misagent_install(misagent, plistProfile)", c_code)
        self.assertIn("lockdownd_get_value(client, nil, key, &valNode)", c_code)

    def test_malformed_frozen_plan_is_rejected(self):
        variants = (namespace.TOKEN_SPANS[:-1], tuple(reversed(namespace.TOKEN_SPANS)),
                    ((namespace.TOKEN_SPANS[0][0] + 1, namespace.TOKEN_SPANS[0][1]),) + namespace.TOKEN_SPANS[1:])
        for spans in variants:
            with self.subTest(spans=spans[:1]), mock.patch.object(namespace, "TOKEN_SPANS", spans):
                with self.assertRaises(ValueError):
                    namespace.transform_gateway(self.prepared)
        wrong_map = dict(namespace.RENAMES, plist_free="plist_free")
        with mock.patch.object(namespace, "RENAMES", wrong_map):
            with self.assertRaisesRegex(ValueError, "span"):
                namespace.transform_gateway(self.prepared)
        with mock.patch.object(namespace, "POSTIMAGE_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "postimage"):
                namespace.transform_gateway(self.prepared)


if __name__ == "__main__":
    unittest.main()
