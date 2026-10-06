# Web bootstrap verification

Verified 2026-10-06 UTC with Node 24.19.0 and npm 11.9.0.

- `npm test`: 47 passed, 0 failed
- `npm run build`: passed, including pinned WASM and patched metadata-adapter hashes
- Independent review repeated the 47 tests/build and reconciled source hashes
- Actual public worker executed through a VM/shim with real WORKERFS/WASM signing
  and project-subpath asset URLs; this was not a browser test
- Actual WASM version/sign/archive ran with a generated self-signed fixture P12,
  CMS profile and synthetic Mach-O input; this proves runtime execution/output,
  not Apple trust or an installable iPhone app
- DOM-emulated UI/API tests use mocked network/worker responses where labeled;
  they verify state/cancellation/consent/return behavior, not Apple services
- Metadata tests check exact profile binding, ordinary ZIP limits, binary plist
  traversal/depth budgets and known Tetherless App Group identity derivation
- `npm audit --omit=dev`: one unpatched high node-forge verification advisory;
  no clean security-audit claim (see THIRD_PARTY_NOTICES.md)

Not passed or not run:

- Chromium Playwright acceptance could not start: local IPC sockets were blocked,
  including after an approved execution escalation
- Cloud browser localhost navigation was blocked; no alternate restriction bypass
  was attempted
- The included browser suite, visual mobile QA, actual WebKit/Safari behavior,
  real Apple login/2FA/provisioning, iOS profile collection, first installation,
  native identity takeover and self-signing remain acceptance gates

This is an isolated candidate. It does not change native App code, native CI,
repository branch references, Pages settings, a public release or deployed services.
The free Personal Team clean-phone BOOT-01 outcome remains incomplete.
