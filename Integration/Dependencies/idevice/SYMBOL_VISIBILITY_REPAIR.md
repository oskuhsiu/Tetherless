# Native symbol ownership from bound compiler text

## First cause and evidence

Source `0ba3b504dd48cc398c6f4a63020f1b7d54098386`, Apple producer run
`37547552049`, attempt `1`, job `112555067574` failed at the unchanged
`ambiguous required live map symbol` assertion. The Rust release archive,
C/Swift host links and C mixed link had completed. This is a map ownership
classification failure after linking, not a Simulator boot, signing or device
failure. The Apple producer did not complete its two-target acceptance contract.

The original artifact `11452220009` is 23,756,495 bytes, SHA-256
`b407ec368fdc1a7b5294fe92cd7e14e257fca81c25f7b569e3d2c2e512157a1d`.
Its exact retained archives are:

- Rust: 17,999,272 bytes, SHA-256
  `9b458c0842244b6d5ea4377df999d1ada6f87a0f10ebc6ae51b5fdf23c4adc24`
- C: 820,672 bytes, SHA-256
  `8695e4538970f7cec522958cbc03d362472f5f2678448c82558077d932520911`

The C mixed map SHA-256 is
`e6119d6bed477439b75e8d985f3019a2e6d5e370ebfc06bb7a56f575d6e9b321`.
Both member-qualified scans and all seven reached operations have retained
command/status/log joins and equal original/copy archive hashes before and
after each operation. All 29 same-name map cases have one non-external Rust
`f8e4fd781484bd36-bcm.o` definition and one private external C definition in
the matching named member. The 47,173 Rust and 3,392 C scan rows contain
4,819 and 829 unique external symbols respectively, with disjoint external sets.

The original just-symbols Rust stream contains three interleaved empty-member
warnings. It is not clean equivalence evidence. The new strict acceptance
parser rejects it; the original failed producer remains ineligible.

## Narrow contract change

Use the already pinned Rust host `llvm-nm` visibility scans as acceptance
inputs after validating their complete bytes, member-qualified grammar,
source/recipe context, exact tool identity, operation command, status and
pre/post original/copy archive identities. Require each archive's complete
external set to equal its independent just-symbols scan. Add `--quiet` to
that pinned external scan to suppress empty-member warnings, while retaining
normal member headings and rejecting malformed names or diagnostic lines.
No tool, component, native source, target, provider or namespace is changed.

For every required live map name, require exactly one intended external
owner. Every additional mapped candidate must have exactly one non-external
record for its exact archive and member name. Unknown or wrong archives,
missing records, repeated map rows, ambiguous member/name records and
competing external definitions still fail. Weak definitions count as external,
never local. A winner that resolves additional local candidates must be strong;
a sole weak external preserves existing full-export App behavior.

Repeated member basenames exist in the real C archive. The parser preserves
all member/name records, including repeated local names, instead of reducing
them to a set. A repeated record needed to justify a candidate is ambiguous
and fails. The independent C SHA512 families must still occupy distinct real
map object IDs.

The same validator is used by the producer and offline product consumer.
The package includes complete raw scans and operation receipts/status/logs;
archive bytes remain in the XCFramework and nested authenticated C handoff.
The consumer checks those packaged archive hashes and sizes before deriving
the visibility projection used by the App observer. App path rebasing requires
byte-identical processed DerivedData archives and preserves the existing live
root and dead-stripping checks. Complete raw-map bytes and LF parsing remain
unchanged, including opaque literal-string payloads.

## Verification and retry decision

Hypothesis: the old map gate conflates internal same-name implementations with
external ownership. The discriminating change is member visibility bound to
exact archive bytes; no name-specific exception or ignored duplicate is added.
The full real-text regression must resolve all 829 required C exports and 382
required Rust exports while retaining all 29 local candidates as explicit proof.
Negative fixtures cover wrong archives/members, duplicate/weak external owners,
missing and malformed records, repeated-basename ambiguity, stale source or
recipe context, altered scan/map/status/operation bytes and archive rebasing.

`automaticRetryAllowed=false`. Do not rerun the unchanged failed source.
After final independent review and publication of this exact source/recipe,
one planned native producer verification can discriminate the repair. Require
both Apple targets and every original export, force-load link, provider,
source, toolchain, process-supervision and input-audit condition. Record that
implementation SHA and its run/job/artifact IDs. If the same stage/symptom
recurs, preserve the new evidence and stop the full-run loop before another
attempt. A new failure boundary requires a new evidence-backed decision.

Offline text tests and opaque byte hashing do not establish a successful native
producer or App build. No failed artifact is admitted, no retained runtime
producer is updated here, and no native payload, Swift/Xcode, Apple account,
physical device, release or deployment action is performed locally.
