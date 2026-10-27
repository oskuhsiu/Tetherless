# Exact authenticated README filename alias

Run 37342573081 at 347bf0c21ad0465d86a86531f62c0c4b864c4094 isolated
one difference: expected 22,799 file keys, enumerated 22,798; missing 1, extra 0,
changed 0. The missing logical key was
`nskeyedarchiver_converter-0.1.3/README.md`, SHA256
`8f9d7995df53d0b3c75999fb5b253930513d761808f54f1b118c5c02cfee6f31`.
Every original logical-path hash had passed before that spelling comparison.

The independently reviewed immutable source is
[michaelwright235/nskeyedarchiver_converter commit 1b55c2a708d02bad89f52de831f4c785671b5d4a](https://github.com/michaelwright235/nskeyedarchiver_converter/tree/1b55c2a708d02bad89f52de831f4c785671b5d4a),
which declares version 0.1.3 and contains `README.MD`. Its 2,398 bytes have the
same SHA256 as the missing logical key. Git blob:
`5281aeeb5ad654fec5399de4ec8463d3fbedf39d`. The retained source/provenance is at
`upstream/registry-build/nskeyedarchiver_converter-0.1.3/`; provenance SHA256
`54e8bc4f7034aa6b732e77d20c165d6b212151676e5f1c1056047d067383f31d`.
The locked registry archive identity remains
`36c53158d1bf37bbbdd165f5220fda8bb5757c89eb700107992152c64c6cad7e`.

## Narrow reconciliation

The code accepts only the observed missing `README.md` when all these conditions
hold at the actual native preparation site:

- There are no extra or changed entries and no other missing entry
- Both README spellings are original authenticated checksum keys with the exact
  reviewed hash, and `README.MD` is an observed key with that hash
- The package archive checksum matches the unchanged lock pin
- Each exact logical path resolves safely and independently hashes to the pin
- Both paths identify regular files with one hardlink each
- `samefile` succeeds and their device/inode identities are equal

No filename normalization, case folding or generic equivalent-path exception is
used. A same-content but different file does not qualify. Neither a symlink nor a
hardlink qualifies. The pristine enumeration rejects unexpected hardlinks; both
pristine and derived final audits also reject hardlinks, original-file mutations,
missing files and unsafe paths. Genuine extra files remain rejected.

All original checksum keys remain present in the pristine and derived receipts.
The normal copy and post-copy checks still read every logical path and verify its
expected hash. No registry data, Cargo.lock, package manifest, source overlay,
cbindgen Rust postimage, helper profile or fixture filter changes.

## Evidence remains explicit

The existing `helper-work/vendor-derivation-inventory.json` remains the retained
artifact. Its raw `exact_match` and missing/extra/changed counts are unchanged:
accepting the alias does not turn raw missing 1 into raw equality.

Separate `admitted` and `readme_reconciliation` fields state whether the exact
exception was proved. Successful alias evidence includes package/archive identity,
both path spellings, the fixed content hash, device, inode, link count, samefile
result and `checksum_keys_preserved`. Failure records a fixed reason. The derived
layout receipt carries the same evidence and binds the diagnostic hash.

The original/derived/workspace audits still run on real Cargo success or failure.
The known generated-header evidence and bounded subprocess ownership are unchanged.
The earlier diagnostic-only document describes the previous checkpoint; this
explicitly reviewed alias is its sole new admission condition.

## Controlled checks and pending native proof

Ten new tests are authored: nine pass on this local Linux filesystem; the positive
real-volume alias/copy test explicitly skips because this volume is case-sensitive.
That test creates only `README.MD`, requires opposite-case lookup to identify the
same regular file, exercises the reconciliation and verifies both logical names
after copying. It will execute on the native macOS volume that showed the alias.
No mocked positive identity is reported as native evidence.

Negative fixtures use real separate files, symlinks and hardlinks to exercise
identity rejection, plus wrong hashes/archive identity, unexpected differences,
content mutation and post-copy audits. Eight diagnostic, twelve derivation and
eighteen existing vendor/audit tests also pass locally. The diagnostic mismatch
fixture now injects a real extra file after authentication and verifies rejection.

The macOS alias proof and all 43 Rust fixtures remain pending. This worker has not
published or run CI. The next parent-controlled run must establish the actual
filesystem identity and retain successful original/derived/workspace audits.

## Upstream notices

The retained nskeyedarchiver_converter source declares `MIT OR Apache-2.0`. Both
unchanged upstream notice files, LICENSE-MIT and LICENSE-APACHE, are included
beside the source. NOTICE_PROVENANCE.json records their independently checked
Git blob identities, byte lengths and SHA256 hashes. The original source receipt
and all reviewed code/test files remain unchanged.
