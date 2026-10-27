# Authenticate the Homebrew compatibility metadata reader

Run `37495495457`, attempt 1, job `112378841927`, source
`b2da26b4901d5b09bd28601dab19772b82985a40`, completed all five initial
setup commands, including the offline config and cached metadata read.
The strict metadata validator then rejected `compatibility_version: null` for
all four formulas, where the locked formula sources declare the integer `1`.
The other 116 comparisons matched. No bottle fetch, installation or native
compilation started; all nine prior preservation audits passed.

The source/run-bound verification report has SHA-256
`adf16b496b39f8e0288d254e4042c037defadae97338ec9c19e99a5e5cd13d9b`.
Its metadata analysis has SHA-256
`710dda08d42551c297e34cd6d5b17a6d1626951541e13621af39d65fcab3073f`.
The exact 11,434-byte offline JSON is retained as the test fixture
`tests/fixtures/homebrew-6.0.22-selected-metadata.json`, SHA-256
`328dbe191e11d9aa068686b50be18cb7b5e5087218afbad3fd65c370967d6516`.

## Exact source explanation

The observed Homebrew version is 6.0.22, commit
`08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3`. Its
[API formula loader](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/formulary.rb)
constructs a Formula subclass from API data and copies revision and version
scheme, but never assigns `compatibility_version` anywhere in that loader.
The [Formula implementation](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/formula.rb)
defines the unset class value as nil, copies it into the instance and emits it
in its JSON representation. The API struct and generator also omit this field.
[The info command](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/cmd/info.rb)
serializes these generated Formula objects. This source behavior explains the
four observed nulls without implying that the pinned formula files changed.

Null is not equivalent to compatibility version 1. Homebrew describes this
field as an API/ABI compatibility hint for dependency upgrade decisions.
This correction does not patch Homebrew or assign 1 to its generated classes.
The setup still requires the exact locked formula versions and bottle bytes;
it accepts no alternate package version based on a compatibility hint.

## Bounded admission

For every selected formula, the helper now checks that its retained Ruby source
has the locked SHA-256 and exactly one literal declaration of the locked integer
compatibility version. The CLI's formula-source hash must also match that same
lock. The lock itself, including all four compatibility values of 1, is unchanged.

A null CLI field is accepted only when four reader files from the installed
Homebrew match the exact SHA-256 values recorded in `API_COMPATIBILITY_READER`:
`brew.rb`, `cmd/info.rb`, `formula.rb` and `formulary.rb`. These hashes come from
the official observed commit, read without execution. The files are included
in the existing runtime before/after hash audits and remain within the existing
write-protected Homebrew Library. Missing or changed reader identities reject
the null case. Missing metadata fields, unexpected integers and noninteger
values remain errors. A directly reported exact integer continues to use the
ordinary equality path.

The raw JSON remains unchanged. The setup receipt separately records the
observed value, authenticated source declaration, formula-source hash and
expected/observed reader hashes. Both offline metadata validations use the
same authenticated reader profile. Formula versions, source hashes, dependencies,
bottle identities, network denial during install, unrelated-package checks and
all native C/Rust/ABI/link gates remain required.

## One next-run decision

After independent review, the parent may publish this narrow delta once on
the existing verification branch under the owner's four-package authorization.
Expect the actual installed reader hashes to match the observed-source profile
and both metadata validations to preserve raw nulls while proving source value 1.
Only then may the original bottle acquisition and installation gates proceed.
A reader mismatch or any package/dependency drift must stop with evidence;
there is no general null fallback or unchanged rerun authorization.

Portable tests replay the exact failed JSON, reject unknown/changed readers and
source declarations, preserve raw observations, reject other identity drift and
exercise both setup metadata gates and final reader-mutation auditing with mocks.
They establish neither actual tool installation nor native C acceptance.
