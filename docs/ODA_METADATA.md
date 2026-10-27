# Bounded ODA metadata and explicit source selection

The native server-list, source-metadata and indirect-package fetch routes now use `ODAMetadata` through `ValidatedODAMetadata`. The underlying HTTPS/transfer workspace rules are unchanged. The old tolerant public SideSign model decoders still exist for source compatibility, but these network routes do not use them to choose a package or silently ignore bad fields.

## Before object allocation

A noncopying byte-buffer scan bounds JSON nesting, value count, array length, keys, ordinary strings, payload strings and total string bytes before Foundation builds the decoded graph. It checks full grammar, UTF-8 and Unicode surrogate pairs, including ignored fields. Object keys are decoded with a small bounded Foundation string decoder before duplicate detection, so escaped-equivalent names cannot select different values. Cancelled scans remain cancellations; errors contain fixed categories, not source bytes or field values.

Production limits: the existing metadata body ceiling (Base64 of a 64 MiB archive plus 1 MiB), depth 8, 4096 values, 256 entries per JSON array, 128 raw UTF-8 bytes per key, 16 KiB per ordinary string, 256 decoded UTF-8 bytes per server name and at most 128 servers. Only known payload aliases at the direct package root or immediately under `oda` receive the larger Base64 budget. All string bytes together are limited to that payload budget plus 64 KiB. Numeric tokens are limited to 64 bytes. Escapes count against raw-byte budgets, making limits conservative.

Only one metadata decode may execute per process; another call fails explicitly busy rather than queuing a second Foundation graph. This is NOT a measured whole-App RSS ceiling or an install-wide memory reservation: already downloaded Data, decoded payloads, Base64 conversion, other processes and caller retention are separate. Foundation still performs the final typed decode. No claim of total RAM safety or live-service acceptance follows from these limits.

## Schema and fallback

Supported layouts remain a direct ODA package, a `{servers, oda}` object and a legacy server array. Package digest aliases `sha256`/`sha`/`s` and payload aliases `url`/`l`/`libraries`/`payload`/`data` are supported individually. More than one non-null alias is rejected, even when values match. A null alias may coexist with one real value. Known fields with wrong types, mixed direct/catalog envelopes and duplicate keys fail explicitly rather than selecting whichever decoded first. Bounded unknown fields remain compatible with future additions.

Addresses and resolved metadata references require HTTPS without embedded credentials, fragments, control characters or unescaped spaces. Relative references resolve against the downloaded source URL. An explicitly supplied fallback may be selected only when a structurally valid recognized catalog truly has no ODA entry. A malformed ODA value, invalid URL, failed decode or indirection to another catalog is not permission to use fallback. The indirect package route expects a direct package, so it cannot recurse through unlimited metadata links.

These choices deliberately reject formerly tolerated ambiguous/invalid metadata. They do not authenticate the publisher or the libraries. Digest validation, archive checks, receipt verification, binary provenance and redistribution rights remain distinct boundaries.

## Evidence

18 core tests execute the real scanner and typed decoder against valid/hostile JSON, exact limits, escaped keys, invalid Unicode, cancellation and synthetic secret-bearing errors. Five integration tests exercise pinned-input rejection, all three transformed fetch routes, unchanged helper copies and the actual compiled adapter with SideSign's real model declarations. The no-network adapter test verifies both legitimate fallback and refusal to fall back on malformed metadata or an unsafe reference. Native compilation and full UI require their own CI results; these tests use no Apple credentials or executable library payload.
