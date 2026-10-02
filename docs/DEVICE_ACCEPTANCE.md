# Consolidated device acceptance — NOT requested yet

Start this only after the native implementation and available CI gates pass. The developer must deliver the integrated build, exact source revision, bootstrap instructions and diagnostics together. Do not request credentials or pairing material in chat/GitHub.

## One-time setup

Use a dedicated test Apple Account. User enters login and 2FA locally, confirms required system permissions, and authorizes the automation. Record OS/build and nonsecret configuration locally. Complete a manual baseline installation and a locked-screen automation self-check. No debugger stays attached for unattended observations.

## Early renewal check

Schedule a next-day renewal (or an accelerated interval in a clearly identified test build). Do not open the manager or manually invoke refresh during the observation window. Verify the actual target/profile binding and expiry advancing, not merely a changed on-screen countdown. Include manager and app extensions. Preserve app data and signing identity.

## Consolidated failure checks

Exercise unavailable network then recovery, duplicate triggers, cancelled execution, restart followed by first unlock, VPN conflict, expired session/2FA requirement, write failure, partially applied profile batch and explicit certificate rotation. Automatic work must never revoke unrelated certificates or turn off a user's VPN. A necessary interactive repair must be reported honestly and must not be called an unattended success.

## Longer validation

Continue daily observations across the original signed expiry date and a separate longer soak. Opening the manager to inspect state changes the experiment; collect evidence without doing that, or mark the run as assisted. Real-time observation does not block coding or the early renewal test.

## Result classification

Record separately: build passed; action triggered; Apple authorization obtained; profile install acknowledged; device readback matched; app launched; no foreground intervention. Missing stages cannot be inferred from earlier stages. Failed/unsupported conditions require explicit recovery guidance, not a blanket reliability guarantee.
