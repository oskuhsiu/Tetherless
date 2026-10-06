# Cold pairing selection and semantic identity fixture

This is a bounded, nonphysical source fixture. It adds no production behavior,
startup call, reload, restart requirement, cache operation or install check.
Ordinary renewal remains mobile-only after the first authorized setup.

## Actual sources and explicit seams

The launcher compiles unchanged `PairingFileManager`, `PrivateFileStore`,
`PairingRecord`, `PairingReset`, `NativePairingMutation` and `MutationScope`
from Tetherless `4838168e2692e087b0465fca349f4cba8704011d`. Its separate
`MinimuxerCommon` module compiles four exact upstream files from minimuxer
`12be70dc2627307a16bfd2dc7a009080d5bec909`: `PairingFile.swift`,
`ConcurrencyUtils.swift`, `PairingProtocol.swift` (including `PairingError`),
and `MinimuxerConstants.swift`. The ordinary parser is not stubbed or rewritten.

`Integration/fixtures/ColdPairingParser/source-lock.json` records every source
SHA-256 and upstream Git blob identity/URL. The launcher pins the manifest itself,
verifies all inputs before staging and checks the original and staged inputs
around every supervised command. Upstream notices are retained; the existing
`docs/supply-chain/licenses/SideStore__minimuxer__LICENSE` supplies its license.

The following are explicitly synthetic:

- App directory accessors point at an owned temporary root
- Preference accessors persist raw strings in a fixture-owned plist, keeping the
  app's optional `PairingProtocol(rawValue:)` conversion. This does not exercise
  CFPreferences, app defaults registration, sandbox migration or crash atomicity
- Process-lock acquisition is a no-op seam. Actual mutation-scope and synchronous
  wrapper sources compile unchanged, but this fixture makes no OS-lock claim
- `PairingGatewayInputSpy` is a new receiver in the reader process. It receives the
  selected content/preference and calls the actual ordinary parser. The real
  `IdeviceGateway`, its native RP handle, network service, live read and startup
  wrappers are not compiled or called
- Key bytes and identifiers are synthetic. The fixture checks values, not valid
  cryptographic key relationships, peer acceptance or hardware identity

For every scenario the writer calls the actual save entry points, saves remote
preference, and exits. The bounded supervisor verifies writer/group termination
before launching the separate reader executable. There is no retained manager or
gateway object between these processes. Each pair has its own temporary root.
This models the cold-reader contract without running app startup or asking for a
manual restart.

## Assertions

Both Debug and optimized builds run the same nine scenarios:

1. A fresh reader selects the saved remote record despite retained lockdown data;
   the actual parser preserves its supplied UTF-8 data, host keys and identifier
2. Binary stored plist normalizes to XML while preserving semantic remote fields
3. Alternate XML comment/whitespace representation preserves semantic fields
4. Explicit selection wins over preferred, preferred wins over persisted-active,
   active is used when preferred is absent; two unselected records conflict and a
   sole record can be selected
5. A missing selected remote record returns nil without using retained lockdown
6. A corrupt or wrong-kind selected record throws; the compatibility getter returns
   nil and does not use retained lockdown
7. Explicit or saved enum `.unknown` throws. An unrecognized raw preference string
   converts to nil and uses persisted-active selection, matching existing accessors
8. The reset default and durable reset marker each suppress selection
9. The actual parser rejects explicit wrong/unknown protocol and unselected mixed
   protocol dictionaries; app validation also rejects mixed families

Every writer additionally checks the exact saved bytes. The existing generated
promotion/exact-validated-save fixture is unchanged and remains the separate
byte-preservation and cancellation/lease test. Ordinary read assertions compare
semantic values; they do not introduce an exact XML-formatting requirement.

## Running and evidence

Run on a macOS Apple toolchain from a complete checkout containing these files:

```sh
python3 Integration/verify_pairing_cold_read.py \
  --source-root . --output-root /absolute/new/evidence-directory
```

The output directory must be new, its parent must exist and neither may be a
symlink. The launcher reuses the existing pinned bounded process-group supervisor.
It retains command logs/status, hashes and `report.json`; no pairing values are
printed. Scratch cleanup requires a reaped direct child and empty process group.
There is no network download or dependency resolution during this fixture.

The same fixture also runs through `test_pairing_cold_read.py` during Darwin Python
test discovery. Portable tests validate frozen sources and launcher failure
classification using explicit Python runner doubles; these are not Swift results.
Linux reports `unsupported_platform` or an explicit unittest skip and exits the
standalone launcher nonzero. A zero compiler exit or skipped/missing fixture line
cannot produce a passed report. An injected runner is labelled separately.

At authoring, seven portable checks passed and the single Darwin execution test
was unrun. Swift/Xcode are unavailable on the authoring Linux host. Actual Apple
Debug/optimized execution remains required; this packet supplies no native pass.

Even a complete fixture pass proves only this bounded source/store/parser
contract. Native handle parsing, prepared-app linkage, live device access,
cryptographic interoperability, renewal and unattended scheduling remain distinct
evidence. A force-live service read is operational evidence, not a stored-byte
fingerprint or hardware attestation.
