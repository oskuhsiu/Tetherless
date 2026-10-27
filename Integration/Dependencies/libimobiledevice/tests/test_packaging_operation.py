"""C producer reuses the existing reviewed operation; no Xcode execution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import build_provider as b
import xcframework_operation as operation

class CPackagingOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(strict=True)
        self.evidence=self.root/'evidence';self.evidence.mkdir()
        self.records=[{'sdk':sdk,'library':str(self.root/(sdk+'.a')),'headers':str(self.root/(sdk+' headers'))}
                      for sdk in ['iphoneos','iphonesimulator']]
        self.output=self.root/'libimobiledevice.xcframework'
        self.runner=SimpleNamespace(evidence=self.evidence,run=Mock(),
            env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                 'DEVELOPER_DIR':b.DEVELOPER,'HOME':str(self.root/'home'),'TMPDIR':str(self.root/'tmp'),
                 'LANG':'en_US.UTF-8','UNRELATED':'not-for-child'})
    def test_existing_wrapper_source_pin_matches_reviewed_rust_recipe(self):
        self.assertEqual(hashlib.sha256(b.XCFRAMEWORK_OPERATION.read_bytes()).hexdigest(),b.XCFRAMEWORK_OPERATION_SHA256)
        recipe=json.loads((b.SIBLING/'apple-recipe-files.json').read_bytes())
        self.assertEqual(recipe['xcframework_operation.py'],b.XCFRAMEWORK_OPERATION_SHA256)
    def test_owned_wrapper_receives_exact_command_environment_and_hashes(self):
        receipt=b.package_xcframework(self.runner,self.records,self.output)
        arguments=[value for row in self.records for value in (row['library'],row['headers'])]+[str(self.output)]
        expected=[sys.executable,'-I',str(b.XCFRAMEWORK_OPERATION),*arguments]
        actual=self.runner.run.call_args
        self.assertEqual(actual.args,(expected,'create-xcframework'))
        self.assertEqual(set(actual.kwargs),{'env'})
        environment=actual.kwargs['env']
        self.assertEqual(set(environment),set(operation.ENVIRONMENT_KEYS))
        self.assertEqual(environment['PATH'],'/usr/bin:/bin:/usr/sbin:/sbin')
        self.assertNotIn('UNRELATED',environment)
        self.assertEqual(receipt['xcodebuild_command'],operation.packaging_command(arguments))
        self.assertEqual(receipt['operation_command_sha256'],b.sha256(json.dumps(expected,separators=(',',':'),ensure_ascii=False).encode()))
        self.assertEqual(receipt['timeout_seconds'],900)
        self.assertFalse(receipt['ios_payloads_executed'])
        self.assertEqual(json.loads((self.evidence/'xcframework-operation.json').read_bytes()),receipt)
    def test_unexpected_slice_count_order_or_relative_path_rejected(self):
        for records,output in [(self.records[:1],self.output),(list(reversed(self.records)),self.output),
                               (self.records,Path('relative.xcframework')),
                               ([{**self.records[0],'library':'relative.a'},self.records[1]],self.output)]:
            with self.subTest(records=records,output=output),self.assertRaises(ValueError):
                b.package_xcframework(self.runner,records,output)
        self.runner.run.assert_not_called()
    def test_modified_wrapper_rejected_before_launch(self):
        modified=self.root/'modified.py';modified.write_text('not the reviewed wrapper')
        with patch.object(b,'XCFRAMEWORK_OPERATION',modified),self.assertRaises(ValueError):
            b.package_xcframework(self.runner,self.records,self.output)
        self.runner.run.assert_not_called()
    def test_supervisor_failure_preserved_without_receipt(self):
        failure=ValueError('bounded cleanup failure');self.runner.run.side_effect=failure
        with self.assertRaises(ValueError) as observed:b.package_xcframework(self.runner,self.records,self.output)
        self.assertIs(observed.exception,failure)
        self.assertFalse((self.evidence/'xcframework-operation.json').exists())
    def test_wrapper_change_during_operation_fails_closed(self):
        local=self.root/'operation.py';local.write_bytes(b.XCFRAMEWORK_OPERATION.read_bytes())
        self.runner.run.side_effect=lambda *args,**kwargs:local.write_bytes(b'changed')
        with patch.object(b,'XCFRAMEWORK_OPERATION',local),self.assertRaises(ValueError):
            b.package_xcframework(self.runner,self.records,self.output)
        self.assertFalse((self.evidence/'xcframework-operation.json').exists())

if __name__=='__main__':unittest.main()
