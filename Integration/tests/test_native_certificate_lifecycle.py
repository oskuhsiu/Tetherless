"""Pinned transformed-source and real local crypto adapter checks; not iOS acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import platform
import unittest
ROOT = Path(__file__).parents[1]
REPO = ROOT.parent
spec = importlib.util.spec_from_file_location('lifecycle', ROOT / 'certificate_lifecycle_safety.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class NativeLifecycleTests(unittest.TestCase):
    def test_real_pinned_transforms_remove_default_revocation_and_raw_exports(self):
        vendor = REPO / 'Vendor/SideStore'
        if not (vendor / m.HANDLER).exists(): self.skipTest('Pinned SideStore checkout unavailable')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for path in m.BLOBS:
                dest = root / path; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(vendor / path, dest)
            resources = root / 'SideStore/TetherlessNative/SigningCrypto'
            shutil.copytree(ROOT / 'Native/SigningCrypto', resources)
            project = root / 'AltStore.xcodeproj/project.pbxproj'; project.parent.mkdir(parents=True)
            shutil.copyfile(vendor / 'AltStore.xcodeproj/project.pbxproj', project)
            m.apply(root)
            self.assertFalse(resources.exists())
            for name in ['TetherlessForge.min.js', 'TetherlessSigningCrypto.js', 'TetherlessCryptoEnvironment.js']:
                self.assertTrue((root / 'TetherlessSigningResources' / name).is_file())
                self.assertIn(name + ' in Resources', project.read_text())
            handler = (root / m.HANDLER).read_text()
            body = handler.split('func resolveRevocation', 1)[1].split('func resolveTeam', 1)[0]
            self.assertIn('NativeCertificateQuotaPrompt.choose', body)
            self.assertNotIn('RevokeCertificatesAlertViewController', body)
            exporter = (root / m.EXPORTER).read_text()
            self.assertNotIn('encryptedP12Data', exporter)
            self.assertNotIn('sharePrivateKey', exporter)
            self.assertNotIn('copyPrivateKey', exporter)
            self.assertNotIn('CertificateExporter.copyPrivateKey', (root / m.ROW).read_text())
            self.assertNotIn('UIPasteboard.general.string = privateKey', (root / m.DETAIL).read_text())
            with self.assertRaises(ValueError): m.apply(root)
    def test_legacy_import_cannot_bypass_bounded_validated_route(self):
        module_spec = importlib.util.spec_from_file_location('legacy_cert_safety', ROOT / 'certificate_safety.py')
        legacy = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(legacy)
        source = REPO / 'Vendor/SideStore' / legacy.VIEW
        if not source.exists(): self.skipTest('Pinned SideStore checkout unavailable')
        result = legacy.patch_view(source.read_text())
        self.assertNotIn('ALTCertificate(p12Data:', result)
        self.assertIn('func startBulkImport(urls: [URL]) { useValidatedSigningImport() }', result)
        raw = (REPO / 'Vendor/SideStore' / legacy.KEY_INPUT).read_text()
        self.assertIn('throw CertificateExportFailure.useValidatedImport', legacy.patch_key_input(raw))

    def test_single_exact_fresh_certificate_and_cancellation(self):
        flow = (ROOT / 'Overrides/CertificateProvisioningFlow.swift').read_text()
        self.assertIn('guard selected.count == 1', flow)
        self.assertIn('confirmedSnapshot.filter', flow)
        self.assertLess(flow.index('let confirmedSnapshot'), flow.index('revokeCertificate(cert'))
        prompt = (ROOT / 'Native/NativeCertificateQuotaPrompt.swift').read_text()
        for text in ['withTaskCancellationHandler', 'guard !finished', 'didEnterBackgroundNotification',
                     '.revokeSelected([certificate])', 'Team: \\(teamID)', 'invalidates profiles', 'may stop installed apps']:
            self.assertIn(text, prompt)
    def test_pinned_resources_and_no_secret_string_interpolation(self):
        bridge = (ROOT / 'Native/NativeEncryptedP12.swift').read_text()
        for name in ['TetherlessForge.min.js', 'TetherlessSigningCrypto.js', 'TetherlessCryptoEnvironment.js']:
            digest = hashlib.sha256((ROOT / 'Native/SigningCrypto' / name).read_bytes()).hexdigest()
            self.assertIn(digest, bridge)
        self.assertIn('call(withArguments:', bridge)
        self.assertIn('SecRandomCopyBytes', bridge)
        self.assertIn('Math.random = function () { throw', (ROOT / 'Native/SigningCrypto/TetherlessCryptoEnvironment.js').read_text())
        self.assertNotIn('URLSession', bridge)
        self.assertNotIn('debugLog', bridge)
        helper = (ROOT / 'Native/NativeSigningMaterial.swift').read_text()
        self.assertIn('SecPKCS12Import', helper)
        self.assertIn('password: password + "-incorrect"', helper)
        export = helper.split('static func encryptedP12', 1)[1].split('static func backup', 1)[0]
        self.assertNotIn('CertificateManager.convert', export)
        controls = (ROOT / 'Native/NativeSigningMaterialControls.swift').read_text()
        self.assertIn('Task.detached', controls)
        self.assertIn('operation?.cancel()', controls)

    @unittest.skipUnless(platform.system() == 'Darwin' and shutil.which('swiftc') and shutil.which('openssl'), 'macOS Swift/JavaScriptCore/Security needed; Node is not native evidence')
    def test_actual_native_bridge_security_import_and_missing_resource_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def run(*args, ok=True):
                result = subprocess.run(args, cwd=root, capture_output=True, timeout=180)
                if ok: self.assertEqual(result.returncode, 0, result.stderr.decode()[:1000])
                return result
            run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'key.pem', '-out', 'cert.pem', '-subj', '/CN=Native-Synthetic-Not-Apple', '-days', '2')
            run('openssl', 'x509', '-in', 'cert.pem', '-outform', 'DER', '-out', 'cert.der')
            run('openssl', 'pkcs8', '-topk8', '-nocrypt', '-in', 'key.pem', '-outform', 'DER', '-out', 'key.der')
            version = run('openssl', 'version').stdout.decode().strip()
            print('native_crypto_environment macOS=' + platform.mac_ver()[0] + ' openssl=' + version, flush=True)
            # Diagnostic controls only: never replace the product AES output or
            # relax its Security readback assertion. Some OpenSSL builds lack
            # these options; an absent control is explicitly not evidence.
            for name, algorithm in [('control-aes.p12', 'AES-256-CBC'), ('control-3des.p12', 'PBE-SHA1-3DES')]:
                control = run('openssl', 'pkcs12', '-export', '-inkey', 'key.pem', '-in', 'cert.pem', '-out', name,
                    '-passout', 'pass:synthetic-native-backup-only', '-keypbe', algorithm, '-certpbe', algorithm,
                    '-macalg', 'sha1', ok=False)
                print('native_crypto_control ' + name + ' generation_exit=' + str(control.returncode), flush=True)
                if control.returncode: (root / name).unlink(missing_ok=True)
                else:
                    inventory = run('openssl', 'pkcs12', '-in', name, '-passin', 'pass:synthetic-native-backup-only', '-info', '-noout', ok=False)
                    for line in inventory.stderr.decode().splitlines():
                        if line.startswith(('MAC:', 'MAC Iteration', 'Shrouded Keybag', 'PKCS7 Encrypted data')):
                            print('native_crypto_control ' + name + ' ' + line, flush=True)
            # Test-only same-library controls isolate algorithm vs iteration.
            # Product export and its readback assertion remain AES-256/100000.
            control_script = r'''const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const resources=process.argv[2], c=vm.createContext({nativeSecureRandom:n=>Array.from(crypto.randomBytes(n))});
for(const name of ['TetherlessCryptoEnvironment.js','TetherlessForge.min.js','TetherlessSigningCrypto.js'])vm.runInContext(fs.readFileSync(resources+'/'+name,'utf8'),c);
c.cert=fs.readFileSync('cert.der').toString('base64');c.key=fs.readFileSync('key.der').toString('base64');
for(const [name,algorithm,count,prf] of [['control-forge-aes-2048.p12','aes256',2048,'sha1'],['control-forge-3des-100000.p12','3des',100000,'sha1'],['control-forge-aes-sha256-100000.p12','aes256',100000,'sha256']]) {
 c.algorithm=algorithm;c.count=count;c.prf=prf;
 const value=vm.runInContext("forge.util.encode64(forge.asn1.toDer(forge.pkcs12.toPkcs12Asn1(forge.pki.privateKeyFromAsn1(forge.asn1.fromDer(forge.util.decode64(key))),[forge.pki.certificateFromAsn1(forge.asn1.fromDer(forge.util.decode64(cert)))],'synthetic-native-backup-only',{algorithm:algorithm,count:count,prfAlgorithm:prf,saltSize:16,useMac:true})).getBytes())",c);
 fs.writeFileSync(name,Buffer.from(value,'base64'));
}
'''
            (root / 'controls.cjs').write_text(control_script)
            run('node', 'controls.cjs', str(ROOT / 'Native/SigningCrypto'))
            bundle = root / 'NativeCryptoTest.app/Contents'
            resources = bundle / 'Resources'; resources.mkdir(parents=True)
            executable = bundle / 'MacOS/native-check'; executable.parent.mkdir()
            import plistlib
            (bundle / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.tetherless.synthetic.crypto','CFBundleExecutable':'native-check','CFBundlePackageType':'APPL'}))
            for file in (ROOT / 'Native/SigningCrypto').glob('*.js'): shutil.copyfile(file, resources / file.name)
            harness = r'''import Foundation
import Security
enum NativeHarnessFailure: Error { case securityReadback(correct: OSStatus, empty: OSStatus, wrong: OSStatus, opensslAES: OSStatus?, openssl3DES: OSStatus?, forgeAES2048: OSStatus?, forge3DES100000: OSStatus?, forgeAESSHA256100000: OSStatus?) }
@main struct Check {
 static func main() async throws {
  let root = URL(fileURLWithPath: CommandLine.arguments[1]), password = "synthetic-native-backup-only"
  let bytes = try await Task.detached {
    try NativeEncryptedP12.export(certificateDER: Data(contentsOf: root.appendingPathComponent("cert.der")), privateKeyDER: Data(contentsOf: root.appendingPathComponent("key.der")), password: password)
  }.value
  // macOS otherwise persists identities in the default Keychain, unlike iOS.
  // The CI runner is macOS 15; require its public memory-only option so this
  // synthetic test measures decoding, never Keychain unlock or persistence.
  guard #available(macOS 15.0, *) else { throw CertificateExportFailure.unavailable }
  let memoryOnlyKey = kSecImportToMemoryOnly as String
  func imported(_ password: String) -> OSStatus { var entries: CFArray?; return SecPKCS12Import(bytes as CFData, [kSecImportExportPassphrase as String:password, memoryOnlyKey:true] as CFDictionary, &entries) }
  func control(_ name: String) -> OSStatus? {
    guard let control = try? Data(contentsOf: root.appendingPathComponent(name)) else { return nil }
    var entries: CFArray?
    return SecPKCS12Import(control as CFData, [kSecImportExportPassphrase as String: password, memoryOnlyKey:true] as CFDictionary, &entries)
  }
  let correct = imported(password), empty = imported(""), wrong = imported("incorrect")
  let aes = control("control-aes.p12"), tripleDES = control("control-3des.p12")
  let forgeAES = control("control-forge-aes-2048.p12"), forge3DES = control("control-forge-3des-100000.p12")
  let forgeAESSHA256 = control("control-forge-aes-sha256-100000.p12")
  guard correct == errSecSuccess, empty != errSecSuccess, wrong != errSecSuccess else {
    // Synthetic fixture only: fixed stage and numeric status, never key/password/P12.
    throw NativeHarnessFailure.securityReadback(correct: correct, empty: empty, wrong: wrong, opensslAES: aes, openssl3DES: tripleDES, forgeAES2048: forgeAES, forge3DES100000: forge3DES, forgeAESSHA256100000: forgeAESSHA256)
  }
  try bytes.write(to: root.appendingPathComponent("native.p12"))
 }
}
'''
            (root / 'Harness.swift').write_text(harness)
            run('swiftc', '-parse-as-library', str(REPO / 'Sources/TetherlessCore/CertificateExportPolicy.swift'), str(ROOT / 'Native/NativeEncryptedP12.swift'), 'Harness.swift', '-o', str(executable))
            run(str(executable), str(root))
            run('openssl','pkcs12','-in','native.p12','-passin','pass:synthetic-native-backup-only','-info','-noout')
            (resources / 'TetherlessSigningCrypto.js').write_text('throw new Error("tampered");')
            self.assertNotEqual(run(str(executable), str(root), ok=False).returncode, 0)
            (resources / 'TetherlessSigningCrypto.js').unlink()
            self.assertNotEqual(run(str(executable), str(root), ok=False).returncode, 0)

    @unittest.skipUnless(shutil.which('openssl') and shutil.which('node'), 'Node/OpenSSL required')
    def test_actual_bundled_forge_p12_openssl_password_mac_and_entropy_failures(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def run(*args, ok=True):
                result = subprocess.run(args, cwd=root, capture_output=True, timeout=120)
                if ok: self.assertEqual(result.returncode, 0, result.stderr.decode()[:1000])
                return result
            run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'key.pem', '-out', 'cert.pem', '-subj', '/CN=Synthetic-not-Apple', '-days', '2')
            run('openssl', 'x509', '-in', 'cert.pem', '-outform', 'DER', '-out', 'cert.der')
            run('openssl', 'pkcs8', '-topk8', '-nocrypt', '-in', 'key.pem', '-outform', 'DER', '-out', 'key.der')
            script = r'''
const fs=require('node:fs'), vm=require('node:vm'), crypto=require('node:crypto');
const resource=process.argv[2], password='synthetic-test-password-only';
function context(mode) {
  const c=vm.createContext({nativeSecureRandom(n) {if(mode==='fail')return null;if(mode==='short')return [];return Array.from(crypto.randomBytes(n));}});
  vm.runInContext(fs.readFileSync(resource+'/TetherlessCryptoEnvironment.js','utf8'),c);
  vm.runInContext(fs.readFileSync(resource+'/TetherlessForge.min.js','utf8'),c);
  vm.runInContext(fs.readFileSync(resource+'/TetherlessSigningCrypto.js','utf8'),c); return c;
}
const cert=fs.readFileSync('cert.der').toString('base64'), key=fs.readFileSync('key.der').toString('base64');
const seed=vm.createContext({nativeSecureRandom:n=>Array.from({length:n},(_,i)=>i+1)});vm.runInContext(fs.readFileSync(resource+'/TetherlessCryptoEnvironment.js','utf8'),seed);const bytes=vm.runInContext('var a=new Uint32Array(2);crypto.getRandomValues(a);Array.from(new Uint8Array(a.buffer))',seed);if(JSON.stringify(bytes)!=='[1,2,3,4,5,6,7,8]')throw Error('partialEntropy');
const c=context('ok'), pfx=c.tetherlessEncryptP12(cert,key,password);
fs.writeFileSync('identity.p12',Buffer.from(pfx,'base64'));
if(c.tetherlessValidateP12(pfx,password)!=='valid')throw Error('validImportRejected');
for(const bad of ['', 'wrong']) {let rejected=false;try{c.tetherlessValidateP12(pfx,bad)}catch{rejected=true}if(!rejected)throw Error('badPasswordImport');}
// Rebuild a valid-MAC PFX with a cheap encrypted outer SafeContents and an
// attacker-controlled expensive inner shrouded-key KDF. Only a full decoder
// with per-primitive budgets can see/reject that inner request before work.
c.originalPFX=pfx;c.testPassword=password;
const nested=vm.runInContext(`(function(){
 const a=forge.asn1, p=a.fromDer(forge.util.decode64(originalPFX)), safe=a.fromDer(p.value[1].value[1].value[0].value);
 const keys=a.fromDer(safe.value[1].value[1].value[0].value);
 const info=keys.value[0].value[1].value[0];
 info.value[0].value[1].value[0].value[1].value[1].value=a.integerToDer(2000000000).getBytes();
 const wrapped=forge.pki.encryptPrivateKeyInfo(keys,testPassword,{algorithm:'aes256',count:1,saltSize:16});
 const seq=v=>a.create(a.Class.UNIVERSAL,a.Type.SEQUENCE,true,v), oid=v=>a.create(a.Class.UNIVERSAL,a.Type.OID,false,a.oidToDer(v).getBytes());
 const encrypted=seq([a.create(a.Class.UNIVERSAL,a.Type.INTEGER,false,a.integerToDer(0).getBytes()),seq([oid(forge.pki.oids.data),wrapped.value[0],a.create(a.Class.CONTEXT_SPECIFIC,0,false,wrapped.value[1].value)])]);
 safe.value[1]=seq([oid(forge.pki.oids.encryptedData),a.create(a.Class.CONTEXT_SPECIFIC,0,true,[encrypted])]);
 const bytes=a.toDer(safe).getBytes();p.value[1].value[1].value[0].value=bytes;
 const salt=forge.util.createBuffer(p.value[2].value[1].value);p.value[2].value[2].value=a.integerToDer(1).getBytes();
 const key=forge.pkcs12.generateKey(testPassword,salt,3,1,20), mac=forge.hmac.create();mac.start(forge.md.sha1.create(),key);mac.update(bytes);p.value[2].value[0].value[1].value=mac.digest().getBytes();
 return forge.util.encode64(a.toDer(p).getBytes());
})()`,c);
const start=Date.now();let rejected=false;try{c.tetherlessValidateP12(nested,password)}catch(e){rejected=String(e).includes('workLimit')}if(!rejected||Date.now()-start>2000)throw Error('nestedWorkLimitMissing');

const second=c.tetherlessEncryptP12(cert,key,password);
if(second===pfx)throw Error('randomnessMissing');
for(const mode of ['fail','short']) {let rejected=false;try{context(mode).tetherlessEncryptP12(cert,key,password)}catch{rejected=true}if(!rejected)throw Error('entropyFailOpen');}
'''
            (root / 'test.cjs').write_text(script)
            run('node', 'test.cjs', str(ROOT / 'Native/SigningCrypto'))
            password = 'pass:synthetic-test-password-only'
            result = run('openssl', 'pkcs12', '-in', 'identity.p12', '-passin', password, '-info', '-noout')
            info = result.stderr.decode()
            self.assertIn('Shrouded Keybag', info)
            self.assertIn('AES-256-CBC', info)
            self.assertIn('Iteration 100000', info)
            self.assertIn('MAC:', info)
            self.assertNotIn((root/'key.der').read_bytes(), (root/'identity.p12').read_bytes())
            for wrong in ['pass:wrong', 'pass:']:
                self.assertNotEqual(run('openssl', 'pkcs12', '-in', 'identity.p12', '-passin', wrong, '-noout', ok=False).returncode, 0)
            run('openssl', 'pkcs12', '-in', 'identity.p12', '-passin', password, '-nocerts', '-nodes', '-out', 'extracted.pem')
            first=run('openssl','pkey','-in','key.pem','-pubout','-outform','DER').stdout
            other=run('openssl','pkey','-in','extracted.pem','-pubout','-outform','DER').stdout
            self.assertEqual(first,other)
            data=bytearray((root/'identity.p12').read_bytes()); data[len(data)//2] ^= 1; (root/'tampered.p12').write_bytes(data)
            self.assertNotEqual(run('openssl','pkcs12','-in','tampered.p12','-passin',password,'-noout',ok=False).returncode,0)
