# Device-last implementation sequence

This updates the v1.0 planning sequence to the owner's 2026-10-02 instruction: finish code and all available non-device verification first. Missing device evidence is a final acceptance item, not permission to stop implementing modules.

## Architecture decision

Use a pinned SideStore native baseline plus independently tested renewal logic. Do not rewrite Apple authentication or signing cryptography. Keep reviewed transformations outside Vendor so upstream updates remain auditable. A prepared tree is disposable; do not develop in it or publish it as an official SideStore build.

## Work packages

| Package | Completion evidence before device handoff |
|---|---|
| Core policy, coordinator, journal | Debug/Release tests, faults, real filesystem and cross-process exclusion |
| Native profile-only adapter | Actual API integration and fixtures for signed-profile parsing/binding; no `return success` stubs; batch recovery tests |
| Unattended entry point | App Intent calls the same coordinator without `openAppWhenRun`, foreground continuation, detached mutation or fabricated success; cancellation tests |
| Authentication and onboarding | Existing native login and user verification; safe session repair; local Anisette and pairing setup; no passwords in CI |
| Installation and self-update | Existing signing/install path, explicit identity-change flow, manager-first renewal, durable recovery; no automatic revocation |
| Background and alerts | Early retry opportunities, bounded backoff, actual deadline-aware alerts; OS scheduling not represented as a guaranteed timer |
| UI and diagnostics | Installed apps, effective expiry, evidence level, setup/repair, export without account/device secrets |
| Build and supply chain | Locked source/dependencies, unsigned native builds, simulator tests where meaningful, reproducible build instructions and third-party notices |
| Device acceptance | Run only after preceding implementation gates, using the consolidated procedure |

## Development tests are not seven-day waits

Use injected clocks and backends for policy/fault tests, and a two-hour eligible interval for accelerated native testing. Real automatic renewal can be evaluated the next day by comparing actual installed profiles. Keep a longer real-time soak as a separate release measure; never change the device clock to fake Apple expiry.

## No-go behaviors

Never reinterpret a reminder as automatic renewal, a cached database date as device evidence, a missing readback as 'not applied', or a failed gate as complete. Do not replace unavailable native behavior with a mock backend in production. A device is not requested until there is a coherent integrated candidate to test.
