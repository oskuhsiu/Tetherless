# Offline Homebrew diagnostic and fresh metadata cache

The owner approved the four-package setup on 2026-10-06. The earlier
`PROPOSAL.md` records its original unapproved review state; this correction
does not expand the approved package set or authorize a separate installation.

## Observed failure

Run `37490322437`, attempt 1, job `112361029248`, source
`dec9d9b40fe956a974bbb806a7aba8b8908f1ade`, passed 103 portable tests and
16 host-contract tests. Setup stopped at its first command, offline `brew config`.
Homebrew 6.0.22, HEAD `08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3`, attempted
to initialize `api/internal/packages.arm64_sequoia.jws.json` in the fresh cache.
The intentional network denial produced curl exit 6, HTTP 000 and brew exit 1.
This is not evidence of an external DNS outage. No formula metadata validation,
bottle acquisition, installation, native-source acquisition or native build ran.

The 117 Cellar names/version/receipt entries and all nine recorded runtime,
existing-tool and unrelated-formula preservation checks remained unchanged.
The process was reaped and its group was empty. Its status says
`output_complete=false`, `output_truncated=false`; the retained 2,246-byte log
is evidence of the failure, not an accepted complete command output.

Verified evidence identities:

- Actions artifact `11425690962`, 15,150 bytes, SHA-256
  `6d4bf6b535e61abe8b494e3a025999bef44689e12453813880036aace1eb1e3c`
- Raw setup log SHA-256
  `29d56d1d7bd988f27fa9258367badef6c6b690702a9bce5ef3a2bfab619e7eff`
- Independent run report SHA-256
  `e1bf9de16f474d8d3042ca8acc474d89710617f8eaae62a47fc70a4d161bd187`
- Setup failure analysis SHA-256
  `12749dc768530846414999476c94c6f36a09d81df27ccb1cd8a06035d6864a4d`

## Source-backed correction

The [observed Homebrew revision's command entry point](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/brew.rb)
calls `Homebrew::API.fetch_api_files!` before Ruby commands, including config,
unless `HOMEBREW_NO_INSTALL_FROM_API` is set. The [documented option](https://docs.brew.sh/Manpage#environment)
is now supplied through `/usr/bin/env` for the single offline config command.
It does not enter the shared environment or any formula command. The same
network denial and runtime/code write restrictions still supervise config.

The first normal `brew info --json=v2 --formula m4 autoconf automake libtool`
operation remains the permitted network metadata acquisition step. Its complete
merged output is retained under `acquire-selected-metadata`, including any
startup progress. [Homebrew's download queue](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/download_queue.rb)
writes download progress to stderr, which the existing supervisor intentionally
merges with stdout. That first output is not accepted as JSON metadata.

The identical command is then repeated offline against the owned cache, and
only this output is strictly parsed and checked against the unchanged four-formula
lock. No warnings or arbitrary prefixes are stripped. [Homebrew's API cache logic](https://github.com/Homebrew/brew/blob/08e85c4e42f5d8f1ea17c36cb59cf61c2ccb26c3/Library/Homebrew/api.rb)
uses an existing nonempty cache when `HOMEBREW_NO_AUTO_UPDATE` is set. Missing
cached metadata or additional network needs fail at the offline boundary.

There are no network-policy changes. The first diagnostic remains offline;
metadata acquisition uses the same previously approved command and protections;
the added acceptance read is offline. Runtime bootstrap, extra packages,
unrelated upgrades, source-built tools and formula/bottle drift remain rejected.
The workflow, formula lock, native build, source authentication, public headers,
SHA contexts, namespace, OpenSSL, whole-archive links and final audits are unchanged.

## One next-run decision

After independent review of this exact delta, the parent may publish it once
on the existing verification branch. Expect the offline config diagnostic to
finish, the ordinary metadata acquisition to populate its cache, and the offline
metadata read to match the existing lock before any bottle fetch. Every original
setup and native acceptance condition remains required. A new failure requires
its retained evidence and a new decision; this record permits no blind rerun.

Portable mock regressions cover the observed fresh-cache startup failure,
command-local API suppression, acquisition progress retention, strict offline
JSON acceptance and failure stops before downstream operations. They do not
establish actual macOS/Homebrew execution or native C acceptance.
