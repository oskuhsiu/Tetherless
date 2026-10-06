# One-run decision: pinned Rust archive reader

- Evidence source: b477539bcfd43a4350d98b2a5fc5775bb8818e37; run 37440005277,
  attempt 1; Apple job 112191146458
- Authenticated artifact: 11400748913,
  SHA-256 105ee77c46e1c58c4e53b5e1829fc3701d13d1db0f9319bb72926ceaffb4c014
- Current report: SHA-256
  1c4dc7b102978fc22c4905050bba8a6d447ce61b394e8d2f5d6add9e6b4fdbb8
- Earliest failed stage: build evidence, after device Rust compilation;
  `04-rust-export-symbols.txt`, exit 1, 36 unreadable compiler_builtins members,
  Unknown attribute kind 102/105
- Hypothesis: the Xcode LLVM 17 reader cannot decode Rust LLVM 22.1.8 bitcode;
  observed partial symbol output is not proof of a complete scan
- Discriminating change: install official llvm-tools for pinned Rust 1.98.1,
  bind the host llvm-nm identity and use it for both full archive scans
- Expected first observation: the pinned reader emits complete Rust and C symbol
  output with zero exit and fully joined processes. Then all unchanged export,
  16-link, map, feature, input-preservation and packaging gates must pass
- Environment: keep macos-15 arm64, Xcode 26.3, recorded SDK identities and Rust
  1.98.1. Record actual runner image and added component identity; do not call
  the first new reader observation previously accepted
- Unchanged scope: no native artifact execution, app activation, Apple service,
  credentials, signing, parser/admission, OTA, manager replacement or release
- Next run: at most one new-source producer run after source review and commit.
  Parent owns publication and records its exact implementation SHA/run/attempt.
  No automatic retries; a repeated boundary requires new retained evidence and
  a new discriminating decision, not another identical run
- Consumer remains blocked until the new exact-source producer passes. Do not
  relabel old artifacts or edit runtime-producer.json to the failed source

See `Integration/Dependencies/idevice/SYMBOL_READER_REPAIR.md` for the reader
call-site audit and portable-vs-macOS evidence boundary.
