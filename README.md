# Casdoor integration for Thesmos

Deployment recipes and integration changes for using Casdoor with Thesmos.
Casdoor is developed by the [Casdoor project and its contributors](https://github.com/casdoor/casdoor).
This is an independently maintained integration project, without upstream endorsement.

## Status

Initial project scaffold. No patches, container images, or production deployment
recipes have been released from this repository. Production acceptance is still
in progress in a separate private evaluation workspace. The upstream reference
in `upstream.lock.json` identifies the evaluated source, not a supported release.

The planned integration covers Community OIDC, Enterprise SAML, SCIM provisioning
in either direction with an explicit authority per scope, and administrator
configuration of supported JWT claims. Arbitrary JWT scripts are not a promised
feature. Enterprise features require the appropriate Thesmos edition and licence.

## Maintenance and contributions

See [MAINTENANCE.md](MAINTENANCE.md). Contributions can be submitted to this
repository. Upstream contributions are manual: automation must never create an
issue, pull request, comment, or branch in the original Casdoor repository.

Our distributable integration source will be published here after review.
Private evaluation history, credentials, customer data and commercial source
are excluded from publication.

## Planned container distribution

A registry and repository path will be selected by the project owner. Registry
credentials belong in GitHub Actions secrets, never source files or image layers.
There is currently no image publishing workflow.

The intended release includes a versioned image, matching build source, upstream
revision, patch checksums, dependency licences, an SBOM and signed provenance.
Deployments should pin the immutable image digest. Compose is the first planned
recipe; Kubernetes support requires separate acceptance.

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
