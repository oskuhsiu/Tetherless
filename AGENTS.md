# Tetherless development contract

## Owner's required workflow

Complete implementation, native integration, build verification and all feasible non-device tests BEFORE requesting the owner's iPhone. Device checks are a consolidated acceptance pass, not recurring development blockers. A missing device does not justify stopping unrelated implementation. Do not request passwords, 2FA codes, UDIDs, pairing files or private keys in chat, commits or issues.

## Branch and pull-request workflow

- `develop` is the integration branch for ongoing development. Create new feature/fix branches from `develop` and target all development-stage PRs at `develop`, never `main`.
- Continue existing feature work on its current branch and retarget its PR to `develop`; do not reset branches or discard existing commits to adopt this workflow.
- `main` is reserved for release/stable integration. Promote `develop` to `main` only through a separate, explicitly approved release PR after the agreed acceptance gates.
- The owner explicitly authorized merging existing and subsequent development PRs into `develop`, or committing directly to `develop` (2026-10-02). Prefer direct, tested commits for small coherent increments. Never force push. This authorization does not cover promotion to `main` or a stable release.
- Before creating or updating a PR, verify its actual base branch. CI results must correspond to the relevant implementation commit and integration target; green checks are not physical-device acceptance.
- The repository default branch and branch-protection settings are separate from PR targeting. Do not change them without an explicit request.

## Product invariant

A personal/free Apple Account is primary. After first-time authorized setup, normal renewal is mobile-only, proactive and unattended: no desktop, opening the manager or pressing refresh. Daily is the default policy; a two-hour test policy is available through injected settings. Never change a device clock to simulate Apple authorization. Long real-time soak testing is separate, not the development iteration cycle.

## Evidence and safety

- Build passing, scripted tests, simulator results, device readback and device launch are DIFFERENT evidence levels.
- Never mark a module complete because a stub/mocked backend returns success. Connected native routes still need their integration and acceptance evidence; scripted results do not prove real-device behavior.
- `appliedUnverified` is not `verified`. Unchanged or merely displayed expiry is not renewal.
- Recover interrupted transactions by readback before retrying mutation. Preserve the write-ahead journal.
- Serialize all native mutation paths (including old foreground routes), not only calls to the actor. File locks must not be unlinked while in use.
- Never silently revoke certificates, rotate signing identity, reinstall the manager, disable another VPN or fall back to foreground during unattended work.
- Keep sensitive artifacts out of logs and CI. No secrets are required for unsigned CI builds.
- No exploit-based limit bypass, DRM circumvention, fake audio/location keepalive or cloud custody of credentials.

## Repository and verification

Work directly on `develop` or use short-lived development PRs that are merged into `develop` after checks. In-progress integration is allowed; stable-release and device-acceptance claims still require their evidence. Preserve upstream licenses, copyrights and branding attribution; this is an independent derivative, not an official SideStore release. Do not submit automated contributions/issues to upstream maintainers. Never run upstream `make update` (`--remote`) or curl-to-shell recipes. Pin and review all dependency updates.

Run `swift test`, `swift test -c release`, and `python3 -m unittest discover -s Integration/tests -v`. Run the unsigned native CI separately. Inspect actual logs and report failures precisely; do not call queued workflows successful. Keep `docs/STATUS.md` accurate and include a single consolidated acceptance procedure before device handoff.
