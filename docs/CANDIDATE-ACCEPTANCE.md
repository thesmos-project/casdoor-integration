# Candidate distribution acceptance

Local maintainer review on 2026-10-06 by Codex, for evaluation distribution only.
This is not an independent security/legal review or production approval.

## Accepted scope

- Exact Casdoor v4.15.0 source revision and six ordered, hash-checked patch layers.
- Rebuilt frontend and Go backend with selected object/SCIM/certificate regressions
  and the LDAP package tests under the race detector; frontend typecheck/build.
- Byte-identical normal and inventory frontend builds, including CSS import/font evidence.
- Checked notices for 272 Go modules/toolchain entries, 190 frontend packages,
  94 Swagger dependencies and 18 installed system packages, with no coverage gaps.
- Nine corresponding Go source ZIPs for modules with MPL notices, and exact
  Alpine recipes, patches/configuration and checksum-verified source archives for
  all eleven system package source origins.
- LDAP dependency pinned to its author's MIT revision. Its parent is the previously
  pinned revision; only LICENSE changes, and every other file compares byte for byte.
- Original FreeType licence option and required attribution retained. Inter font
  OFL notice retained. Recovered licence evidence distinctions are documented in
  `DISTRIBUTION.md` and `licenses/overrides.json`.
- Actual-image checks for missing configuration refusal, served frontend, saved
  theme, theme persistence across restart, reserved-claim override rejection,
  nonroot execution, read-only filesystem and dropped capabilities.
- SPDX 2.3 inventory with 575 entries validated against the official JSON schema.
  Image publication signs/verifies it as a separate attestation so compiled
  browser dependencies are represented alongside BuildKit's automatic SBOM.
- Negative checks reject altered notices, missing covered source archives, changed
  accepted build inputs and registry authentication/network errors mistaken for
  an absent version tag. Stable publishing rejects RC versions.
- Publication scan found no protected fixture values or private checkout paths.

## Distribution limits

The local packaging fixture uses upstream demonstration bootstrap only in a
disposable SQLite database on loopback. Default bootstrap, MFA/recovery, full
deployment/protocol/upgrade/capacity acceptance, advisory review and independent
review remain production requirements. No production gate is closed by candidate
distribution acceptance. No commercial implementation or image is distributed.

Local checks and future publication builds remain subject to fresh CI checks. The manual publication job additionally requires the repository's
configured `release` environment owner approval. Publishing must sign and verify,
pull the immutable digest and pass the runtime checks before advertising a
verified artifact. A pushed image with a failed later check is unaccepted.

`release-policy.json` binds this scope to the current build-input fingerprint;
changed inputs require a new acceptance review. Upstream issues or PRs are never
opened automatically.
