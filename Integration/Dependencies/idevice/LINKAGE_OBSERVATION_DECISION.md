# Diagnostic capture after the first mixed Rust/C link

## Observed boundary

Source `da12c068bb069c2e1c8fb27ea19a041f902474f4`,
[run 37515373680](https://github.com/oskuhsiu/Tetherless/actions/runs/37515373680),
attempt 1, Apple job `112446821537`: device Rust compilation, the existing export
checks and three probe links completed. The first mixed C/Rust probe linked
successfully, then UTF-8 decoding of its retained linker map failed. Simulator
Rust compilation and XCFramework packaging never started. This is an evidence
reader failure, not a Simulator or linker startup failure.

The original map is 4,652,403 bytes, SHA-256
`d71ea907b4d554f2352f1c4bd5880ed649a90a4128b2ad2e42a81f7be9b79097`.
Literal-string payloads contain invalid UTF-8 and non-LF control bytes. The
structural reader must consume bytes, split only on LF and validate ASCII syntax
without changing opaque literal payload bytes. Raw hashes and the 32 MiB map
limit remain authoritative; replacement decoding and Unicode splitlines are
not admissible.

After that reader boundary, 29 required C names also have Rust `bcm.o` rows.
All 1,211 required C/Rust names appear. A linker map has no symbol visibility
flag. The previous merged external-symbol log has interleaved `no symbols`
diagnostics, and its failed artifact did not retain a bound Rust archive. Those
observations are insufficient to change ownership acceptance. Duplicate required
live rows must still fail; external-global disjointness, required exports,
required owner identity and all input audits stay unchanged.

## Discriminating diagnostic

Before any export scan or probe link, preserve the exact produced Rust static
archive and authenticated selected C archive in a fresh `linkage-observation`
directory under each reached target's work directory. Each opaque archive is
limited to 256 MiB. Copying is bounded, hashes both source and retained bytes,
and detects path/descriptor changes during reads. No archive or native payload
is executed. The C copy must match the selected provider's existing archive
hash. Retention does not authorize using a failed artifact as a provider.

Invoke the already observed and hash-pinned Rust LLVM reader once for each
original archive with exactly these diagnostic flags:

```
--defined-only --format=darwin --print-file-name --quiet
```

[LLVM's documented options](https://www.llvm.org/docs/CommandGuide/llvm-nm.html)
provide defined symbols, Darwin visibility descriptions, per-symbol member
provenance and suppression of the specific `no symbols` diagnostic. Local
definitions remain included so the duplicate map rows can later be compared
against explicit external/non-external records. This diagnostic does not parse
the output into acceptance facts or replace either original external scan.

The existing bounded supervisor retains complete scan logs and status sidecars,
with its existing command/output/cleanup limits. Both original archives and
both retained copies are rehashed before and after each of the two diagnostic
scans, two unchanged acceptance scans and eight unchanged links per target.
There are at most 12 observed operations per reached target. Raw command log,
status and mixed-link map hashes are written before ownership validation, so
the unchanged duplicate gate cannot discard the new evidence. A failed command
remains primary if capture also fails; a capture failure prevents otherwise
successful work from being accepted.

Only these two explicit folders are added to the existing artifact upload:

```
.proof/apple-producer-work/aarch64-apple-ios/linkage-observation/
.proof/apple-producer-work/aarch64-apple-ios-sim/linkage-observation/
```

No new runner, tool installation, link option, SDK, OpenSSL identity, C source,
C selection, runtime producer context, product activation or device action is
introduced. The diagnostic archives stay outside `completed` and packaging.
Existing recipe/workflow hashes are refreshed to bind this exact source.

## Expected observation and operating gate

One independently reviewed combined capture/byte-reader candidate can obtain
member-qualified visibility evidence bound to exact Rust/C archive bytes. It
may deliberately fail at the known duplicate-owner gate. Inspect that retained
evidence before considering any separately reviewed ownership change. The
byte-reader repair alone must not be published or run. An unchanged rerun is
not the next step. This decision does not claim native success or permit using
the historical failed Rust producer as runtime input.

Portable tests use opaque synthetic archives and Python-only command doubles;
they can prove capture bounds, mutation rejection, failure evidence and unchanged
gates, but cannot establish the pinned macOS reader's actual output. The tiny
genuine-map regression records its source and exact byte ranges. The complete
failed map remains in the preserved failure proof, not the repository.
