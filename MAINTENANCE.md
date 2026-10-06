# Maintaining the integration

## Upstream alignment

1. Pin a Casdoor release tag and exact commit in `upstream.lock.json`.
2. Keep the patches ordered with checksums and document each reason in
   [PATCHES.md](docs/PATCHES.md).
3. Evaluate upstream updates in a branch of this repository. Resolve patch
   conflicts and review behavior even when the series applies cleanly.
4. Check protocol behavior, tenant boundaries, claim/theme configuration,
   database migrations, upgrades, key rotation and recovery.
5. Remove a patch once its upstream equivalent has been verified.

Source provenance must connect the Casdoor revision, patch series, toolchain,
dependency inventory and final image digest. Contributors may submit patches
here under the repository's licence while preserving upstream notices.

## Upstream contributions

Contributions to the original Casdoor repository require an explicit manual
maintainer decision. Automation must not open upstream issues or pull requests,
post comments, push branches or submit security reports. Update automation may
propose changes in this integration repository but must not automatically merge
or release them. Security-sensitive changes require publication review and,
where applicable, coordinated disclosure.

## Release procedure

1. Update source/build locks, patch documentation and version limitations.
2. Build and run the relevant checks. Review source provenance, dependency
   notices and sources, and the runtime reports.
3. Record the selected channel's acceptance in `release-policy.json`, including
   a truthful reviewer, evidence and the exact reviewed input fingerprint:

   ```sh
   python3 scripts/validate-project.py --print-inputs-sha256
   ```

   A fingerprint identifies inputs; it does not replace review. Changed inputs
   require renewed acceptance. Candidate distribution requires its three gates;
   stable publication requires every production gate and production approval.
4. Validate the selected channel:

   ```sh
   python3 scripts/validate-project.py --candidate
   # For an accepted stable version, use --release instead.
   ```

5. Require successful CI for the source revision. Configure the
   [registry settings](docs/REGISTRY.md) and manually dispatch publication from
   `main`. Preserve the `release` environment's required maintainer review,
   restriction to `main` and disabled administrator bypass.
6. Announce a digest only after publication, signature/attestation verification
   and pulled-image runtime checks succeed. Retain matching source, notices,
   SBOM/provenance and release notes. Candidate availability does not establish
   production support.

RC versions use the candidate channel and retain production approval `false`.
Stable versions have no RC suffix and require full production acceptance.
[The release status](docs/RELEASE-STATUS.md) describes the current version's limits.

## Configuration and contributions

Use Casdoor UI/API settings for supported branding and identity configuration.
Keep deployment-specific users, secrets, domains and signing keys out of the
image. Changes must preserve administrator settings across restart, upgrade and
recovery; persistent storage must work with the runtime restrictions.

Publish implementation, usable instructions, patch rationale and reproducible
validation scope. Keep investigation journals, deployment troubleshooting,
credentials, fixture dumps and commercial source out of public documentation.
Retain original third-party licence evidence even when it is embedded in a README.
