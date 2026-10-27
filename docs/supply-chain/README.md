# Candidate dependency and rights inventory

This review describes the pinned dependency graph at Tetherless baseline `3dd8641e84698b97f96d53a6c53ed8c6ca4675bd`, checked 2026-10-05. It is not the final binary SBOM or distribution clearance. New candidate builds must reconcile their actual graph and artifacts against these records.

Read [REPORT.md](REPORT.md) for source-linked findings, reachable dependencies, specific unresolved gates and closure options. [inventory.json](inventory.json) has 32 source/binary component records; [candidate-sbom.spdx.json](candidate-sbom.spdx.json) is the candidate source graph. [THIRD_PARTY_NOTICES.draft.md](THIRD_PARTY_NOTICES.draft.md) and `licenses/` preserve collected attribution and unmodified texts. Per-crate and final linked-component notices are not complete. The report references a larger read-only evidence collection; the compact checked-in review intentionally preserves the original source URLs and pins without copying every upstream source tree or connector response.

[review-file-hashes.json](review-file-hashes.json) identifies the copied review artifacts and license texts. The full source evidence was independently Git-blob-verified during the review; these local hashes preserve the review copies, not binary publisher trust.

[The draft binary-admission policy](binary-admission-policy.draft.json) is documentation only, not installed configuration. No empty allowlist or silent authentication disablement is introduced. Essential ADI provenance/use basis and exact Unicorn combined-license basis remain unresolved; matching release digests alone does not close them. BASE-02 stays open.

Tetherless is an independent SideStore derivative, not an official SideStore release. The repository's original code declares AGPL-3.0-only; the root LICENSE supplies the full AGPLv3 text without changing any third-party grant. External LocalDevVPN and StikPair texts are retained as review references and are not assertions that their code is included or generally licensed as MIT.
