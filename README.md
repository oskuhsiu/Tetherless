# Tetherless

An independently maintained, mobile-first iOS sideloading project focused on unattended renewal with a user's personal Apple account.

## Development contract

- Finish implementation, integration and all available non-device checks before asking the owner to connect an iPhone.
- Device-dependent checks are collected into one acceptance pass, never used as a reason to stop implementing unrelated work.
- Renewal is proactive (daily by default), not a job that waits until day seven. Accelerated test policies do not alter Apple's signed expiry dates.
- Automated tests, successful builds and real-device evidence are reported separately. Passing mocks is not proof of iOS background execution.
- Never request Apple passwords, 2FA codes, pairing records, private keys or device identifiers in GitHub issues or chat.

Status: implementation in progress; not a validated release. No real-device or Apple-account validation has been performed.

The implementation work will be proposed on a separate branch. Upstream sources and their licenses will be retained and pinned rather than silently tracking moving branches.
