# Registry setup

The project owner can configure the destination without changing the builder.
No registry credentials are needed to inspect patches or build the image locally.

In GitHub **Settings → Environments → release**, configure:

| Name | Kind | Value |
| --- | --- | --- |
| `REGISTRY_URL` | Environment variable | Registry hostname, optionally with port; no `https://` prefix |
| `REGISTRY_IMAGE` | Environment variable | Full repository path including that hostname, without a tag |
| `REGISTRY_USERNAME` | Environment secret | Registry login identity |
| `REGISTRY_PASSWORD` | Environment secret | Registry token or password |

The project environment is configured to require owner review, restrict deployment
to `main`, and disable administrator bypass. Preserve these protections. Use a
registry token scoped to this image repository where the registry permits it.
The registry must support OCI manifests, SBOM/provenance attestations and Cosign
signatures, and be reachable with trusted HTTPS from the Actions runner.

After production/publication acceptance is recorded, manually run **Actions →
Publish accepted image → Run workflow**, selecting `main`. It validates acceptance,
prepares exact source, reruns the container build and tests, publishes the version
from `build.lock.json`, attaches SBOM/provenance, signs the immutable digest with
GitHub OIDC, and verifies that signature. Pull and test the returned digest in the
supported deployment before announcing it. There is no automatic upstream PR,
registry publishing on push, or `latest` tag.

Credentials go only to the registry login action. They are not build arguments.
The workflow does not need permission to write to the original Casdoor repository.

To verify a released image, use the full digest from its release evidence:

```sh
cosign verify \
  --certificate-identity 'https://github.com/thesmos-project/casdoor-integration/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  "$REGISTRY_IMAGE@$IMAGE_DIGEST"
```

A verified signature identifies the publishing workflow. It does not by itself
establish production security or protocol compatibility.
