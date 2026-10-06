# Casdoor integration for Thesmos

Deployment recipes and integration changes for using Casdoor with Thesmos.
Casdoor is developed by the [Casdoor project and its contributors](https://github.com/casdoor/casdoor).
This is an independently maintained integration project, without upstream endorsement.

## Status

Source candidate: six attributed patch layers and a complete backend/frontend
container builder are available for evaluation. No registry image or supported
production release has been published. Production acceptance remains in progress.
`upstream.lock.json` records the exact upstream revision and ordered patch checksums.

The planned integration covers Community OIDC, Enterprise SAML, SCIM provisioning
in either direction with an explicit authority per scope, and administrator
configuration of supported JWT claims. Arbitrary JWT scripts are not a promised
feature. Enterprise features require the appropriate Thesmos edition and licence.

## Maintenance and contributions

See [MAINTENANCE.md](MAINTENANCE.md). Contributions can be submitted to this
repository. Upstream contributions are manual: automation must never create an
issue, pull request, comment, or branch in the original Casdoor repository.

The reviewed Casdoor patch series is available in `patches/`. Private evaluation
history, credentials, customer data and commercial source are excluded.

## Planned container distribution

Registry settings belong in GitHub Actions variables and secrets, never source
files or image layers. **Publish integration image** is manual, with separate
candidate and stable channels. Candidate distribution has scoped acceptance in `release-policy.json`; stable
publishing remains blocked. The publication job requires the configured owner
review in the `release` environment.
Candidates require reviewed distribution, provenance and runtime evidence; stable
releases additionally require full production acceptance. See [registry setup](docs/REGISTRY.md).

The intended release includes a versioned image, matching build source, upstream
revision, patch checksums, dependency licences, an SBOM and signed provenance.
Deployments should pin the immutable image digest. Compose is the first planned
recipe; Kubernetes support requires separate acceptance.

## Build the candidate

Requires Git, Python 3, the authenticated GitHub CLI and Docker with Buildx.
The GitHub CLI reads public Alpine build recipes; it never creates upstream PRs.
The current target is Linux amd64.

```sh
python3 scripts/validate-project.py
python3 scripts/build-image.py
```

This fetches the pinned upstream revision, verifies its tag and every patch
checksum, applies all six layers, runs selected Go regressions under the race
detector, typechecks the frontend, and compiles both components. Go, Node,
Yarn and runtime base versions are recorded in `build.lock.json`. `os.lock.json`
records the exact installed system packages and Alpine source commits. The builder
retains checked backend/frontend/font/Swagger notices and corresponding system
package source archives in `/licenses`. See [distribution inventory](docs/DISTRIBUTION.md).

The output is the local image `casdoor-integration:candidate`. Prepared source,
logs and build metadata belong in ignored `.local/`. A changed existing source
export is refused; move it aside before preparing a different candidate.
This controls source/build inputs; it does not promise byte-identical images
while runtime package repositories can change. Distribution checks reject an
image whose installed system packages differ from the lock.

See [patch details](docs/PATCHES.md), [local component recipe](recipes/README.md)
and [remaining release requirements](docs/RELEASE-STATUS.md).

## Configuration

The intended image preserves Casdoor's supported administrator UI/API settings
for organization and application themes, clients, providers and claim mappings.
Server configuration and secrets are supplied at deployment. User settings must
survive restart and upgrade; bootstrap must not overwrite an existing deployment.
Media storage must be persistent and tested with the hardened runtime.
Changing frontend components can require rebuilding the frontend.

A shared PostgreSQL server may host both products, using separate databases and
roles. Sharing a server does not imply sharing identity or metadata tables.

## Licence and attribution

The original integration material in this repository is licensed under
[Apache License 2.0](LICENSE). Recipients may use, modify and redistribute it
subject to that licence. Casdoor and other dependencies retain their own
copyrights, licences and applicable notices. See [NOTICE](NOTICE).
