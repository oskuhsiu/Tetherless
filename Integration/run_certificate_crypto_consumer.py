#!/usr/bin/env python3
"""Synthetic macOS runtime gate; never contacts Apple or stores test identities."""
import json
import platform
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/certificate-crypto'

def main():
    if platform.system() != 'Darwin':
        raise SystemExit('Requires macOS Security/JavaScriptCore; no substitute pass on Linux')
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tetherless-synthetic-consumer-') as directory:
        work = Path(directory)
        package = work / 'package'
        shutil.copytree(ROOT / 'Integration/CertificateCryptoConsumer', package)
        sources = package / 'Sources/Consumer'
        for source in ['Integration/Native/NativeEncryptedP12.swift', 'Sources/TetherlessCore/CertificateExportPolicy.swift', 'Sources/TetherlessCore/SigningKeyProof.swift']:
            shutil.copyfile(ROOT / source, sources / Path(source).name)
        def run(args, timeout=120):
            return subprocess.run(args, cwd=work, check=True, capture_output=True, text=True, timeout=timeout)
        # Build logs precede all fixture generation: no key material enters logs.
        with (OUT / 'build.log').open('w') as log:
            subprocess.run(['swift', 'build', '--package-path', str(package), '--force-resolved-versions', '--product', 'CertificateCryptoConsumer'], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        pins = json.loads((package / 'Package.resolved').read_text())['pins']
        expected = json.loads((ROOT / 'Integration/CertificateCryptoConsumer/Package.resolved').read_text())['pins']
        assert {p['identity']:p['state']['revision'] for p in pins} == {p['identity']:p['state']['revision'] for p in expected}, 'Resolved dependency drift'
        binpath = Path(run(['swift', 'build', '--package-path', str(package), '--show-bin-path']).stdout.strip())
        bundle = work / 'Consumer.app/Contents'
        resources = bundle / 'Resources'; resources.mkdir(parents=True)
        executable = bundle / 'MacOS/CertificateCryptoConsumer'; executable.parent.mkdir()
        shutil.copyfile(binpath / 'CertificateCryptoConsumer', executable); executable.chmod(0o700)
        (bundle / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.tetherless.synthetic.consumer','CFBundleExecutable':'CertificateCryptoConsumer','CFBundlePackageType':'APPL'}))
        for file in (ROOT / 'Integration/Native/SigningCrypto').glob('*.js'):
            shutil.copyfile(file, resources / file.name)
        run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout','key.pem','-out','cert.pem','-days','1','-subj','/CN=Tetherless Synthetic Consumer/OU=SYNTHETIC'])
        run(['openssl','x509','-in','cert.pem','-outform','DER','-out','cert.der'])
        run(['openssl','rsa','-in','key.pem','-outform','DER','-out','key.der'])
        generator = work / 'fixtures.mjs'
        generator.write_text('''import fs from 'node:fs';
import {File} from 'node:buffer';
import {pathToFileURL} from 'node:url';
globalThis.File ??= File;
const root=process.argv[2];
const forge=(await import(pathToFileURL(root+'/WebBootstrap/node_modules/node-forge/lib/index.js'))).default;
const {exportP12}=await import(pathToFileURL(root+'/WebBootstrap/src/certificate-recovery.js'));
const password='synthetic-consumer-test-only';
const privateKey=forge.pki.privateKeyFromPem(fs.readFileSync('key.pem','utf8'));
const cert=forge.pki.certificateFromPem(fs.readFileSync('cert.pem','utf8'));
const original=Buffer.from(await exportP12({keys:{privateKey},cert},password).arrayBuffer());
fs.writeFileSync('web-original.p12',original);
const asn=forge.asn1.fromDer(original.toString('binary'));
const digest=asn.value[2].value[0].value[1];
digest.value=String.fromCharCode(digest.value.charCodeAt(0)^1)+digest.value.slice(1);
fs.writeFileSync('mac-tampered.p12',Buffer.from(forge.asn1.toDer(asn).getBytes(),'binary'));
''')
        run(['node',str(generator),str(ROOT)])
        result = run([str(executable),str(work)], timeout=180)
        report = json.loads(result.stdout)
        assert len(report['checks']) == 9 and len(set(report['checks'])) == 9, 'Incomplete consumer checks'
        report['dependencies'] = {p['identity']:p['state']['revision'] for p in pins}
        report['platform'] = platform.mac_ver()[0]
        (OUT / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report))

if __name__ == '__main__':
    main()
