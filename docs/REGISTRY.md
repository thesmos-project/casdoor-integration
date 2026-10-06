# Registry setup

The project owner can configure the destination without changing the builder.
No registry credentials are needed to inspect patches or build the image locally.

Organization and repository settings are supported; there is no need to copy
organization credentials into repository secrets. Configure these names:

| Name | Kind | Value |
| --- | --- | --- |
| `REGISTRY_URL` | Actions variable | Registry hostname, optionally with port; no `https://` prefix |
| `REGISTRY_IMAGE` | Actions variable | Image name such as `casdoor`, namespace/name, or full repository path; no tag |
| `PUBLIC_REGISTRY_URL` | Optional Actions variable | Anonymous consumer mirror hostname; uses the same repository path |
| `REGISTRY_USERNAME` | Actions secret | Registry login identity |
| `REGISTRY_PASSWORD` | Actions secret | Registry token or password |

For example, a repository image name of `casdoor` is prefixed with your configured
registry hostname. Organization settings must grant this repository access. A
`release` environment setting can override the inherited organization/repository
value; leave it unset when sharing organization credentials.

Run **Actions → Check registry access → Run workflow** on `main` to verify
organization/repository settings and registry login. It does not push an image or
publish an image manifest. For a Basic-auth registry it also creates an empty,
authenticated blob upload and immediately cancels that same upload. This checks
upload access, not acceptance of every image/attestation manifest type. The check
refuses redirects and unexpected cancellation locations. Bearer-token registries
need a separate permission-check implementation. It does not use any `release`
environment overrides.

A registry that permits anonymous reads can report a successful Docker login
without proving the supplied account can upload. Check the account's push rights
for the normalized `REGISTRY_IMAGE` path. A failed upload probe occurs before the
publication workflow spends time building the image.

## Separate upload origin and public mirror

When a public registry is a read-only mirror, upload to the authenticated origin.
The repository's Zot deployment uses these repository-level variable overrides:

| Variable | Value |
| --- | --- |
| `REGISTRY_URL` | `customers.thesmos.dev` |
| `REGISTRY_IMAGE` | `thesmos/casdoor` |
| `PUBLIC_REGISTRY_URL` | `registry.thesmos.dev` |

The organization-wide settings are retained. The inherited credentials must
identify the origin's authorized CI account. The image path matches the public
mirror's `thesmos/**` sync selection. Do not upload to the read-only mirror or
enable anonymous writes there.

In the mirror configuration, set `preserveDigest` on the upstream sync entry:

```json
{
  "urls": ["http://zot:5000"],
  "tlsVerify": false,
  "onDemand": true,
  "pollInterval": "1h",
  "preserveDigest": true,
  "content": [{ "prefix": "thesmos/**" }]
}
```

Keep the mirror's existing `http.compat: ["docker2s2"]`, credential-file setting
and private upstream connectivity. This fragment replaces only one registry
entry; it is not a complete Zot configuration. Verify that the deployed Zot
version supports these settings before applying them.
[Zot's mirroring guide](https://zotregistry.dev/latest/articles/mirroring/)
documents digest/signature/referrer preservation.

After signing at the origin, the publication workflow uses an empty Docker
credential configuration to pull the mirror tag and exact origin digest, verify
the image signature and SPDX attestation, and test the pulled image. A missing
digest or signed artifact fails publication acceptance. The final consumer
reference uses the public mirror only after those checks succeed.

The project environment is configured to require owner review, restrict deployment
to `main`, and disable administrator bypass. Preserve these protections. Use a
registry token scoped to this image repository where the registry permits it.
The registry must support OCI manifests, SBOM/provenance attestations and Cosign
signatures, and be reachable with trusted HTTPS from the Actions runner.

After the selected channel's acceptance is recorded, manually run **Actions →
Publish integration image → Run workflow**, selecting `main` and a channel.
`candidate` requires an RC version and distribution/provenance/runtime acceptance;
its production label remains `false`. `stable` requires a non-RC version and
every production acceptance gate. It validates acceptance,
prepares exact source, reruns the container build and tests, publishes the version
from `build.lock.json`, checks actual image notices/sources and the configurable
runtime before pushing, attaches SBOM/provenance, signs the immutable digest with
GitHub OIDC, verifies that signature, then pulls and smoke tests that digest.
Test the returned digest in the supported deployment before announcing it.
A failed post-push check leaves an unaccepted artifact that must not be advertised.
There is no automatic upstream PR,
registry publishing on push, or `latest` tag.

Credentials go only to the registry login action and the direct upload check.
They are not build arguments, and the upload check does not print their values.
The workflow does not need permission to write to the original Casdoor repository.

To verify a released image, set `IMAGE_REPOSITORY` to its complete registry path
and use the full digest from its release evidence:

```sh
cosign verify \
  --certificate-identity 'https://github.com/thesmos-project/casdoor-integration/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  "$IMAGE_REPOSITORY@$IMAGE_DIGEST"
```

A verified signature identifies the publishing workflow. It does not by itself
establish production security or protocol compatibility.
