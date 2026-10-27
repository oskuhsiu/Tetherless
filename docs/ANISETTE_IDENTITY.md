# Coherent Anisette provisioning identity

The device identifier and adi.pb are one versioned device-local Keychain record, shared by the on-device provider and the explicitly selected remote provider. This is not an Apple account, signing certificate, library-integrity assertion or proof of login. The provider selection policy is unchanged.

## Persistence and recovery

The native wrapper uses KeychainAuthenticationStorage in a dedicated non-synchronizing AfterFirstUnlockThisDeviceOnly namespace. The record has a generation UUID and prepared, ready or reset phase. A ready record contains both identifier and blob. The identifier is committed before provisioning starts. New returned material is committed and read back before headers can escape. When cancellation arrives during the provider call, returned material is preserved before cancellation is surfaced; a provider that throws without returning its material is outside this recovery boundary.

Legacy canonical UUID strings and strict 16-byte Base64 UUIDs are supported. Legacy blob Base64 must be canonical and nonempty. A blob without its identifier, unreadable records, unsupported schema or malformed data are errors; none generates a replacement identity. Blob and envelope limits are 32 KiB and 64 KiB respectively. These structural checks do not validate Apple's ADI protocol content.

Migration writes and reads back the whole new pair before removing split fields. A coherent record remains authoritative if legacy cleanup fails, and cleanup is retried without reading partly removed fields. Resets are explicit only: blob-only reset preserves the identifier but changes generation, full reset writes a secret-free tombstone. Late results cannot replace a changed generation. The new namespace survives legacy-service cleanup so old state cannot resurrect. Corrupt/future envelopes cannot be silently reset.

## Mutation ownership

Every native identity use or reset enters NativeMutationGate and a generation-bound in-process admission guard. The process lock remains held across provisioning and persistence. A competing or reentrant provider receives a busy result rather than sharing mutable state.

The headless RenewalEngine now transfers its already acquired ProcessLease into MutationScope. Nested authentication/Anisette operations borrow that actual descriptor; they do not reacquire it or skip exclusion. Admitted children keep the descriptor until they finish. The old handle cannot unlock the transferred descriptor or close an unrelated descriptor reused later. Native foreground repair preflights use the same scope. Daily cadence, profile verification and unattended consent are unchanged.

## Evidence and limits

Production-store tests use actual durable files and synthetic provisioning results, including lost writes, readback failures, invalid legacy fields, cleanup interruption, resets, stale callbacks and cancellation. Real descriptor tests include the actual RenewalEngine entering a nested native-style lease, outside-handle exclusion and child lifetime. A separate macOS test uses the actual system Keychain with a unique service and synthetic blob. Native source transformations are hash-locked for every input before any write.

Compilation, Simulator navigation and synthetic-provider tests do not prove real Apple provisioning, hardware protection or locked-screen renewal. Existing executable cache validation/promotion and independent binary provenance are separate unfinished work, as are broader native logging, resource cleanup and supported-configuration acceptance.
