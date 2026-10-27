# Provider-pinned Anisette cache reclamation

Cleanup is connected to ordinary managed-provider construction and to pre-install admission. No user cleanup button or daily library reinstall is required. This is local integrity/lifecycle work, not binary publisher authentication.

## Ownership

Each managed cache slot has one stable `usage.lock`. `LibraryCacheUsage` takes a nonblocking shared flock for a provider or an in-progress installation. Only reclamation takes the exclusive form. The inode is never removed or replaced, including when directories are pruned. Separate descriptors and separate processes respect the same boundary. The existing native mutation lease remains required to serialize installs, identity changes and foreground/background operations.

`pinCurrent()` acquires shared ownership before validating and returning the recorded generation. The native local/remote paths return `LibraryPinnedAnisetteClient`, which owns both the real upstream client and its pin and retains the pin through asynchronous calls. Merely capturing a pin in `libraryDirectoryResolver` would be incorrect: AnisetteKit's pinned `AnisetteClient` consumes that closure during initialization and retains only the URL, not the closure. The wrapper avoids that premature release. Remote-server-only mode does not manufacture a library pin.

## Reclamation

With exclusive usage ownership, read/validate the active receipt and inventory first. An unreadable, unsupported or tampered active generation aborts cleanup and replacement. Remove only canonical UUID-named `version-`, `stage-` and record `.staging-` entries other than the active generation. Unknown entries, the receipt and the lock are preserved. A complete bounded no-follow preflight runs before deletion; links, hard-linked files, special files and excessive trees are rejected. Actual deletion is descriptor-relative and rechecks identity. A partly removed obsolete tree can be reclaimed on the next attempt; the active generation is never part of that work.

A live reader returns deferred cleanup without reading the receipt or deleting anything. Installs also hold shared ownership through extraction and publication. Updates may retain old pinned versions, and the four-generation admission cap still refuses new updates while those versions cannot safely be removed. Once no provider is active, the next normal entry reclaims old generations and abandoned staging. With no pins, repeated updates no longer exhaust the four-generation quota. A failed update still preserves the previously active version until a later successful generation is published.

This assumes a caller-owned sandbox parent, the common mutation lease, and managed clients. It is not a defense against arbitrary code already executing inside the application. It does not yet collect the separate HTTP-transfer temp directories, all other app staging, or authenticate the metadata that supplied the original checksum.

## Evidence

Nine portable tests execute real filesystem operations and shared/exclusive descriptors (including an independent Python process on macOS/Linux). Four additional Darwin cache tests exercise repeated updates, pins across version replacement, corrupt-current refusal, and reclamation around actual install callbacks. Existing twelve cache tests remain, with the capacity test now retaining a real pin. The cache extractor in these core tests is explicitly synthetic; the native transform still uses the real SafeArchive and requires separate native CI. Passing navigation UI is not real provisioning/library execution or locked-screen renewal.
