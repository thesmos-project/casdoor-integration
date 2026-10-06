# Maintenance and release policy

## Upstream alignment

1. Pin each candidate to an exact Casdoor commit and record its release tag.
2. Maintain an ordered patch series with checksums and a reason for each patch.
3. Evaluate upstream releases and security fixes in an update branch here.
4. Resolve conflicts explicitly. A clean patch application alone is insufficient.
5. Verify protocol behavior, tenant boundaries, supported customization,
   database migrations, upgrades, key rotation and recovery before promotion.
6. Remove a patch when the equivalent upstream change has been verified.

Release metadata must connect the source revision, patch series, toolchain,
frontend, dependency inventory and final image digest. The published builder must
reproduce every accepted patch layer, including the frontend. A GitHub fork can
be introduced later; it does not replace update review or integration tests.

## Upstream interaction

All upstream contributions are manual and require an explicit maintainer decision.
No automation may open issues or PRs, post comments, push branches, or submit
security findings to the original Casdoor repository. Any future update bot may
propose changes only in this integration repository. Do not automatically merge
or release those changes.

Security findings and unreleased security-sensitive patches require publication
review and, where applicable, coordinated disclosure before public inclusion.

## Registry setup

Once the complete build is accepted, the owner supplies:

- `REGISTRY_URL`: registry host, optionally including its port, without a URL scheme.
- `REGISTRY_IMAGE`: full image repository path, including the registry host.
- `REGISTRY_USERNAME`: registry login identity, stored as an Actions secret.
- `REGISTRY_PASSWORD`: registry token or password, stored as an Actions secret.

Use Actions variables for the two non-secret values and Actions secrets for the
credentials. Prefer a dedicated account/token with the minimum required access.
If the registry supports federation, short-lived credentials are preferable.
Never copy credentials into build arguments, Dockerfiles, generated images or
public build logs. Pull-request builds must not receive publishing credentials.

The initial publishing workflow should require a manual dispatch through a
protected GitHub environment named `release`. Registry credentials do not by
themselves approve a release. Publish only an accepted source revision and retain
its digest, SBOM, provenance and release notes. The immutable digest is the
supported deployment reference; a mutable tag is only a convenience.

## Customization contract

Keep deployment-specific users, passwords, domains, signing keys and themes out
of the distributable image. Prefer upstream UI/API configuration for ordinary
branding. Initial provisioning must not reset later administrator changes.
Custom HTML and other powerful settings require trusted administrator access.
Persistent files and object storage need acceptance with read-only runtime
controls. Test customization persistence during restart, upgrade and recovery.

## Publication boundary

Publish reviewed Casdoor patches, original integration code, builders and
sanitized recipes. Do not copy the private evaluation repository wholesale.
Commercial Thesmos source or images, credentials, keys, fixture dumps, private
reports and deployment-specific identifiers are excluded. An initial scaffold
or successful local test does not establish production readiness.
