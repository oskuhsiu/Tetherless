# One-run decision: isolate the native providers

## Current failure

- Consumer source: `3f717ea5441d2cacee13e1d078e5ba7f1484edc5`
- Workflow: Retained pairing iOS diagnostic
- Run/attempt/job: `37407474925` / `1` / `112088119151`
- Artifact SHA-256:
  `6fe740a1687b2f9d6fbfe01df4b7f82e02c0804d4a83a4d71b266289073648e9`
- First failure: Debug build, Clang provider-declaration collision,
  `xcodebuild.txt:8989`; 25 repeated reports. Preparation/authentication passed.
- Release: build passed, with both static providers in the final link command at
  line 7005. Symbol ownership is not established by that success alone.
- Read-only classifier: `build`; symptom `clang-provider-declaration-collision`;
  automatic retry disallowed, product acceptance false. No Simulator boot,
  installation or UI failure is inferred.

## Hypothesis and discriminating change

The two providers share global native identifiers despite different plist/handle
implementations and declarations. A source-level Rust export namespace, matching
public header and one scoped Swift gateway adaptation will separate those
providers without changing parser algorithms, service lifetimes or data formats.

The candidate's exact implementation and boundary checks are documented in
`Integration/Dependencies/idevice/NATIVE_NAMESPACE_REPAIR.md`. A new producer is
required; the 9ee2ccc producer cannot be reused as proof of renamed exports.

## Next expensive item, after review and commit

Run the existing reviewed component/native producer workflow once at the exact
reviewed namespace commit, with the same Rust 1.98.1, Xcode 26.3, arm64 runner,
device and Simulator targets, SDK observation checks, default/selected features,
bounded supervisor and unchanged command deadlines. Confirm there is no relevant
active run before dispatch. Record its actual source SHA, run/attempt/job IDs and
runner image fingerprint; this candidate does not invent those future identities.

Support requires both target builds, unchanged old probes, new C/Swift
mixed-provider links, exact namespace inventories, disjoint provider exports,
retained maps and all input audits. A compiler or linker failure, missing map,
remaining old export or changed input refutes this candidate's acceptance.

Stop after that run's retained result. If it fails, inspect its first new failed
boundary and repair or instrument that boundary before any other long run. Do
not add enum members, suppress diagnostics, change archive order, remove a
provider, raise deadlines or repeat blindly.

If the producer passes, authenticate its new artifacts/source and update the
explicit retained-producer selection in a separate verification checkpoint. The
next standalone item is the original unsigned app Debug/Release diagnostic with
its original mandatory sources, conditions, callback spy, support source,
capability gate, real archive identities and compile sentinel. Both configurations
must pass. The app map and C header/archive identity now provide additional
evidence; they replace no existing assertion.

## Scope and outstanding evidence

Portable source transformation, fixture and GCC header checks are useful evidence,
not an Apple build. Native C/Swift module imports, new archives and actual final
symbol maps remain pending until the exact candidate executes on the pinned
Apple toolchain. This Linux environment lacks swift/swiftc and cannot run those
checks. An authentic C release download in this investigation returned HTTP 403;
the response body was not retained, and no cause or access entitlement is inferred.

No Apple credentials, account calls, signing, deployment, release, physical device
use, parser/signing-admission work, manager replacement, startup ownership change
or install-budget change is part of this decision. No workflow was dispatched by
the candidate author.
