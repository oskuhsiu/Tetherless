import argparse
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import build_provider as b

class MainAuditTests(unittest.TestCase):
    def argv(self,root):
        return ['build_provider.py','--source',str(root/'source'),'--openssl',str(root/'ssl'),
                '--old-provider',str(root/'old'),'--work',str(root/'work')]
    def test_primary_build_exception_survives_audit_failure(self):
        with tempfile.TemporaryDirectory() as d:
            error=RuntimeError('original compile failure')
            def fail(args):args._work_created=True;raise error
            with patch.object(sys,'argv',self.argv(Path(d))),patch.object(b,'build',side_effect=fail),patch.object(b,'final_audits',side_effect=ValueError('audit secondary')):
                with self.assertRaises(RuntimeError) as observed:b.main()
            self.assertIs(observed.exception,error)
    def test_false_audit_after_success_fails(self):
        with tempfile.TemporaryDirectory() as d:
            def ok(args):args._work_created=True
            with patch.object(sys,'argv',self.argv(Path(d))),patch.object(b,'build',side_effect=ok),patch.object(b,'final_audits',return_value={'all_passed':False}):
                with self.assertRaisesRegex(ValueError,'final input integrity'):b.main()
    def test_audit_exception_after_success_fails(self):
        with tempfile.TemporaryDirectory() as d:
            def ok(args):args._work_created=True
            with patch.object(sys,'argv',self.argv(Path(d))),patch.object(b,'build',side_effect=ok),patch.object(b,'final_audits',side_effect=OSError('audit write failure')):
                with self.assertRaisesRegex(OSError,'audit write'):b.main()
    def test_preexisting_work_never_written_by_audit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);work=root/'work';work.mkdir();(work/'sentinel').write_text('unchanged')
            with patch.object(sys,'argv',self.argv(root)),patch.object(b,'final_audits') as audit:
                with self.assertRaisesRegex(ValueError,'fresh'):b.main()
                audit.assert_not_called()
            self.assertEqual({p.name for p in work.iterdir()},{'sentinel'})
            self.assertEqual((work/'sentinel').read_text(),'unchanged')

class FinalInputAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.args=argparse.Namespace(source=root/'source',openssl=root/'ssl',old_provider=root/'old',work=root/'work')
        for p in [self.args.source,self.args.openssl,self.args.old_provider,self.args.work]:p.mkdir()
        self.evidence=self.args.work/'evidence';self.evidence.mkdir();self.prefix=root/'tool';self.prefix.mkdir()
        (self.prefix/'macro').write_text('original');macros=self.args.work/'tool-macros';macros.mkdir();(macros/'pkg.m4').write_text('pkg')
        self.original_recipe={'a':{'sha256':'test','bytes':4}}
        b.write(self.evidence/'recipe-inputs.json',self.original_recipe)
        b.write(self.evidence/'toolchain.json',{'tools':{},'tool_installation_closures':{str(self.prefix):b.closure_inventory(self.prefix)},'pkg_m4_sha256':b.sha256(b'pkg')})
        for name,replacement in [('verify_retained',lambda p:{}),('verify_old',lambda p,t:{}),('load_openssl',lambda:SimpleNamespace(verify_inputs=lambda p:{})),('recipe_inventory',lambda:self.original_recipe)]:
            patcher=patch.object(b,name,replacement);patcher.start();self.addCleanup(patcher.stop)
    def run_audit(self):
        return b.final_audits(self.args)
    def test_good_inputs_pass_and_receipt_retained(self):
        self.assertTrue(self.run_audit()['all_passed']);self.assertTrue((self.evidence/'final-input-audit.json').is_file())
    def test_added_tool_closure_member_rejected(self):
        (self.prefix/'extra').write_text('new')
        r=self.run_audit();self.assertFalse(r['all_passed']);self.assertFalse(r['checks']['toolchain_inputs']['passed'])
    def test_deleted_tool_closure_member_rejected(self):
        (self.prefix/'macro').unlink();self.assertFalse(self.run_audit()['checks']['toolchain_inputs']['passed'])
    def test_changed_tool_closure_member_rejected(self):
        (self.prefix/'macro').write_text('changed');self.assertFalse(self.run_audit()['checks']['toolchain_inputs']['passed'])
    def test_recipe_mutation_rejected(self):
        with patch.object(b,'recipe_inventory',return_value={'a':{'sha256':'changed','bytes':4}}):
            self.assertFalse(self.run_audit()['checks']['recipe_inputs']['passed'])
    def test_copied_macro_mutation_rejected(self):
        (self.args.work/'tool-macros/pkg.m4').write_text('changed');self.assertFalse(self.run_audit()['checks']['toolchain_inputs']['passed'])
    def test_missing_toolchain_observation_is_not_a_pass(self):
        (self.evidence/'toolchain.json').unlink();self.assertFalse(self.run_audit()['checks']['toolchain_inputs']['passed'])
    def test_multiple_audit_failures_all_retained(self):
        with patch.object(b,'verify_retained',side_effect=ValueError('source changed')),patch.object(b,'verify_old',side_effect=ValueError('C changed')):
            r=self.run_audit();self.assertFalse(r['all_passed']);self.assertFalse(r['checks']['pristine_source']['passed']);self.assertFalse(r['checks']['original_c_iphoneos']['passed']);self.assertFalse(r['checks']['original_c_iphonesimulator']['passed'])


class PreinstalledM4Tests(unittest.TestCase):
    def test_missing_keg_does_not_fall_back_to_system_m4(self):
        with patch.object(b.Path,'is_file',return_value=False),patch.object(b.shutil,'which',return_value='/usr/bin/m4') as which:
            with self.assertRaisesRegex(ValueError,'missing'):b.resolve_preinstalled_tool('m4','m4','/usr/bin')
            which.assert_not_called()
    def test_existing_verified_opt_route(self):
        target=Path('/opt/homebrew/Cellar/m4/1.4.20/bin/m4')
        with patch.object(b.Path,'is_file',return_value=True),patch.object(b.Path,'resolve',return_value=target),patch.object(b.shutil,'which') as which:
            self.assertEqual(b.resolve_preinstalled_tool('m4','m4','/usr/bin'),target)
            which.assert_not_called()
    def test_opt_route_cannot_resolve_to_system_m4(self):
        target=Path('/usr/bin/m4')
        with patch.object(b.Path,'is_file',return_value=True),patch.object(b.Path,'resolve',return_value=target):
            with self.assertRaisesRegex(ValueError,'Homebrew GNU'):b.resolve_preinstalled_tool('m4','m4','/usr/bin')

if __name__=='__main__':unittest.main()
