"""The actual transformed callback never reads or emits native payloads."""
from pathlib import Path
import hashlib
import importlib.util
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('emproxy_logging_safety', ROOT/'emproxy_logging_safety.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FIXTURE = Path(__file__).parent/'fixtures/EMProxyImpl.upstream.swift'


class EMProxyLoggingTests(unittest.TestCase):
    def test_exact_source_identity_and_callback_only_change(self):
        raw = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),m.EXPECTED)
        old = raw.decode(); new = m.patch(old)
        self.assertEqual(new.replace(m.NEW,m.OLD),old)
        self.assertEqual(new.count('set_log_callback'),1)
        self.assertNotIn('String(cString:',new)
        self.assertEqual(new.split('    public func start(',1)[1],old.split('    public func start(',1)[1])

    def test_transform_and_drift_rejection_preserve_input(self):
        for drift in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);p=root/m.SOURCE;p.parent.mkdir(parents=True)
                raw=FIXTURE.read_bytes()+(b'\n// drift' if drift else b'');p.write_bytes(raw)
                if drift:
                    with self.assertRaises(ValueError):m.apply(root)
                    self.assertEqual(p.read_bytes(),raw)
                else:
                    m.apply(root);output=p.read_bytes()
                    self.assertEqual(output.decode(),m.patch(raw.decode()))
                    with self.assertRaises(ValueError):m.apply(root)
                    self.assertEqual(p.read_bytes(),output)

    def test_callback_anchor_drift_rejected(self):
        with self.assertRaises(ValueError):m.patch(FIXTURE.read_text().replace('set_log_callback','set_other_callback'))

    def test_preparation_chain_registers_once(self):
        chain=(ROOT/'network_safety.py').read_text()
        self.assertEqual(chain.count('with_name("emproxy_logging_safety.py")'),1)
        self.assertLess(chain.index('with_name("native_logging_safety.py")'),chain.index('with_name("emproxy_logging_safety.py")'))

    @unittest.skipUnless(shutil.which('swiftc'),'Swift compiler unavailable; callback execution pending native CI')
    def test_actual_initializer_callback_debug_and_release(self):
        transformed=m.patch(FIXTURE.read_text())
        initializer=transformed.split('    public init() {',1)[1].split('    public func start(',1)[0].strip()
        self.assertTrue(initializer.endswith('}'))
        initializer='    public init() {'+initializer
        source='''import Foundation
+typealias LogCallback = @convention(c) (Int32, UnsafePointer<CChar>?) -> Bool
+enum Spy { nonisolated(unsafe) static var callback: LogCallback? }
+func set_log_callback(_ callback: LogCallback?) { Spy.callback = callback }
+final class CallbackOwner {
+'''.replace('\n+','\n')+initializer+'''
+}
+@main struct Main {
+ static func main() {
+  for _ in 0..<3 {
+   Spy.callback = nil
+   _ = CallbackOwner()
+   guard let callback = Spy.callback else { fatalError("callback missing") }
+   for level in [Int32.min, -1, 0, 1, 2, 3, Int32.max] {
+    precondition(callback(level, nil))
+    precondition(callback(level, UnsafePointer<CChar>(bitPattern: 1)))
+    "SYNTHETIC_EMAIL_PIN_TOKEN".withCString { precondition(callback(level, $0)) }
+   }
+  }
+  print("EMProxy callback privacy passed")
+ }
+}
+'''.replace('\n+','\n')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);swift=p/'Probe.swift';swift.write_text(source)
            for mode,flags in [('Debug',['-D','DEBUG','-Onone']),('Release',['-O'])]:
                binary=p/mode
                built=subprocess.run([shutil.which('swiftc'),'-swift-version','6','-parse-as-library',*flags,str(swift),'-o',str(binary)],capture_output=True,text=True,timeout=60)
                self.assertEqual(built.returncode,0,built.stderr)
                ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
                self.assertEqual(ran.returncode,0,ran.stderr)
                self.assertEqual(ran.stdout,'EMProxy callback privacy passed\n')
                self.assertEqual(ran.stderr,'')


if __name__=='__main__': unittest.main()
