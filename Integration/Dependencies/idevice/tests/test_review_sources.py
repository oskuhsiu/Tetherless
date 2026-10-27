import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('retain_review_sources', ROOT / 'retain_review_sources.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def archive(rows):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode='w:gz') as t:
        for name, content, kind in rows:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            entry.size = len(content)
            t.addfile(entry, io.BytesIO(content))
    return b.getvalue()

class ReviewSourcesTests(unittest.TestCase):
    def run_archive(self, rows, selected=None):
        data = archive(rows)
        return m.selected_archive(data, 'crate-1', m.digest(data), selected or ['src/lib.rs'])
    def test_only_allowlisted_source_retained(self):
        self.assertEqual(self.run_archive([('crate-1/src/lib.rs', b'public', tarfile.REGTYPE), ('crate-1/other', b'not retained', tarfile.REGTYPE)]), {'src/lib.rs': b'public'})
    def test_missing_member_is_not_substituted(self):
        self.assertEqual(self.run_archive([('crate-1/other.rs', b'public', tarfile.REGTYPE)]), {})
    def test_checksum_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            m.selected_archive(b'bad', 'crate-1', '0'*64, ['src/lib.rs'])
    def test_selected_symlink_rejected(self):
        with self.assertRaises(ValueError):
            self.run_archive([('crate-1/src/lib.rs', b'', tarfile.SYMTYPE)])
    def test_duplicate_member_rejected(self):
        with self.assertRaises(ValueError):
            self.run_archive([('crate-1/src/lib.rs', b'a', tarfile.REGTYPE)]*2)
    def test_traversal_even_unselected_rejected(self):
        with self.assertRaises(ValueError):
            self.run_archive([('crate-1/../private', b'a', tarfile.REGTYPE)])
    def test_selected_member_bound(self):
        with self.assertRaises(ValueError):
            self.run_archive([('crate-1/src/lib.rs', b'a'*(m.MAX_FILE+1), tarfile.REGTYPE)])

if __name__ == '__main__':
    unittest.main()
