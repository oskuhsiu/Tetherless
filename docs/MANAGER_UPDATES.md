# Manager replacement and recovery

Ordinary daily profile renewal does not replace the manager executable. A version update or explicit signing repair is a separate foreground operation. This implementation currently requires the same installed bundle identity, Team and data container; it is not a cross-Team migration facility.

## Transaction

1. Validate the running and prepared replacement identities. Obtain explicit foreground confirmation before the installer changes manager state. A backup-app shortcut cannot bypass this step.
2. Persist a bounded `manager-update.json` receipt in protected Application Support. Read it back. Mark it `applying` and verify that write **before** invoking installation. The phase means installation *may* have been dispatched, not that iOS accepted it.
3. When the replacement next runs, compare its bundle ID, Team, version/build and every main/extension executable and embedded-profile SHA-256 against the expected receipt. A changed bundle path alone proves nothing.
4. Update only the manager's whitelisted database fields, save, and read back main/extension metadata through a new database context. Replace only the manager's obsolete renewal record; retain other applications and account/backoff gates.
5. Mark the receipt complete only after those operations succeed. A failure keeps it recoverable for an idempotent retry. There is no arbitrary serialized Core Data graph import.

A pending receipt temporarily blocks profile transport so renewal cannot race manager recovery. Startup and the Auto Renewal recovery panel use the same mutation ownership as installation. An explicit discard operation only accepts the exact original running identity; it cannot undo an installed replacement, remove keys, or silently dismiss an unknown/mismatched receipt. Wait for any previously dispatched installation to stop before discarding it.

The delayed return-to-Home task is cancelled when its installation operation finishes or fails. An earlier failure cannot leave a timer that later suspends an unrelated screen.

## Cache identity

The inherited filename/length fingerprint is replaced by a streamed content hash. Same-length changed bytes produce a different identity. Hidden payloads are included; only the defined detached-signature/profile/OS metadata names are excluded. Paths, file types, link count, counts/depth and byte totals have explicit limits. This is cache identity, not independent code-signature trust validation.

## Verification boundaries

Core tests use real private files, restart/reconciliation and injected storage/database failures. Darwin tests hash real file content. Native builds check actual integration against the pinned app. These tests do not replace installation on a physical device. Exact profile/executable equality is not independent CMS trust or kernel launch attestation. Full UI navigation, delayed-install behavior, identity rotation and interrupted replacement still require integration/physical acceptance before release.
