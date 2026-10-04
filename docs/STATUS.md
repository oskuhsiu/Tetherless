# Checkpoint — authoritative IPA snapshot and targeted Simulator build

Updated 2026-10-04. This increment closes a concrete INSTALL-01/QA-02 input consistency gap and corrects an AUTO-02/PAIR-01 test-environment regression. Starting develop is decaef176aa0dbcb858f39b85fff8a8ad0eb1c87. Main remains unpromoted; no phone or credentials requested.

## Product change

DownloadAppOperation now creates one bounded protected App.ipa snapshot before extraction and keeps that same file in the install context. The old path extracted the original URL, then copied that URL again, allowing a mutable document to change between validation and cached-input creation. External reads use a security-scoped NSFileCoordinator accessor only for the copy; internal HTTPS downloads use the same snapshot primitive. Size/type/change/cancellation checks and descriptor-bound cleanup preserve the source and refuse a changed/replaced output. All source input is hash-checked before transforming the native method. See IPA_INPUT.md.

## Actual harness failure and narrow correction

The isolated-device change at decaef1 created its owned shutdown SE Simulator successfully, but its generic Simulator build also attempted x86_64. The downloaded native build log reports undefined x86_64 idevice symbols such as _adapter_free/_afc_client_connect. This is a regression introduced by the generic destination, not another observed simctl installation timeout or picker failure. The failure artifact 11294585641 matched SHA-256 bb929b2a687e8e78e8d0d1ed511330392f1edb3e1ecd49756c3e24cdab52c1c2. The present workflow restores the selected device destination for build and tests while preserving isolated ownership, explicit boot after compilation, bounded service diagnostics and every existing UI assertion. No automatic retry or broader unsupported-architecture claim.

## Completed local evidence

- Core Debug and Release: 296 tests in 38 suites passed each, including ten new real-file snapshot tests. An earlier Release driver timed out during compilation and is not counted; the completed later invocation returned zero.
- Python: 171 tests passed with no skips, including four new exact-input snapshot integration checks and seven new simulator lifecycle checks. Earlier 12/3 prepared-input skips were resolved by restoring the actual reviewed inputs. The metadata preimage reconstructed from the exact reviewed manager and existing cache transformation matches required blob df58f374bd41fc901ee5ed265429f765d33fee09.
- Actual Linux Foundation IO and subprocesses ran; file-provider coordination and iOS protection still need native/device verification. No live Apple, downloads or fake success backend was supplied.
- Fresh native builds and complete App/UI execution are still required for this product. Earlier green builds do not validate the new adapter. The original simctl timeout and corrected picker UI remain unaccepted until those real steps execute.

PLAN_PROGRESS.md remains the original sixteen-task inventory. Next read fresh native/UI results, preserve any real failure, and close the remaining install resource/lifecycle and BASE-02 provenance/distribution conditions. This increment does not complete all INSTALL-01 or QA-02 acceptance. Source and its exact pending verification boundary are saved together.
