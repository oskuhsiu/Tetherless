# One-run decision record

Fill in a project-local checkpoint before the next dispatch; never commit secrets.

- Source SHA / workflow / run attempt / job:
- Diagnosis report SHA-256 and first failed stage:
- Symptom fingerprint; same as previous? If yes, why is another full run justified?
- Observed evidence (exact log/result/trace, completeness, artifact digest):
- Root cause: unknown / hypothesis / confirmed; distinguish these explicitly.
- One hypothesis for this run:
- New evidence or discriminating code/configuration change:
- Expected observation that would support OR refute it:
- Acceptance assertions and data-preservation checks that remain unchanged:
- Fast checks already executed (not merely defined):
- Environment fingerprint; differences from the accepted baseline:
- Scope of execution (reuse only a matching tested artifact):
- New run ID after dispatch; do not dispatch if a relevant run is already active:
- Stop condition and exact next standalone action:

No new evidence or discriminating change means **do not repeat the full run**.
A filled form is not automated proof that a diagnosis is correct; review its evidence.
