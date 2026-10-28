# Certificate lifecycle dependency security review

Checked 2026-10-28. This is a scoped call-path review, not a claim of zero dependency vulnerabilities.

## node-forge: official patched 1.4.2 and independent platform verification

The initial primary advisory https://github.com/advisories/GHSA-86w9-cpqp-85rv (CVE-2026-85393, published 2026-09-03, last updated 2026-10-01) still listed no patched version. A fresh isolated audit instead reported a 1.4.2 fix. This contradiction was investigated rather than trusting either old metadata or audit's recommendation alone.

The maintainer's newer advisory https://github.com/digitalbazaar/forge/security/advisories/GHSA-2g46-22mc-6gwp (published 2026-10-27) identifies versions through 1.4.0 as affected and 1.4.1 as patched. The official https://github.com/digitalbazaar/forge/releases/tag/v1.4.2 and https://raw.githubusercontent.com/digitalbazaar/forge/v1.4.2/CHANGELOG.md confirm the fix and the later PEM Buffer compatibility repair. Official npm 1.4.2 was published 2026-10-27T14:09:15.471Z, with gitHead `7928054627d93ab8c0216b756246e8ca8d62a93e`. The downloaded tarball matched registry SHA512 integrity; its RSA source matched the tagged source byte-for-byte. We do not claim the tag is cryptographically signed. Both web dependency and native vendored resource are upgraded together; their hashes and licenses must remain verified.

The vulnerable PKCS#1 v1.5 RSA verifier accepted malformed nested DigestAlgorithm fields, with low-exponent attack conditions. The official repair validates canonical DigestInfo encoding. The changelog also contains P12 MAC iteration and ASN.1/PEM parsing repairs, so merely removing RSA call sites was not treated as a substitute for the package update.

Review identified two new recovery CSR verification calls reaching the old verifier. Product verification now independently uses platform WebCrypto SHA-256 over original CertificationRequestInfo DER and SPKI. Missing WebCrypto fails closed, with no Forge fallback. A synthetic malformed signature was independently reproduced as accepted by 1.4.0 and rejected by WebCrypto before the upgrade; the upgraded regression requires rejection and does not retain a vulnerable package just to demonstrate history. Complete private-key consistency and exact CSR/key/Team binding remain separate admission checks.

The review also scanned existing web paths and the native adapter, not only the modified calls. No product Forge CSR/RSA signature-verification call remains. Existing certificate/profile operations parse data; they do not gain trusted-chain status from a Forge verification call. Native uses Forge ASN.1/P12 encryption, decryption and MAC handling, with Security proving private-key possession and a separately tested pinned signer consumer. All these consumers require regression after the resource update. This review does not certify all parsers or dependencies free of other vulnerabilities; report the final audit output and exact final CI rather than claiming safety from a version bump alone.

## Vite: bounded development-tool update

Official release: https://github.com/vitejs/vite/releases/tag/v8.1.6 (published 2026-10-06). The following advisories identify 8.1.6 as a patched version for the affected 8.0.0–8.1.5 line. Upgrade only the Vite pin and its required lockfile graph; do not infer that an audit client's `fixAvailable: false` means no official patch exists.

- https://github.com/advisories/GHSA-698v-4r3x-3vcv — Windows launch-editor escaping / NTFS and environment conditions.
- https://github.com/advisories/GHSA-587h-7wmj-h5pm — Windows editor existence-check bypass; can chain with the prior issue.
- https://github.com/advisories/GHSA-r825-w8mm-5pxw — WSL/editor and controlled working-directory entry conditions.
- https://github.com/advisories/GHSA-9jrq-w75r-8gcw — custom middleware forwarding untrusted raw URL into transformIndexHtml; no such middleware identified here.
- https://github.com/advisories/GHSA-rq7h-c2jc-7f22 — non-Windows development server explicitly exposed to the network, with an imported-path/host-file collision outside deny rules. Those deployment and file conditions have not been established for this repository.

The first three advisories were updated 2026-10-20 and the latter two 2026-10-21. Production's final Docker image serves built dist files using the Rust/custom Node service; it does not run a Vite dev server or include its node_modules. Browser CI uses the repository's custom preview server, not Vite preview. This limits the identified production exposure but does not excuse affected developer tooling. Validate the bounded update with the entire web unit/build/harness suite and actual Chromium/WebKit CI before treating it as accepted.

## Evidence boundaries

All vulnerability and certificate fixtures are synthetic. No test authenticates an Apple account, issues or revokes live certificates, or deploys a service. Native compile, artifact resource hashes, Security/CodeSignKit readback, real WASM signing and browser regressions are distinct evidence; none substitutes for a real-device installation test. Report the exact final commit and workflow results separately from earlier passing commits.
