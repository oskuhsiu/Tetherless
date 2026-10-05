# One-run decision — distinguish uncertain install outcome from lost diagnostics

- Current product/test baseline: 8c25ff3b984cd08401b4491aa0876ff0129161e6.
- Observed run / attempt / job: 37242839315 / 1 / 111554802378.
- First failure: install_launch, step 8, a 120-second simctl install timeout.
- Report SHA-256: 4b10b0db99b2afbf39295b91bb2b5c13bd4fa65169f52dcf8d0b2062bb2fad0e.
- Artifact: 11318286484, SHA-256 dc10213d482dbc643681f7c698bb2ef1ab03fafbe711bc9930a512411fb13048.

## Evidence and uncertainty

The actual job passed build/signature/boot/screenshot. It did not execute either recipient's document picker: those steps were skipped after the install timeout. The retained generic service log omitted 375,462 bytes of its middle and mostly mixed container initialization with installer work. Its absence of a product-specific completion is not conclusive. No supported root-cause finding justifies a product permission change, new tap target, global reset or longer timeout.

One question to discriminate: after the client command times out, is the product container registered, or is even a read-only product lookup unavailable? A returned container is only a partial-state observation, not complete-install or launch acceptance. Separately retain installer/LaunchServices events and product-specific events rather than obscuring them inside the generic container log.

## Single change and preserved conditions

In the existing failure-diagnostic helper, add three bounded read-only queries after validating current SHA/owner/device/product. Run them before generic host queries so the three-minute log window is useful. Keep the existing 15-second/256-KiB capture limits and each query's exit/timeout/truncation metadata. Never rewrite smoke results. Invalid bindings record a gap and preserve generic diagnosis.

The next code commit may trigger one full workflow with these observations. There is no automatic rerun. Existing runner/toolchain selection, concrete device, signing, boot ordering, 120-second installation bound and all product/control UI tests remain byte-identical. The comparison is still failure-only and cannot pass the original product assertion. No new permissions or successful backend fixture.

## Fast verification and stopping rule

8 new focused tests, 23 existing Simulator tests and 16 skill tests passed locally. The selector also consumed this actual failed artifact's identities without executing remote commands. simctl itself was not run in the Linux environment. Before publication, check current head and any related active run.

If another timeout occurs, inspect focused logs/readback before any further change; query failure or truncated logs are incomplete evidence, not root cause. If it reaches UI, inspect the original product result and independent control; success does not retroactively explain this timeout. Save the new run ID once, then use a separate verification turn rather than polling or adding another long feature.

Primary reference for separating simctl installation/launch and collecting failure diagnostics: https://developer.apple.com/videos/play/wwdc2019/418/ . The bounded diagnostic policy is project-specific; Apple does not identify this particular timeout's cause there.
