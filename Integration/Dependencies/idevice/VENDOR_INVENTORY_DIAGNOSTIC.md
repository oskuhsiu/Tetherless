# Retain the exact vendor inventory mismatch

Run 37339519028 at 87dcec6fd14dfbbe9cdef0b36feeebe72b1a6dd0 passed
116 portable macOS tests, then failed before Cargo with:

`pristine vendor inventory changed before derivation`

The supplied artifact ZIP matches SHA256
`41d398fe0e152e5781421788721f42a2dd0765c989c52b6a366f34b6fd72a0cf`.
It does not contain the complete vendor tree or the two compared inventories.
The exact differing native paths are therefore unknown. All original logical
paths had passed their hash checks before the raw path/hash dictionary comparison.
There is no intervening code that writes inside the vendor directory. Filesystem
filename representation is one hypothesis; it is not a demonstrated cause.

This delta adds diagnostics only. Before the existing rejection, it writes:

`helper-work/vendor-derivation-inventory.json`

The parent workflow must retain this exact path on preparation failure. The error
also gives separate missing, extra and changed counts. A matching inventory writes
the same receipt with zero differences and binds its path/hash into the derived
layout receipt.

The new JSON records both inventory hashes, full counts and up to 64 entries independently for each of the three
categories (missing, extra and changed), at most 192 entries total. Each recorded entry contains its exact logical or enumerated path
and expected/observed file hashes. Paths longer than 512 UTF-8 bytes are explicitly
omitted and represented by byte length and path hash. Truncation is explicit, with an omitted count for each category. The
encoded diagnostic is capped at 1 MiB; if that cap is exceeded, the complete counts
remain while detailed entries are explicitly omitted. File contents are never
retained by this diagnostic.

The original exact comparison remains the admission condition. No filename
normalization, case folding, inode reconciliation, ignored files, changed pins or
mutation allowances are introduced. The retained diagnosis can distinguish path
representation from extra files or changed content in the next parent-controlled
preparation attempt. A diagnostic run alone is not a native fixture pass.

Eight controlled diagnostic cases and the unchanged 12 derivation cases pass
locally. They distinguish missing/extra/changed files, preserve dotfile entries,
keep case/Unicode spelling mismatches rejected, bound detail/path output, retain all three categories when each exceeds its cap, and
retain the mismatch before the same failure stops derivation. The helper runner,
source overlays/profile, generated Rust patch and all 43 fixture selections are
unchanged. No native toolchain or CI run was executed by this worker.
