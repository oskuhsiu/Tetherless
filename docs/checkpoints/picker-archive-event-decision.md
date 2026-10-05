# Decision: classify one identified historical picker event

Prepared 2026-10-05. One narrower read-only observation was approved after archive analysis run 37375339797 exposed a specific new lead. This candidate does not rerun the broad query, change that report, or perform product/UI work. Publication and execution belong to the coordinating task.

## Exact lead and scope

The prior report contains one DocumentManager event at 2026-10-05T10:55:56.651894+00:00 with navigation, timeout and error lexical tags. Its text was not retained; none of the already-authorized local text matched its message hash. Earlier enumeration tags precede the local-root activation and do not establish successful root enumeration. The new question is the technical operation/error stated by this one event, not whether the earlier failing UI test should pass.

Required identity, all matched before inspecting template/error fields:

- PID 22858 and the previously reviewed owned-picker subsystem allowlist
- Exact timestamp 2026-10-05T10:55:56.651894+00:00
- Message SHA-256 f7547ed30e40537407357290e3b3f7caf45d9665a9c8fa5bb427986f5a11cfd2
- Activity SHA-256 2b2a184998c7a08b7ff6ed56f6cee51dbcc2a78b49a3758886bc481ebad12246

The query covers only 10:55:56 through 10:55:57 UTC, a one-second subset of the original authorized 10:54:58–10:55:57 window. It selects the observed DocumentManager PID only. No fileproviderd or LocalStorage process, other archive, broader interval or UI is queried. Nonmatching records are counted and discarded without publishing their text, hashes or metadata.

## Reuse the verified archive path

The new entry point loads an immutable private copy of existing Integration/Diagnostics/picker_archive.py only after matching SHA-256 b3272ed5743bc887a2254ef3eae7e27e95c4ce4dae0505a067acf61cf5b94b4d. It does not call the old analyze function or modify any old helper/report. Existing exact ZIP, owner/source identity, xcresult-tree, archive object, archive Info.plist, exported-tree and supervisor gates are reused unchanged.

The sole input remains artifact 11341735733 from run 37298228388, original ZIP SHA-256 ac79e699970ebf98f07277855ffd824529fb826b6aba01583da4538433b742e2. Only its pinned owned Simulator archive object is exported. The existing byte-pinned bounded_process.py and apply_patch.py dependencies remain unchanged.

The separate workflow runs only on verify/staged-pairing-native, guarded by exact repository/ref and narrow paths for its own new files. The old broad diagnostic workflow is unchanged and is not triggered by this slice. Permissions are contents:read and actions:read. The already-reviewed official download-artifact v8.0.0 action is SHA-pinned and preserves the raw ZIP using skip-decompress; the independent reviewed ZIP digest is enforced before extraction. Python does not read credentials. No software installation, Simulator command, product launch, selector, original deadline, account access or privacy-logging configuration change is involved.

Installed Apple help is checked before using export/query syntax. The single native query is bounded to 90 seconds and 1 MiB, and uses the same supervised process-group cleanup. Only a complete untruncated query reaches identification; export and tree identity must succeed first. These are offline tool limits, not altered UI acceptance deadlines.

## Useful technical detail without private content

A formatString is not assumed safe merely because it comes from a log record. Only the exact hash-bound event can supply it. A strict bounded printf tokenizer elides runtime substitutions, including positional widths, privacy/type qualifiers and recognized conversions. Unsupported conversions or unbalanced delimiters refuse the template. Quoted/backtick/object/dictionary spans, literal paths (including relative and Windows forms), URLs, addresses, UUIDs, credential assignments and other payloads are elided.

Remaining text passes a closed technical/common-word vocabulary, with ordinary words canonicalized to lowercase. Only exact reviewed framework/class symbols are preserved. Unknown words and technical-looking prefixes are withheld rather than assumed nonsecret. The output includes the resulting technical template and explicit elision counts/hash, so an operation’s surrounding static wording remains reviewable without printing the dynamic eventMessage. Recognized operations describe what this exact log says, not a causal finding or proof that an operation completed.

Error details use exact reviewed domain names and bounded integer codes with explicit terminators. A trusted-looking NS/FP/DOC/com.apple prefix alone is insufficient. Unknown domains are counted without publication; excessive codes stop classification. Missing/unsafe templates have no raw-message fallback. A known technical error code can still be reported independently of a missing template.

Exactly one valid match is required for a classified result. Multiple/missing matches stop inconclusive. Unsupported query lines also make the overall result inconclusive and leave uniqueness unproven. If one fully byte-matched event was observed among unsupported lines, its already-sanitized technical details may be retained under provisionalExactMatchDetails; those details are positive evidence about the matched bytes, not proof that the surrounding query is complete. Unrelated or unsupported line contents are never emitted.

Only report.json is uploaded. Raw download, xcresult/archive bytes, Apple stdout and supervisor sidecars remain unuploaded temporary data. Analysis scratch is deleted only after child/group cleanup is confirmed; the action’s original download remains in ephemeral runner storage. No raw archive or user content is added to source control.

## Stopping and interpretation

One safely identified event with a meaningful operation/template or recognized technical error yields classified evidence. This identifies the technical content of a historical log message only. It does not establish a root cause, provider readiness or product acceptance.

If the event is missing, ambiguous, cannot be safely interpreted, or cannot be read with complete bounded output, stop this path and report inconclusive. Preserve any explicitly provisional positive detail as such. Do not automatically repeat, widen the query, run UI, change product code, or loosen privacy/hash gates. The original full-product acceptance remains failed and unchanged.

Portable checks cover adversarial privacy/template input, exact event identity, duplicate/malformed query handling, immutable helper pinning, actual execution of the trusted supervisor against a synthetic child, one-query orchestration, source/export hash refusal and cleanup failures. These tests are not native Apple decoding or evidence of the historical event’s meaning.
