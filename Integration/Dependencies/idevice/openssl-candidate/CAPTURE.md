# Pinned OpenSSL input capture

This preparation stage retains exact public input bytes for later provider tests.
It does not link, execute, parse a binary/signature, change the app's provider or
approve source/binary equivalence. The helper/RSD Rust step runs before this stage,
so source acquisition cannot prevent that step reaching Cargo.

The source is krzyzanowskim/OpenSSL commit
`fdc9231384f37f053dffe058fd6dfc6c5072dae5`, tree
`e7c94a8efdade4b77561c7176ba7cc4865bc32ee`. The manifest records 447 exact Git blobs,
40,574,701 bytes, selected from the complete untruncated Git tree:

- Complete iOS arm64 and iOS arm64/x86_64 Simulator frameworks, retained as opaque
  files, plus the root XCFramework Info.plist
- The macOS public headers and separate libssl.a/libcrypto.a fixture-host inputs
- LICENSE.txt, OpenSSL.json and Package.swift

Each Apple framework has 144 headers. The 143 names shared with its corresponding
repository platform include directory all have identical pinned Git blobs; the
additional framework file is OpenSSL.h. This is source-tree metadata correspondence,
not proof of runtime configuration or behavior. Capture verifies the actual bytes
before recording their SHA-256 identities. The existing published release ZIP is
not substituted or claimed equivalent.

The pinned official checkout Action uses sparse paths, no submodules and no saved
credentials. Cone-mode checkout includes ancestor/root files needed by the manifest.
The producer's scripts are never run. The capture script copies only manifest files,
checks exact size, Git blob and executable mode, and publishes a completed directory
only after every selected file verifies. Partial failure output is not uploaded as
verified input. The workflow owns fresh output names, checked before writing. This is a single-writer
publication path; it does not promise no-replace behavior against a concurrent writer.

The completed inputs and receipt are wrapped in a plain tar before artifact upload,
because upload-artifact normalizes direct file modes. Tar member modes preserve the
manifest identity, including the two executable framework files. The round-trip
fixture checks exact names, bytes and both modes without extracting or executing
any member. Only the completed tar is uploaded; partial copies/archives are excluded.

The callback/owned-write source review, separate host-static tests, Apple
OPENSSL_LIBS-empty final-framework arrangement, C/Swift/Rust linking and runtime
compatibility still require their own evidence. Helper success alone cannot close
those gates. No source-level signing or Mach-O admission work is part of this stage.
