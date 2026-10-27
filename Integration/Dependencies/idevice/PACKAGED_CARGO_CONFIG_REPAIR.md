> Historical checkpoint. The current helper recipe is described in DERIVED_METADATA_REPAIR.md; it uses a separately audited build-vendor copy and classifies configs by actual Cargo discovery scope.

# Exact packaged Cargo config exception

## Observed failure

Helper CI run 37329375641 at c01234988c670421f78dc39ad5c3c1a2e5544e01
passed 89 portable macOS checks. Preparation then rejected
`vendor/dialoguer-0.12.0/.cargo/config.toml` before Cargo fixture execution.
No Rust fixture ran. The retained transport ZIP matches SHA256
`98192a9091f52b3cf9d1ef7862e8094249c0dbf54c9886f151b1713f0df7f1ce`.
Its 38 retained files do not include the dialoguer archive or config.

## Conditional exception and source identity

The only permitted packaged config is `.cargo/config.toml` within dialoguer 0.12.0
from crates.io, with both identities checked after archive authentication:

- Archive SHA256: `25f104b501bf2364e78d0d3974cbc774f738f5865306ed128e1e0d7499c0ad96`
- Config SHA256: `362771141e605c79a39783cb704a5736c746688c4ec9c20c9c448c75e2e8d2fa`

The 198 expected config bytes are retained at
`upstream/packaged-config/dialoguer-0.12.0/config.toml`. Their immutable source is
[console-rs/dialoguer commit 731c70b9a5919f39eb2b88f08a569c5980713b3f](https://github.com/console-rs/dialoguer/blob/731c70b9a5919f39eb2b88f08a569c5980713b3f/.cargo/config.toml),
Git blob `7c81907f38326657aa6e0c771577a470430ff842`. The annotated v0.12.0 tag
object is `7b0ef09fa8c8fbfc31bc8c74b09507efcb58a07b`. These upstream bytes
are an expected candidate, not proof that the published archive contains them.
The next authenticated archive extraction must match the exact config hash or stop.

The config contains only the four reviewed custom aliases `format`,
`format-check`, `lint` and `test-cover`. The implementation also compares the
parsed content with those exact four aliases. No build, source, environment or
target settings are permitted. Explicit built-in `cargo test` and `cargo metadata`
commands do not invoke these custom aliases, even if this config is discovered.
[Cargo's configuration reference](https://doc.rust-lang.org/cargo/reference/config.html)
describes its cwd/ancestor hierarchy and alias behavior. Dependency selection alone
does not make every sibling dependency's config an invocation ancestor.

All other packaged configs remain blocked. The exception cannot be used with a
different package, version, registry, archive, relative path or file hash. Legacy
`.cargo/config`, additional configs, config symlinks and ambient ancestor configs
remain blocked. No authenticated crate file or manifest is changed. Post-command
input audits still hash the accepted config and fail on any mutation.

## Retained all-config inventory

After authenticating all archives and extracted original files, preparation scans
all crate-root `.cargo/config` and `.cargo/config.toml` paths before rejecting an
unknown packaged config. It writes this new file using exclusive creation:

`.component/helper-work/vendor-config-inventory.json`

The parent workflow must retain that exact path on failure as well as success.
The file is outside `completed/` so it can survive a preparation failure before
native commands begin. Successful preparation also records its path/hash in the
existing vendor-layout receipt.

The inventory records package/path, archive/file hashes, byte sizes, fixed status
codes and parsed setting-name paths. It never records setting values, raw file
contents or TOML parser exception messages. Unknown, malformed or over-budget
configs remain blocking. Inspection continues to later configs after those errors,
within these explicit limits:

- 1,024 config entries; the pinned 363-package lock can have at most 726 root paths
- 64 KiB per config and 256 KiB total parsed input bytes
- 4,096 setting names, 128 UTF-8 bytes per key and 64 KiB total key bytes
- 16 nested key/array levels
- 1 MiB encoded inventory

If the entry or output limit prevents a complete inventory, the retained receipt
states that it is incomplete and blocking. Parsing/size errors retain bounded
metadata without config values. Existing evidence is never overwritten. No Cargo
command is launched when the inventory contains a blocked config.

## Verification boundary

The 22 new controlled checks pass, alongside the unchanged 18 vendor-isolation
and 23 process/summary checks. They cover exact exception identity, wrong package/
version/path/archive, changed content, ancestor/legacy/symlink rejection, complete
multi-config inspection, value omission, limits, retained failure evidence and
post-command mutation detection. The synthetic archive wiring fixture temporarily
substitutes its own expected archive digest inside the test only; it does not
claim to authenticate the real dialoguer registry archive.

Run the focused new suite with:

```sh
python3 -m unittest discover -s Integration/Dependencies/idevice/tests \
  -p test_packaged_cargo_config.py -v
```

The helper runner, source/profile hashes, 43 fixture filters, Cargo.lock, bounded
capture limits and native build flags remain unchanged. The actual archive match,
macOS Cargo/cbindgen build and all 43 Rust fixtures still require the parent's
next native run. This delta does not add a crate-lock mutation allowance.
