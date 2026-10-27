# Explicit certificate-request recovery

Implementation: core recovery, native portal integration and dedicated foreground controls are connected. Actual signed-in Apple execution is not yet verified.

`CertificateRecoveryCoordinator.check` accepts a read-only `CertificateIssuanceLookup` capability with no key generation, request submission, persistence or revocation methods. It never writes the request journal. Prepared requests are reported without sending them; submitted requests are queried in the current owner's Team; issued responses are validated locally. A unique matching response permits an explicit save action, not automatic activation. An empty query result never proves Apple rejected an earlier request.

Explicit actions are separate: save an existing issued/matched certificate, submit an existing never-dispatched request, or discard an existing never-dispatched request. A request already marked submitted cannot be resubmitted or discarded. Its private key remains recoverable. Each action checks owner (account/Team/type), request UUID, current phase and cancellation under the common mutation lease. A late lookup for a changed request cannot publish its result.

The existing issuance method's `allowNew: false` only prevents key generation when no request exists. It can still dispatch an already-prepared request. It is intentionally NOT the check API.

Tests call the production recovery API against real durable journal files and a scripted portal. They verify unchanged bytes during checks, owner/UUID binding, duplicate clicks, absent/ambiguous portal results, cancellation, concurrent record replacement, failed writes/readback and failed key persistence. They do not prove real Apple behavior or locked-screen renewal.

## Native integration and foreground UI

The native controls now live under Auto Renewal → Certificate request recovery. Local reload and never-submitted discard use the common lease with no auth-header or portal call. Check/save/submit go through authenticated portal methods that verify the exact saved request before obtaining headers, then hold the lease through completion. Normal issuance and recovery use one owner-scoped Keychain namespace.

The request type is explicit. Confirmation captures the request UUID, type and action at the original button press. A changed account, Team, request or phase is rejected by the core instead of applying the confirmation to a new request. Leaving the screen cancels the task and invalidates its UI generation. Issuance still preserves an accepted certificate/key even if the view disappears after submission.

Checking does not persist the matching response. Saving re-queries a submitted request under the lease before persisting a unique, validated match, or saves the previously validated issued response. Saved material is cached and read back; the active signer, installed applications and unattended-renewal consent are not changed. Continue the regular setup/signing workflow separately. Expired sessions still require the normal account-repair UI.

An uncertain or ambiguous response remains a safe blocked state, not an automatic create-again path. There is deliberately no force-discard or revoke-all action. Real Apple visibility and signed-in interaction are part of consolidated device acceptance.

The actual-app UI test is extended to open the recovery screen without fake credentials, verify its signed-out message, reveal each control on a small display and require all portal/mutation controls to be disabled, then return and verify consent remains off. At the integration commit, this is a test definition awaiting its fresh native/UI CI, not a passing execution claim.
