# Historical candidate SPDX 2.3 schema check

Checked 2026-10-05. **PASS: zero JSON Schema validation errors.** No corrected
derivative is needed for this schema check. The historical candidate and all
historical review files remain unchanged.

## Exact input and result

- Input: `docs/supply-chain/candidate-sbom.spdx.json`
- Historical baseline: `3dd8641e84698b97f96d53a6c53ed8c6ca4675bd`
- Input SHA-256: `e249a287e44af82fed07e6525b6bc18d801989ee67101ce1745dbb21e1b17ebc`
- Input size: 27,588 bytes; 32 packages and 37 relationships
- Complete result and provenance of this check: `result.json`
- Repeated validator output: `validation-output.json`
- Negative control: removing top-level `SPDXID` in memory produced the expected
  `/required` error; the original file was not changed
- All 40 hashes in the historical `review-file-hashes.json` still match, and every
  historical review copy is byte-identical to the retained original

## Official schema identity

The [official SPDX 2.3 specification](https://spdx.github.io/spdx-spec/v2.3/)
identifies this version. The schema was retrieved from the SPDX project's
[specification repository at its pinned release commit](https://github.com/spdx/spdx-spec/blob/aadf3b0b8dbbabdb4d880b0fc714255fea436ff7/schemas/spdx-schema.json).

- Release tag: `v2.3`
- Annotated tag object: `f7f7bce5511a23fe3c9d8a1edca0d870a7d0bea5`
- Commit: `aadf3b0b8dbbabdb4d880b0fc714255fea436ff7`
- File: `schemas/spdx-schema.json`, preserved here as `spdx-2.3.schema.json`
- Git blob SHA-1: `ee61e6686e885f8139c132647fd0b4f483b8fb81`
- Schema SHA-256: `239208b7ac287b3cf5d9a9af23f9d69863971102a5e1587a27a398b43490b89b`
- Schema size: 45,312 bytes; JSON Schema Draft 7

The retrieved base64 bytes match the upstream Git blob. The tag and exact-commit
file retrievals return identical content. The tag is unsigned; this is source
identity evidence, not a claim of cryptographic publisher authentication.

Schema attribution: SPDX Specification 2.3, copyright 2010–2022 Linux Foundation
and its Contributors. The schema is reproduced unchanged under the repository's
[Creative Commons Attribution 3.0 Unported license](https://github.com/spdx/spdx-spec/blob/aadf3b0b8dbbabdb4d880b0fc714255fea436ff7/LICENSE).

## Method and reproduction

Used the already installed `python-jsonschema` 4.26.0,
`jsonschema.Draft7Validator`, `referencing` 0.37.0 and Python 3.12.14. No package
was installed and no dependency executable was run. The schema passed its Draft
7 metaschema self-check. Validation used a registry that refuses remote retrieval;
there were zero retrieval attempts and no candidate data was transmitted.

Run from the repository root using those installed packages:

```sh
python3 docs/delivery/spdx-validation/validate.py
```

The script verifies both input hashes and the schema's Git blob identity,
validates locally, exercises the negative control and writes the complete result
to stdout. It does not modify inputs, download dependencies or run native builds.

## Limits

This tagged official schema contains no `$ref` or `format` keywords. A format
checker was enabled, but no format checks were prescribed by this schema.
Passing establishes the encoded structural/type/required-field/enum constraints;
it does not establish every normative SPDX rule, license-expression semantics,
identifier/relationship referential integrity or the factual accuracy of the
candidate's dependency and licensing claims.

This remains a historical candidate source/binary graph, not a final linked-binary
SBOM. No current native artifact was available for reconciliation. Complete
corresponding source, notices, licensing compatibility, binary provenance, ADI
rights, native/device acceptance and release authorization remain unresolved.
