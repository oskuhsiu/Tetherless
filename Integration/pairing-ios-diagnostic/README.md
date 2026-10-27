# Retained native artifact consumer

This packet prepares and compiles an owned diagnostic app copy against an exact,
authenticated local IDevice XCFramework. It does not open product capabilities,
run an iOS app, install anything or establish device acceptance.

The native producer and app consumer have separate source identities. Every
indexed native recipe/provider/profile/probe file and the producer workflow must
match the authenticated producer commit. Fourteen app compiler inputs, the
approved opaque manager support source and preparation gate must independently
match the consumer commit and reviewed pins. A reviewed app-only change does not
require rebuilding identical native inputs.

The fourteen mandatory inputs preserve the original twelve and add
PairingValidationBudget.swift and the advanced WirelessPairView.swift. The latter
must appear at SideStore/Views/Settings/Advanced/PairingFile/WirelessPair/WirelessPairView.swift
in actual compiler file membership. The manager is an identity-only support pin;
this adapter does not change or inspect its behavior. Gate 9ddf2811 is the accepted
registration-only UI successor. Normal Swift Debug/Release and Integration tests
remain in the caller workflow, including separately approved regressions.

Before binding, the trusted caller must authenticate one successful native run
and its five selected artifacts: host (26), combined (100), transcript (3), host transcript (10) and
Apple. Each artifact binds its exact producer attempt, so a legitimate earlier
successful lane can survive a failed-job retry in the same producer run. ZIP
hashes come from the authenticated API; an adjacent checksum is insufficient.
Native artifact validation requires two arm64 slices, six successful ABI probe
receipts, exact generated header evidence, the separate framework provider and
matching opaque bytes. See HANDOFF.md for transport and caller details.

The runtime producer template contains null values and cannot trigger a valid
binding or compile. No real runtime-producer.json is supplied. After reviewing
actual native success, the publishing owner supplies explicit run/commit/attempt
values through that one branch-only push path. No guessed artifact IDs or static
native-prerequisite override is accepted.

For both Debug and Release, the compiler adapter rechecks authenticated inputs,
uses the reviewed bounded process supervisor, compares complete compiler/SDK
observations to the producer, and runs ordinary unsigned xcodebuild. The observer
requires real app and gateway SwiftDriver invocations, all fourteen source
memberships, the three diagnostic conditions, the sentinel postimage, the bound
IDevice module/header and matching final archive/OpenSSL framework link paths.
It hashes opaque binaries without parsing their format. Logs are evidence only
and never executed as commands. Bounded response, file-list and module-map bytes
are copied to compiler-inputs before parsing, with an append-only inventory that
survives failure. Changed repeated reads are rejected. The final app output must
be regular and nonempty, and its opaque hash and size are recorded. The diagnostic disables the optional Debug dylib
so app link evidence is a single executable target; no normal project setting is
edited.

The compile cap is 1800 seconds and 32 MiB per configuration. Evidence includes
supervisor status, ordinary compiler text, source/response-file hashes, selected
opaque link identities and independent audits of bound files, recipe and native
handoff on success or failure. Native output is never executed. A missing input,
failed command, incomplete cleanup, absent compiler/link evidence or changed
input prevents a success receipt. Reserved binding destinations and evidence
JSON files are created exclusively and reject symlink substitutions. Independent
audits still run when retention or compiler observation fails.

This is a new implementation checkpoint after workspace replacement. Fourteen
former files were recovered exactly; the missing observer/sentinel/runner and
fixtures were written afresh. Portable test counts belong to this packet only.
Actual UIKit compilation, genuine Swift import and final app linking remain
pending until authenticated native producer evidence is supplied.

Historical command-shape checks use authenticated native-build.log from run
37303840335/source1fc8968f. They established the optional architecture word in
Ld headings and the actual system-include flag forms. The historical log contains
no retained response bodies and does not validate the current app composition.

## Bound unsigned App retention

After each successful configuration, `package_bound_app.py --configuration Debug`
(or `Release`) packages that configuration's complete
`.pairing-consumer/compile-{debug,release}/DerivedData/Build/Products/{Debug,Release}-iphoneos/SideStore.app`.
It calls the unchanged `Integration/package_unsigned.py` using the bound
`.pairing-consumer/diagnostic` prepared tree and that configuration's
`DerivedData/SourcePackages`. Only the outer bundle directory is renamed to
`Payload/Tetherless.app`; the executable name, extensions, frameworks, resources,
symlinks and nested IPAs retain their bytes and paths.

The wrapper requires independently supplied caller environment identities
(`GITHUB_REPOSITORY`, repository ID, SHA, run ID and attempt, plus the explicit
`PRODUCER_*` selection) and the existing handoff, Apple receipt and binding hash
outputs. It accepts only matching diagnostic compile/binding/native-handoff
receipts, all three successful input audits, the exact link-map hash and the
observed final executable path, size and hash. It revalidates the native handoff
and bound inputs, compares every compiled App file/symlink and regular-file executable bits against
the IPA, then
rechecks inputs before publishing. There is no executable-only fallback.

Each complete package is admitted exclusively and atomically at
`.pairing-consumer/packages/{Debug,Release}`. An existing output or any failed
check leaves no new final package. Publication uses macOS `renamex_np` with
`RENAME_EXCL` (Linux `renameat2` with `RENAME_NOREPLACE` in portable tests), and
fails closed if exclusive atomic publication is unavailable. Hidden staging
directories are never selected for artifact upload.

The source/attempt-bound `pairing-ios-unsigned-{debug,release}-SHA-RUN-ATTEMPT`
artifacts retain the IPA, existing available-source/notices bundles, inventories,
open release gates and checksums. `package-binding.json` joins the consumer and
producer contexts, native artifact/source hashes, binding/handoff/compile/audit/
link-map/input-contract identities, complete App inventory and final IPA hash.
It also records a canonical bundle list using only direct bundle-root
`Info.plist` files; storyboard metadata remains in the generic byte inventory.
Retained entitlement templates are source/build-input declarations with hashes,
never claims about effective signing rights. This list covers only declarations
already retained in `inputs.json:files`; generated DerivedData `.xcent` files are
not searched or collected, and the receipt explicitly records that gap. `unsigned=true`,
`deviceValidated=false` and `releaseReady=false` remain explicit.

Packaging runs only when its own compile step succeeds and the job is not
cancelled. Release compilation still runs after Debug failure when binding
succeeded. Evidence retention still runs after failures, and a successful single
configuration may be retained for diagnosis, but acceptance requires both Debug
and Release. The trigger remains a branch-only change to `runtime-producer.json`;
changing packaging code alone cannot launch an old-source App run. Retention is
14 days, not durable release hosting. No IPA is signed, installed or executed.

Portable tests use synthetic App and native receipts plus a controlled ZIP writer
in place of macOS `ditto`. They establish identity, completeness, rejection and
publication behavior only. Actual Xcode/ditto validation remains a separate
macOS acceptance step for the exact source and authenticated producer.
