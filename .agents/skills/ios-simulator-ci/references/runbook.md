# Simulator failure runbook

## Read the actual contract, not a remembered machine image

On the macOS runner record `uname -m`, `sw_vers`, `xcode-select -p`, `xcodebuild -version`, `xcodebuild -showsdks`, and the job's runner image version. Inspect `xcrun simctl help` and relevant subcommand help from that installed toolchain before using new flags. Save available runtime/device-type identifiers with `simctl list --json`; do not download or upgrade an SDK implicitly.

Inspect actual resolved package versions and the Simulator slices of binary dependencies (`file`, `lipo -info`, and their XCFramework Info.plist). ARM64 iPhoneOS and ARM64 iPhoneSimulator are not interchangeable. Do not treat successful unsigned device compilation as Simulator-link evidence. Use a concrete reviewed destination if a dependency cannot support a generic build's additional architecture.

For current repositories, retain existing bounded wrappers for subprocess calls rather than adding free-running commands. In a new repository, specify per-command deadlines, log retention limits, ownership and failure behavior before starting a long build. Keep declared limits unchanged until evidence justifies a specific change.

## Controlled device lifecycle

Allocate one fresh device from a verified installed runtime/type and persist ownership. Never run `simctl erase all`, global `killall`, or cleanup of a device identified only as `booted`. Compile before explicit boot where supported by the existing pipeline. Check boot state/readiness separately from screen availability. Use `simctl install` and `simctl launch` against the owned UUID, save their actual results, and confirm the process survives the smoke interval.

If installation or launch fails, preserve stderr/stdout and bounded installd/containermanagerd logs. If UI fails after launch, inspect the actual process/crash and test hierarchy before altering infrastructure. Log collection failure must not overwrite the original failure. Shutdown/delete only devices whose saved ownership still matches; a local developer's already-running device is not disposable.

## UI-specific evidence

Keep locale/fixture identifiers stable. Match a semantic element inside the intended container, distinguish `exists`, `enabled` and `hittable`, and inspect the actual view hierarchy when they disagree. Decorative descendants are not automatically activation targets. Avoid unbounded swipes and fixed pixel taps. If the correct single action yields no outcome, inspect native delegate/request/dismissal/IO boundaries instead of changing the action repeatedly.

For system pickers, distinguish type-policy acceptance, Files-provider availability, selection delivery, request lifetime, dismissal completion, coordinated reading and persistent mutation. A diagnostic trace must have completeness/truncation information; no marker in a partial scan is not proof of no callback. Use fixed zero-payload event identifiers. No filenames, credentials, pairing material or raw server responses belong in published diagnostics.

Do not warm up the picker, synthesize a successful delegate response, substitute an app-owned Cancel button, or skip original-file preservation merely to pass a CI run. A selected invalid document should be rejected by the production parser, with the visible result and unchanged source independently verified.

## Evidence hierarchy

Source contract/syntax tests < compiled unit tests < Simulator install/launch < actual UI assertions. Each proves only its own scope; these are not interchangeable acceptance levels. Keep immutable SHA/run/attempt/job IDs and artifact digest. The same SHA's cancelled run is not a failed product, and a green cleanup step cannot erase the earlier test failure.

## Primary references checked 2026-10-04

- Apple Xcode command-line tool reference: https://developer.apple.com/documentation/xcode/xcode-command-line-tool-reference
- GitHub hosted-runner reference (labels/architectures are subject to change): https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- GitHub runner-image inventory (inspect the exact image used, not main as a pin): https://github.com/actions/runner-images
- Agent skill manifest/discovery reference: https://developers.openai.com/codex/skills/

The operational retry limits and decision gate are this skill's engineering policy, not guarantees made by Apple or GitHub. Do not promise that a skill can eliminate infrastructure failures.
