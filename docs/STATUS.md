# Current checkpoint — owned ODA transfers and abandoned-download reclamation

Updated 2026-10-04 (Asia/Taipei). Starting develop head: 279c35c844877eefa26ed61767759d1d2a33df28. Product baseline 97903f0. This increment stays on develop; main is not promoted. No phone, account or signing credentials requested.

## Baseline confirmed

The previous complete-App/UI workflow **37129832976** at 97903f0 completed successfully in every step, including setup/recovery navigation, document-picker cancellation, diagnostic retention and upload. The earlier 5a7b5ab blank picker remains a historical failed run; a later pass is not a proven fix for every intermittent system-picker failure. No UI assertion is weakened in this increment.

## Connected change

The four public ODA data-transfer routes now use an owned TransferWorkspace pool, not independent random temporary folders. One real exclusive stable lock covers network callbacks, the final bounded no-follow read and cleanup. Another caller using the same pool fails busy before creating files. After process death, the next admission reclaims only recognized abandoned flat transfer directories under exclusive ownership. Unknown root entries and the lock inode are preserved; malformed/link/special-file stage contents fail the complete deletion preflight.

The existing download byte ceiling remains, with an additional workspace maximum of 128 MiB and one active transfer per pool. Normal success requires checked cleanup. Cancellation/error cleanup does not replace the original error. Both the main core and SideSign receive the identical tested helper source. No URL, metadata or account can select a cleanup path. See TRANSFER_WORKSPACES.md.

This does not yet collect legacy random folders or every IPA install stage, and does not claim aggregate in-memory JSON/Data budgeting or independent binary provenance. Those remain separate pre-handoff work. Unattended renewal policy, consent, pairing and signing behavior are unchanged.

## Local verification before commit

- Swift Debug and Release: **258 tests passed each** on completed invocations. The first compile-only filter had zero matching cases before new tests existed; that is not counted as test execution.
- Twelve new real-files workspace tests, plus two downloader/workspace test declarations (including parameterized success/error cases), cover live ownership, cancelled callbacks, success/error cleanup, a separate process respecting the lock, and process-death leftovers recovered by the actual production manager.
- Python integration tests use retained exact dd0b09c authentication and ae9fd0a cache-transformation inputs, validated by their pinned hashes. **150 checks passed with no skips**, including compiling the real namespaced downloader, workspace helpers and wrapper. Invalid URL and excessive limit tests made no network request or workspace. Native compile/UI results require this increment's own CI.
- The source baseline archive matched outer SHA-256 a9c55aac0f5b0e114ce7fc7d7219e7d9ebeeb7e8ad0dc74d36a0def4ad630ed1, inner TAR dbe6be2df67dfc7d18a58106337ba8e85cb1aa28f75e069facb4e27a0277dca3 and recorded 97903f0. The intervening 279c35c change is documentation-only.

## Next

1. Inspect this commit's macOS/iOS core, native Debug/Release and full App UI results. Earlier successful builds do not validate the new source. Keep real failures and exact implementation SHAs.
2. Continue independent library provenance/redistribution review and remaining native logging/callback lifetimes. Finish metadata structural/RAM and install-wide disk limits, remaining first-sign/self-update/configuration coverage and branding.
3. Consolidate physical acceptance only after feasible implementation/integration gates. No live Apple, downloaded-library execution, physical installation, locked-screen renewal or expiry crossing is claimed here.
