# First helper-only native verification

The temporary `verify/staged-pairing-native` branch runs the reviewed helper-only
profile. It starts from the existing app verification commit `1fc8968` but adds no
app integration and activates neither composite acquisition nor OpenSSL.

The hypothesis is that the hash-bound staged pairing helper and bounded RSD/XPC
source compile against their actual pinned upstream workspace and pass their 18
and 25 host fixtures. Portable source checks cannot establish that result.

The workflow obtains the exact upstream commit with the existing pinned checkout
Action, verifies the complete source inventory, prepares official Rust 1.98.1 with
preinstalled rustup, records executable hashes and the exact Xcode 26.3 SDK
observations, and fetches only the unchanged lock's registry dependencies into an
isolated Cargo home. Fixture compilation uses a separately authenticated vendor
directory with Cargo frozen/offline dependency resolution and the complete
existing default FFI feature set. This is not an operating-system network sandbox. The producer’s justfile and packaging workflow are not executed. Cargo runs the
hash-verified workspace and dependency build scripts required by the fixture
build. There is no account or device operation.

Each command stage has a workflow deadline. The two supervised fixture commands
each allow at most 20 minutes, 32 MiB of merged live output and bounded owned
process-group cleanup. The 43-minute fixture step permits both command budgets;
the 90-minute outer job permits the sum of all individually capped stages and
evidence upload. These are first-run build supervision bounds, not changed
application or UI acceptance deadlines. Evidence uploads are limited to run
context, source/toolchain/crate manifests, native command logs and an explicit
4 MiB maximum subset of public openssl-sys 0.9.112, openssl 0.10.76,
tokio-openssl 0.6.5 and jktcp 0.1.7 source files plus any available explicitly allowlisted license/notice files.
That subset is reauthenticated
against the exact Cargo.lock archive checksums and records requested absent files
without substitution. Its review-checksums.json files cover only the retained
subset and are not Cargo vendor metadata. Dependency archives, compiled products,
user data and credential stores are not uploaded.
A failed or incomplete fixture group cannot produce completed test evidence.

The existing whole-app native job is skipped only on this exact temporary branch.
Develop, pull requests and other branches retain their previous native acceptance.
Full UI acceptance is unchanged. A component success does not establish iOS
compilation/linking, composite TLS or cancellation correctness, application
behavior, device identity, same-container validation, or device acceptance.

The candidate toolchain is first observed in this run. A recorded identity is not
proof of prior validation, and the host runner image remains explicitly observed
rather than falsely called immutable.
