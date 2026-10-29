# Verify or publish an image

The first section shows how to check that an image comes from this repository's
publishing workflow. The rest is for maintainers who publish new versions.
Building locally needs no registry account.

## Verify a published image

You need cosign 3.0.2 or later. The publishing workflow signs with cosign 3,
which stores the signature and SBOM attestation in the Sigstore bundle format,
attached to the image. cosign 2 does not read that format and reports
`no signatures found` even for a correctly signed image.

Use the complete image repository and immutable `sha256:` digest. For the current
release, set:

```sh
IMAGE_REPOSITORY=registry.thesmos.dev/thesmos/casdoor
IMAGE_DIGEST=sha256:8616a2521c1aa1ed90fa612200fee598a40fe058ded14fb7bd9b2cb5a597a6a3
```

Then run:

```sh
cosign verify \
  --certificate-identity 'https://github.com/thesmos-project/casdoor-integration/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  "$IMAGE_REPOSITORY@$IMAGE_DIGEST"

cosign verify-attestation --type spdxjson \
  --certificate-identity 'https://github.com/thesmos-project/casdoor-integration/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  "$IMAGE_REPOSITORY@$IMAGE_DIGEST"
```

Without a local cosign, run the same checks from cosign's own image, pinned by
digest:

```sh
COSIGN_IMAGE=gcr.io/projectsigstore/cosign:v3.0.3@sha256:774391ac9f0c137ee419ce56522df5fd3b1f52be90c5b77e97f7c053bdd67a67

docker run --rm "$COSIGN_IMAGE" verify \
  --certificate-identity 'https://github.com/thesmos-project/casdoor-integration/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  "$IMAGE_REPOSITORY@$IMAGE_DIGEST"

docker run --rm "$COSIGN_IMAGE" verify-attestation --type spdxjson \
  --certificate-identity 'https://github.com/thesmos-project/casdoor-integration/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  "$IMAGE_REPOSITORY@$IMAGE_DIGEST"
```

The [published image check](../.github/workflows/verify-published.yml) runs
these checks with cosign 3.0.2 against the digest in the README every week.

A verified signature identifies the publishing workflow. Check the source
revision and release channel as well: release candidates (`-rc.N`) are
pre-release builds, and stable versions have no suffix. See the
[release notes](RELEASE-NOTES.md).

## Maintainer settings

Configure GitHub Actions variables and secrets:

| Name | Kind | Value |
| --- | --- | --- |
| `REGISTRY_URL` | Variable | Upload registry hostname, optionally with port; no URL scheme. |
| `REGISTRY_IMAGE` | Variable | Image name, namespace/name or full repository path on that host; no tag. |
| `PUBLIC_REGISTRY_URL` | Optional variable | Anonymous read-only mirror hostname, using the same repository path. |
| `REGISTRY_USERNAME` | Secret | Account authorized to upload to that image repository. |
| `REGISTRY_PASSWORD` | Secret | Registry token or password. |

Organization settings must grant this repository access. Repository and
`release` environment settings can override inherited values. Keep credentials
out of source files, build arguments, image layers and public logs. Use a
repository-scoped registry account where supported.

Run **Actions → Check registry access → Run workflow** on `main` to check settings
and credentials. For Basic-auth registries it creates an empty authenticated blob
upload and immediately cancels that same upload. It publishes no image manifest.
A successful Docker login alone does not prove write access when anonymous reads
are enabled. The probe rejects redirects and unexpected cancellation locations;
Bearer-token registries require a separate upload-probe implementation.
The standalone check uses organization/repository settings, not release-environment
overrides.

The registry must support the image manifests, SBOM/provenance attestations and
Cosign signatures, and be reachable over trusted HTTPS from the runner. The
upload probe does not establish support for every manifest/attestation type.

## Separate upload origin and public mirror

Upload and sign at the authenticated origin. Set `PUBLIC_REGISTRY_URL` only when
consumers should pull anonymously through a separate mirror. The repository path
must match the mirror's synchronization selection.

For Zot mirrors, configure `preserveDigest: true` on the matching upstream sync
entry and retain `http.compat: ["docker2s2"]`. The
[Zot mirroring guide](https://zotregistry.dev/latest/articles/mirroring/) documents
digest, signature and referrer preservation. Configure upstream connectivity and
credentials for your deployment and confirm support in its Zot version.

The publisher signs at the origin, then uses an empty Docker credential
configuration to pull the public tag and exact origin digest. It verifies both
the image signature and SPDX attestation and runs the smoke test through the
mirror. It advertises the public reference only after all checks pass.

## Publish a version

Follow [the release procedure](../MAINTENANCE.md#release-procedure). Run
**Actions → Publish integration image → Run workflow** on `main` with the accepted
`candidate` or `stable` channel, then obtain the required `release` environment
review. Candidate publishing requires an RC version; stable publishing requires
a non-RC version and full production acceptance.

The workflow builds/tests the image, checks its notices and runtime, refuses an
existing version tag, pushes, signs and verifies the digest, and tests the pulled
artifact. A failed post-push step leaves an unaccepted artifact that must not be
advertised as verified. The workflow publishes no `latest` tag and does not run
automatically on source pushes.
