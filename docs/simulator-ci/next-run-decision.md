# Decision: isolate the shared document-provider boundary

Status: planned diagnostic; implementation and independent review must complete before the next push starts it. No new native result is claimed.

## Current evidence

- Source: 89c157dbc6acd3c16eb31a32bdc6d73af6c40f57
- Run/attempt/job: 37247923030 / 1 / 111569414544
- Artifact: 11319844035, SHA-256 7edc964fe50816aac025f1a4cd6d43a3f2c644339ed35ba4902fab4553165f81
- Regenerated report: 9a95633a614f751e308d918ae67bd795266292399a6156ac558535e5f56cc711
- Failure fingerprint: 78ee90c7035f5d63724529ad2afee4152e02db2a06122986b2dc2bf2829306f3
- First failed boundary: ui / selection-not-observed. Build/signature/boot/install/launch passed
- Product DocumentManager reached bookmark resolution but got FileProvider -1005 / Resolver -1012 before the delegate. Complete product trace has no selectionReceived/importStarted
- UIKit control did not receive a selection; its own-container path differs from product cross-container access, and its stdout was absent
- Source plist remained 241 bytes with SHA-256 8adc01ad4d6304deb1daf74335f9acc7891ed5ed442dd85c5a50a7e30b58b96b

## Hypothesis and discriminating change

A shared local-file-provider/runtime interaction can explain both recipients failing before callback delivery. It is a hypothesis, not proof of an Apple defect. The previous broad service capture omitted the product selection interval and the relevant ResolverService/LocalStorageFileProvider processes.

Use one new, separately scoped cross-container UIKit diagnostic. Build and sign its producer, separate recipient and test runner once for explicit arm64 on one host. Reuse exactly the same complete artifact hashes across fresh job-owned SE destinations for exact iOS 26.2 and 18.6. Refuse missing runtimes, toolchain mismatch, changed bundle hashes or incomplete evidence; do not download a runtime or silently fall back. Retain partial preflight errors before raising.

Keep the normal complete-app workflow unchanged. The diagnostic lives outside its path filters and uses a distinct concurrency group; one reviewed direct develop commit triggers only the diagnostic and normal core checks. Do not issue another matching-path push while it runs. The source SHA/run/job IDs must be recorded when GitHub creates them.

## Unchanged acceptance and useful observations

- Same 241-byte public fixture, actual coordinated creation, distinct recipient, open-in-place .propertyList/.xml policy
- Two real system Cancel presentations, then one semantic file-cell activation; no warm-up selection, coordinate taps, retry or timeout extension
- Ten-second selection outcome; exactly one selected-file callback and actual dismissal required
- Original fixture readback/hash after each runtime, including failed UI
- Per-case stdout, screenshot/hierarchy, xcresult, ownership and bounded command manifests
- Focused resolver/local-provider/DocumentManager logs before broad service capture; exclude the demonstrated APS flood from provider query and record truncation
- productAccepted remains false: this isolates callback delivery, not pairing parsing/storage or a complete product pass

Only 18.6 passing supports a runtime-associated difference under the current shared host/artifacts. Both failing means 26.2 alone is insufficient. Control passing while the product remains failing returns attention to product presentation/lifecycle. Environment/build/evidence failures establish no runtime conclusion. Another full run without a new discriminating observation/change is not authorized by this decision.

## Follow-through

Read the actual result and preserve both cases. Fix only a demonstrated product or harness boundary. Before closing AUTO-02/PAIR-01, rerun complete-product acceptance for the final implementation and separately prove that selected invalid bytes reach the parser and the original data remains intact. Signing/permissions are not changed merely to make selection green. No physical-device, Apple-login or unattended-renewal conclusion follows from this diagnostic.
