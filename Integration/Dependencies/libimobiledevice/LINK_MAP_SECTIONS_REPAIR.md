# Read the explicit Apple link-map sections table

Run `37507597771`, attempt 1, job `112420111873`, source
`1a71785245af6ae6891a7134447a14cc07b39281`, passed the corrected 56-path
header comparison, the exact old-plus-four set of 829 unique C globals, and
the actual device C whole-archive link. Its next step failed in the text map
reader. Swift linking, Simulator compilation and XCFramework packaging were
not reached. All seven final input audits passed.

The source/run-bound verification report SHA-256 is
`eab70cb639d96244b5b337e00c19812556d5dd917f749ae6c08e01ad20776372`.
The complete authenticated map is retained as
`tests/fixtures/iphoneos-c-run37507597771.map`: 214,129 bytes, SHA-256
`53ea72932edfcb53555b9fe5affa5d477af2f2cb277b62b229760177d7b289d0`.
The corresponding complete 829-symbol receipt is retained beside it, SHA-256
`965c2b62539bdb90b3cc412e8bb48f615ca2324e2adde51eecbb10a6d3607d64`.

The map contains 94 object rows, then `# Sections:` at line 98, a column header
and 14 section-layout rows, followed by `# Symbols:` at line 114. The old reader
ignored `# Sections:` as a comment while staying in object mode. It consequently
rejected the first valid layout row at line 100 as a malformed object.

The correction recognizes that exact section marker after the object table and
enters a separate layout state. Layout rows must contain a hexadecimal address,
hexadecimal size, segment name and section name. Malformed or extra fields fail;
an unknown section marker does not disable object validation. The existing
`# Symbols:` transition resumes the unchanged live-symbol grammar.

Object duplicates, malformed objects, missing or duplicate required globals,
wrong archive ownership and collapsed SHA-family ownership remain errors. The
size bound, exported-symbol reader, native binary parsers, archive generation,
force-load commands and remaining native gates are unchanged.

Portable replay uses the entire authenticated map and all 829 required globals.
Only its 81 exact C archive paths are rebound to an owned canonical temporary
file for the existing strict path check; the stored fixture is unchanged. The
replay places all Ed25519 SHA symbols in object ID 41 and all glue SHA symbols
in object ID 81. Apple displays both members as `libimobiledevice.a(sha512.o)`;
the existing object IDs distinguish them, and the returned ownership dictionary
preserves those IDs. No receipt-format change is made.

After independent review, the parent may publish this exact delta once on the
verification branch. Expect the same genuine C map to pass text acceptance
while every negative ownership check remains enforced. Swift, Simulator and
packaging acceptance still require the new run. Any later failure needs its
own retained evidence and decision; this record permits no unchanged rerun
or permissive skipped-row fallback.
