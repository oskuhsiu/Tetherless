# Authenticated native proof handoff

There is no precleared producer run. The caller requires an explicit successful
producer run, source commit and latest attempt at runtime. Its five native lanes
must belong to that one producer context. The consumer has a separate run,
commit and attempt. Source preparation alone cannot authorize a binding or build.

The current native recipe is pinned by `apple_recipe_index_sha256` in
`input-contract.json`, with transcript profile
`dbf445f10ca106d656c15ff5df84ab4bdcc38d4ecfe9d4010b6780e062a241ee`.
Actual corrected Apple build/link/package evidence remains required at runtime.

The provider-namespace candidate requires a new genuine Apple producer with the
exact export/header namespace contract, all eight C/Swift link probes per target,
disjoint native symbol inventories and retained mixed-provider link maps. The
old 9ee2ccc producer remains historical evidence and cannot satisfy these new
requirements. Its checked-in runtime selection must be replaced only after a
new successful producer is API-authenticated; no future run ID is invented here.

The indexed packaging operation is byte-identical to the independently reviewed
tiny-archive proof at source `7476bde6280c8fec042cf7d12c7fcf4bca68fc31`,
run `37399037692`. The operation retains its fixed xcodebuild child and natural
helper tail inside the unchanged bounded supervisor. Its lifecycle lines and
outer result remain in the authenticated packaging log/status. This consumer
binds that complete producer recipe and successful API-authenticated job; it
does not add a separate lifecycle-log parser. Tiny-archive success alone cannot
satisfy the full Apple artifact prerequisite.

## Two explicit source identities

The caller reads the producer and consumer commits and their complete Git trees
through authenticated, bounded, read-only repository API requests. The local
validator repeats the file checks before binding and compilation and afterward.

- Producer: every current indexed native recipe file, the recipe index itself,
  and the exact reviewed producer workflow must match their producer Git blobs
- Consumer: the fourteen reviewed mandatory compiler sources, the opaque reviewed
  manager support source, and reviewed preparation gate must match both their consumer Git blobs and consumer pins

The native producer compiles Rust and ABI probes. It does not validate an app-only
edit. A separately reviewed app change can therefore update the consumer pins
without rebuilding identical native inputs. Neither side is inferred from the
other; both source receipts are retained. The current gate pin remains
`9ddf28114d14bd99353ef4219e3043e85a2f22ea9429c85d1f887674bceebd68`.

## Artifact origin and transport

Only the consumer job receives `contents: read` and `actions: read`. The caller
obtains complete paginated artifact and attempt-specific job metadata. Each lane
requires its exact artifact ID/name, repository IDs, run, head SHA, successful
completed job and unexpired status. The API ZIP size and SHA256 must match the
retained download before extraction.

Automatic redirects are disabled. The API request carries authorization; the
subsequent approved HTTPS storage request does not. Signed redirect URLs are
neither retained nor printed. Network error messages expose only the error class.
The caller records original API metadata and computes the handoff hash outside
the artifacts. A neighboring hash file alone is not provenance.

The local validator takes that external handoff hash and independent expected
contexts. It rehashes each retained ZIP and compares exact context, native
receipt, status and audit ZIP entries with the extracted files. It makes no
network requests and does not independently authenticate a supplied JSON file's
origin; the reviewed caller owns that API trust boundary.

References: [artifact API](https://docs.github.com/en/rest/actions/artifacts?apiVersion=2026-03-10)
and [attempt-specific job API](https://docs.github.com/en/rest/actions/workflow-jobs?apiVersion=2026-03-10#list-jobs-for-a-workflow-run-attempt).

## Five required lanes

The required artifacts are host-only (26), combined (100), acquisition-transcript
(3), host-transcript (10), and apple-producer. Standalone acquisition-only (74)
remains part of the successful producer workflow; this consumer does not rebuild
it. Component receipts are at `completed/test-evidence.json`. Proof receipts are
at `<lane>-output/test-evidence.json`; Apple instead uses
`apple-producer-output/apple-build-evidence.json`. Every artifact contains
`evidence/run-context.json`. Downloaded roots have no `.proof` wrapper.

The obsolete initial job snapshot was lost during workspace replacement and is
not included in this new packet. Exact matrix names remain in the reviewed
contract and producer workflow identity. Fresh successful attempt-specific API
job metadata is mandatory; no historical snapshot substitutes for it.

Each artifact records its explicit producer attempt, which may be earlier than
the selected producer run's latest successful attempt after a failed-job retry.
The exact attempt-specific job query must agree; an original job `run_attempt`
field, when present, must agree too. Consumer attempt numbers are independent in
retained mode. No mixed producer runs, repositories or source commits are allowed.

## Handoff shape and invocation

The JSON contains `schema: 1`, `mode: retained-producer`, the separate `context`
and `producer_context`, original `api_source_commit`/`api_source_tree`, original
`api_consumer_commit`/`api_consumer_tree`, and exactly five `artifacts` rows. Each
row includes `producer_attempt`, original `api_metadata`, original `producer_job`,
canonical `producer_job_query`, relative `archive_file` and `extracted_root`.
Every extraction root is distinct. Context `needs` records the caller's verified
successful producer groups; it does not invent consumer job dependencies.

The branch-compatible caller uses a push on `verify/staged-pairing-native`
filtered to `Integration/pairing-ios-diagnostic/runtime-producer.json`. The source
packet ships only a null template, never a real producer context. After actual
success, the publishing owner may create the real context with the reviewed run,
commit and attempt. This does not touch producer path filters or commit binary
hashes. The API supplies artifact digests at runtime. The template cannot pass
the strict reader.

`read_runtime_producer.py` exports only the three validated producer identity
variables. `call_retained_diagnostic.py` supplies the caller-computed hashes and
independent consumer/producer identities to preparation and both Debug/Release
builds. All entrypoint arguments remain explicit; no artifact text becomes a
shell command or a workflow input.

Compilation compares complete observed tool identities with the authenticated
Apple device target's retained observations, including the exact Swift driver
and compiler text. It also verifies the original toolchain-lock hash. Both
configurations require the fourteen actual compiler source files, sentinel conditions,
module/header identity and ordinary final archive/framework link evidence.

Retain both source chains, API metadata, five ZIPs, binding receipt, per-command
logs/statuses, native-handoff and binding-input audits, bounded raw compiler response/file-list/module-map bytes with a failure-safe
inventory, final app opaque output identity, and final compile receipt. Normal Integration tests, including the approved
macOS Swift callback spy, remain in the caller alongside focused diagnostic tests.
No iOS app/native binary is executed and no product capability gate is opened.


## New consumer source after recovery

Fourteen of the former packet's twenty-one files were recovered with exact
approved SHA256 matches. The observer, sentinel, compile runner, two main fixture
files and README are newly authored and need their own review. None inherits the
former 141-test result. The explicit recovery boundary records the seven missing
files, including the obsolete job snapshot described above.

The current native source contract requires six successful C/Swift ABI probes
(pairing, host and result constants), their complete joined-process statuses,
and the four bounded retained header files with their comparison/retention
receipts. All bytes must match the ZIP-authenticated producer inventory. The
producer keeps OpenSSL outside the Rust XCFramework; the app observer must match
the selected final framework's opaque bytes independently.

Both diagnostic configurations use ENABLE_DEBUG_DYLIB=NO so ordinary final-link
evidence identifies the app executable directly. This setting applies only to
the diagnostic xcodebuild command. The 1800-second/32-MiB compile supervisor,
complete observed Swift stream comparison and before/after binding, recipe and
native-handoff audits remain explicit. Failure never publishes a success receipt.
