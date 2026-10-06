"""Pinned multi-target project scope fixtures; no xcodebuild execution."""
import hashlib
from pathlib import Path
import re
import sys
import unittest
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import diagnostic_link_project as project
import run_compile

class DiagnosticLinkProjectTests(unittest.TestCase):
    def setUp(self):self.original=(HERE/'upstream/SideStore-project.pbxproj').read_bytes()
    def test_only_two_SideStore_configuration_blocks_change(self):
        patched=project.patch_project(self.original).decode();original=self.original.decode()
        pattern=r'^\t\t([A-F0-9]{24})[^\n]* = \{\n.*?^\t\t};'
        before={m[1]:m[0] for m in re.finditer(pattern,original,re.M|re.S)}
        after={m[1]:m[0] for m in re.finditer(pattern,patched,re.M|re.S)}
        self.assertEqual(before.keys(),after.keys())
        changed={k for k in before if before[k]!=after[k]}
        self.assertEqual(changed,set(project.CONFIGURATIONS.values()))
        self.assertIn('AltWidgetExtension',original);self.assertIn('SideBackup',original)
        for identity in changed:
            for root in project.APP_C_ROOTS|project.APP_RUST_ROOTS:self.assertIn('"-Wl,-u,'+root+'",',after[identity])
            for framework in project.C_SYSTEM_FRAMEWORKS:self.assertIn('"'+framework+'",',after[identity])
            self.assertIn('"$(inherited)",\n\t\t\t\t\t"-Xlinker",\n\t\t\t\t\t"-w",',after[identity])
    def test_global_xcodebuild_override_does_not_leak_app_roots_to_siblings(self):
        command=run_compile.command(Path('/fixture/app'),Path('/fixture/work'),'Debug','iphoneos',
            {'configurations':['Debug','Release'],'required_conditions':[]})
        self.assertFalse(any(x.startswith('OTHER_LDFLAGS=') for x in command))
        self.assertFalse(any(root in ' '.join(command) for root in project.APP_C_ROOTS|project.APP_RUST_ROOTS))
    def test_missing_changed_and_already_patched_preimage_fail(self):
        for raw in (b'',self.original+b'\n',self.original.replace(b'AltWidgetExtension',b'OtherExtension'),project.patch_project(self.original)):
            with self.subTest(raw=hashlib.sha256(raw).hexdigest()),self.assertRaises(ValueError):project.patch_project(raw)

if __name__=='__main__':unittest.main()
