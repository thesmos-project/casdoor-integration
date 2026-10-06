# Casdoor integration for Thesmos

A patched Casdoor build and a local deployment recipe for use with Thesmos.
Casdoor is developed by the [Casdoor project and its contributors](https://github.com/casdoor/casdoor).
This integration is maintained independently and has no upstream endorsement.

## Current version

| Item | Value |
| --- | --- |
| Integration version | `v4.15.0-thesmos.1-rc.1` |
| Casdoor base | `v4.15.0`, commit `2301694036cbdcf932b3b1cbef02fb61d9820429` |
| Build target | `linux/amd64` |
| Available now | Source, six patches, container builder and local Compose recipe |
| Registry image | Publication pending; no verified image digest is available yet |
| Production support | Evaluation candidate; not approved for production |

See [release status and limitations](docs/RELEASE-STATUS.md).

## What this version provides

| Area | Casdoor capability and integration changes |
| --- | --- |
| Branding | Casdoor's organization/application theme and branding settings remain configurable through its administrator UI/API. |
| OIDC | Casdoor provides OIDC for application login, including the Community integration use case. The patches bind authorization-code exchange to its redirect URI and bind introspection/refresh to the authenticated application. |
| JWT claims | Casdoor's custom field mappings plus literal JSON attributes, protected protocol claims and validation before saving configuration. There is no JWT lambda or script runtime. |
| SAML | Casdoor provides SAML; the patches add an optional persistent NameID based on the user's ID. The Thesmos SAML use case requires Enterprise. |
| SCIM | Casdoor's SCIM server for Users/Groups and a remote-user import syncer. Fixes cover import-request lifetime, server filters/pagination, group external IDs and user active-state updates. The syncer cannot push users or import groups. |
| Container | Rebuilt Go backend and frontend, nonroot execution, required mounted configuration, dependency notices and corresponding source archives. |

Protocol support in the source does not certify every client or deployment.
SCIM authority and mappings must be configured for the chosen flow. Provisioning
from Casdoor into another system needs a separate provisioner; this repository
does not provide that component or automatic bidirectional synchronization. See [patch reasons and
behavior](docs/PATCHES.md) and [configuration examples](docs/CONFIGURATION.md).

## Build and try it locally

Requires Git, Python 3, authenticated GitHub CLI, and Docker with Buildx.
The GitHub CLI retrieves public Alpine source recipes. The builder verifies the
pinned source and patch checksums, runs selected Go regressions with the race
detector, typechecks the frontend, and builds both components.

```sh
python3 scripts/validate-project.py
python3 scripts/build-image.py
```

The output is `casdoor-integration:candidate`. Prepared source and build output
are stored in ignored `.local/`. Use the [local Compose instructions](recipes/README.md)
with a disposable PostgreSQL database. Keep the endpoint on loopback: the current
bootstrap still creates an administrator with upstream demonstration credentials.

A single PostgreSQL server can host Casdoor and Thesmos using separate databases
and restricted roles. Their identity and metadata tables remain separate. This
repository's recipe starts Casdoor only; it does not bundle Thesmos or Kubernetes.

## Documentation

- [Configuration: themes, claims, SAML and SCIM](docs/CONFIGURATION.md)
- [Why the patches exist](docs/PATCHES.md)
- [Version limitations](docs/RELEASE-STATUS.md)
- [Automated validation coverage](docs/VALIDATION.md)
- [Image sources, licences and notices](docs/DISTRIBUTION.md)
- [Maintaining and releasing this integration](MAINTENANCE.md)
- [Registry publishing and image verification](docs/REGISTRY.md)
- [Reporting security issues](SECURITY.md)

## Licence and attribution

Original integration material is licensed under [Apache License 2.0](LICENSE).
You may use, modify and redistribute it under that licence. Casdoor and all
other dependencies retain their own copyrights, licences and applicable notices;
see [NOTICE](NOTICE) and the [distribution contents](docs/DISTRIBUTION.md).
Contributions are welcome here. Upstream submissions require a manual maintainer
decision; automation does not open Casdoor issues or pull requests.
