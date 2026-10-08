# Release notes

| Item | Value |
| --- | --- |
| Version | `v4.15.0-thesmos.2` |
| Based on | Casdoor `v4.15.0` with [eight patches](PATCHES.md) |
| Platform | `linux/amd64` |
| Image | `registry.thesmos.dev/thesmos/casdoor@sha256:fcb88561aa8aa4080fbc18a307e509ee4f1bc3901ddbee5cc56492bb05dce003` |
| Recipes | [Compose](../recipes/compose/README.md), with an optional Caddy HTTPS proxy; [Kubernetes](../recipes/kubernetes/README.md), with a k3s overlay |

## v4.15.0-thesmos.2

- **Kubernetes recipe.** Manifests for any cluster, an overlay for k3s with
  Traefik, Let's Encrypt certificates renewed automatically by cert-manager, and
  an automated test on k3s.
- **`sessionCookieSecure` option.** Casdoor marks its cookies `Secure` behind an
  HTTPS proxy or Ingress. The Kubernetes recipe and the Compose HTTPS overlay set
  it. See [server configuration](CONFIGURATION.md#server-configuration-and-persistence).
- **Compose files moved to `recipes/compose/`.** Update your commands, for
  example `docker compose -f recipes/compose/compose.yaml up -d`. The
  configuration folder `.local/deployment` and the volumes stay the same.

## v4.15.0-thesmos.1

- **Exact redirect hosts.** A redirect URI registered as a full URL matches only
  its own host; see [upgrading from upstream Casdoor](#upgrading-from-upstream-casdoor).
- **SSH host keys for database syncers.** A syncer that uses an SSH tunnel needs
  its **SSH host key** before it connects again. See
  [database syncers through an SSH tunnel](CONFIGURATION.md#database-syncers-through-an-ssh-tunnel).
- **Coraza 3.8.1** for Casdoor's web application firewall rules.
- **Compose project renamed `casdoor-integration`.** To keep the volumes of a
  deployment started from a release candidate, set
  `COMPOSE_PROJECT_NAME=casdoor-integration-evaluation` when you run Compose.

## Upgrading from upstream Casdoor

These behaviors differ from Casdoor `v4.15.0`. Test them against your
deployment before you switch.

| Area | What changes | What to do |
| --- | --- | --- |
| Redirect URIs | A redirect URI registered as a full URL, such as `https://app.example.com/callback`, no longer accepts subdomains such as `https://evil.app.example.com/callback`. | Register each callback URL, or use a pattern without a scheme, such as `.example.com`, when subdomains are intended. |
| Authorization codes | The code exchange must send the same redirect URI that started the sign-in. | Check clients that change the redirect URI between the two requests. |
| Introspection | A token is reported active only to the client it was issued to; other clients receive `active: false`. | Let an API verify JWT signatures, or introspect with the issuing client's credentials. |
| Refresh tokens | Custom refresh tokens no longer carry the application's custom claims. | Check clients that read those claims from a refresh token. |
| JWT claims | Saving an application rejects claims Casdoor could not read back, such as role names under `roles`. An initialization file with such a claim stops startup when `initDataNewOnly=false`. | Rename such claims, for example to `role_names`. |
| SCIM `PUT` | A replacement keeps administrator status, MFA, linked providers, groups and properties, and keeps a disabled account disabled unless the request sets `active`. | Send `active` to change whether the account is enabled. |
| Retained signing keys | When enabled, incoming JWTs need an authorized `kid`; older refresh tokens without one require signing in again. | See [JWT signing-key overlap](CONFIGURATION.md#jwt-signing-key-overlap). |
| SAML NameID | Enabling the persistent NameID changes the subject that service providers see. | Enable it before accounts are linked, or relink them. |
| Startup | A new database needs the administrator password file, and unsafe settings stop startup. | See [secure startup](CONFIGURATION.md#initial-administrator-and-secure-startup). |
| Database syncers over SSH | A syncer needs the SSH host key of its server. | Set **SSH host key** on each such syncer. |

## Limits

- JSON JWT claims, the persistent SAML NameID and retained signing keys are set
  through the application API; the administrator UI has no fields for them.
- JWT claims come from field mappings and fixed values; claims cannot run
  scripts.
- SCIM filters support the equality lookups listed in
  [lookup fields](CONFIGURATION.md#lookup-fields).
- Casdoor's built-in SCIM syncer imports remote users only. To sync in both
  directions, use a separate provisioner, decide which directory owns each set
  of users and groups, and prevent update loops.
- Application-specific JWKS publishes only the current signing key, and SAML
  certificates have no rollover.
- Run one Casdoor instance per database. Casdoor keeps captchas, firewall rules
  and syncer schedules in each process, so a second instance causes failed
  captchas, stale rules and duplicate imports; see
  [storage and scaling](../recipes/kubernetes/README.md#storage-and-scaling).
  Scale with the CPU limit.
- [Measured capacity](VALIDATION.md#measured-capacity) applies to the recipe
  limits on the test host; raise the CPU limit for higher sign-in rates.
- Thesmos Enterprise features need that edition and its licence; this repository
  contains no Enterprise code or image.

## Release acceptance

This release passed the [security review](SECURITY-REVIEW.md), the licence and
source coverage check of the [image contents](DISTRIBUTION.md), and the
[automated tests](VALIDATION.md): secure startup, MFA and recovery, upgrade,
rollback, key rotation, backup restore, HTTPS, Kubernetes on k3s and capacity.
OIDC, SAML and SCIM were tested with Thesmos over TLS. The project maintainers
accepted the release; [release-policy.json](../release-policy.json) records the
acceptance and the exact build inputs. [Maintenance](../MAINTENANCE.md)
describes the release process.
