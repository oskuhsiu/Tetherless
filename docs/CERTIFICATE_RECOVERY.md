# Explicit certificate-request recovery

Implementation checkpoint: the core recovery API and its tests are implemented. The native controls are the next integration step, not yet wired by this checkpoint.

`CertificateRecoveryCoordinator.check` accepts a read-only `CertificateIssuanceLookup` capability with no key generation, request submission, persistence or revocation methods. It never writes the request journal. Prepared requests are reported without sending them; submitted requests are queried in the current owner's Team; issued responses are validated locally. A unique matching response permits an explicit save action, not automatic activation. An empty query result never proves Apple rejected an earlier request.

Explicit actions are separate: save an existing issued/matched certificate, submit an existing never-dispatched request, or discard a never-dispatched request. A request already marked submitted cannot be resubmitted or discarded. Its private key remains recoverable. Each action checks owner (account/Team/type), request UUID, current phase and cancellation under the common mutation lease. A late lookup for a changed request cannot publish its result.

The existing issuance method's `allowNew: false` only prevents key generation when no request exists. It can still dispatch an already-prepared request. It is intentionally NOT the check API.

Tests call the production recovery API against real durable journal files and a scripted portal. They verify unchanged bytes during checks, owner/UUID binding, duplicate clicks, absent/ambiguous portal results, cancellation, concurrent record replacement, failed writes/readback and failed key persistence. They do not prove real Apple behavior or locked-screen renewal.
