# Release notes and limits

| Item | Status |
| --- | --- |
| Version | `v4.15.0-thesmos.1` |
| Source | Casdoor `v4.15.0` plus the [eight published patches](PATCHES.md) |
| Platform | `linux/amd64` |
| Deployment | Compose recipe with an optional Caddy HTTPS overlay |
| Image | Signed release `registry.thesmos.dev/thesmos/casdoor:v4.15.0-thesmos.1` |

The [README](../README.md) describes the available capabilities. The
[validation summary](VALIDATION.md) explains what automated checks cover.
Users may inspect, modify and build the published source under its licences.

## Initial administrator setup

The image enables secure startup. On a fresh database, Casdoor still creates its
built-in `admin` account with the upstream default password, then replaces that
password from `bootstrapAdminPasswordFile` before any listener starts. Without
that file, or with a password shorter than 16 characters, startup stops. The
signing certificate is generated per database; it is not a shared key.

The secret applies only while the password is a known default, so later changes
made by the administrator survive restarts and secret rotation. Secure startup
also refuses `runmode` other than `prod`, RADIUS with an empty or default
secret, and a configured initialization file that is missing. See
[secure startup](CONFIGURATION.md#initial-administrator-and-secure-startup).

The [recipe acceptance test](VALIDATION.md) covers TOTP MFA enrollment and
enforcement, one-time recovery codes and sign-in lockout. Email and SMS factors
depend on configured providers and are not covered. With `initDataNewOnly=false`, initialization replaces defined users and
certificates on every restart; keep the image default `true`.

## Configuration and compatibility limits

- JSON JWT attributes, persistent SAML NameIDs and retained JWT certificates are
  API settings; no dedicated UI controls were added for them.
- JWT customization uses supported field mappings and literal values; there is
  no lambda or arbitrary script execution.
- SCIM filters support the equality subset listed in [configuration](CONFIGURATION.md).
  Thesmos-to-Casdoor writes use Casdoor's SCIM API. A separate provisioner
  carries changes between the two directories. Casdoor's built-in syncer
  imports remote Users only; remote writes and group import are unimplemented.
  Flows in both directions need an explicit authority and loop prevention.
- JWT certificate retention does not add retained keys to application-specific
  JWKS or implement SAML certificate rollover.
- The Compose recipe runs one Casdoor instance; sessions are files in that
  container. Multiple instances need `redisEndpoint`. No Kubernetes recipe is provided.
- [Measured capacity](VALIDATION.md#measured-capacity) applies to the recipe's
  limits on the test host; size `cpus` for the expected sign-in rate.
- Thesmos Enterprise features need the corresponding edition and licence; this
  repository does not distribute an Enterprise implementation or image.

## Upgrade considerations

The Compose recipe's project is now named `casdoor-integration`. To keep the
storage volumes of a deployment started from a release candidate, set
`COMPOSE_PROJECT_NAME=casdoor-integration-evaluation` when running Compose.

A redirect URI registered as a full URL now matches only that exact host. A
client that signs in from a subdomain of a registered URL fails with an invalid
redirect URI; register each callback URL, or use a host pattern without a scheme
such as `.example.com` when subdomains are intended.

Database syncers that use an SSH tunnel stop connecting until their **SSH host
key** is set. See [database syncers through an SSH tunnel](CONFIGURATION.md#database-syncers-through-an-ssh-tunnel).

Authorization-code clients must send the exact redirect URI. Codes issued before
the binding change may require fresh login. Custom refresh tokens omit application
custom claims; check any client that relied on those values.

Introspection reports tokens as active only to the client they were issued to.
An API that introspects tokens with its own client credentials receives
`active: false`; let it verify JWT signatures instead, or introspect with the
issuing client's credentials.

Saving an application now rejects claims Casdoor could not read back, such as
role names under `roles`. Rename such claims before editing an affected
application. An initialization file is validated the same way: with
`initDataNewOnly=false` Casdoor replaces each defined application through the
validated save path, so an invalid claim in that file stops startup. The
stored application is kept until the file is corrected.
SCIM `PUT` requests no longer clear administrator status, MFA,
provider links, groups or properties, and leave a disabled account disabled
unless they set `active`.

Enabling retained JWT certificates requires tokens with an authorized `kid`;
older keyless refresh tokens may require reauthentication. Retention applies to
Casdoor's verification policy. Application-specific JWKS still returns the current
certificate, so relying-party key distribution needs separate configuration.
Changing the signing algorithm during an overlap invalidates tokens signed with
the previous algorithm.

Changing an existing SAML NameID policy can require service-provider account
relinking. Test these changes against the existing deployment before upgrading.

## Release acceptance

This release passed the [security review](SECURITY-REVIEW.md), the licence and
source coverage check of [distribution material](DISTRIBUTION.md), and the
[automated acceptance tests](VALIDATION.md): secure startup, MFA and recovery,
upgrade, rollback, key rotation and backup restore, HTTPS, and capacity. OIDC,
SAML and SCIM were tested with Thesmos over TLS. The project maintainers
accepted the release; [release-policy.json](../release-policy.json) records the
acceptance and the exact build inputs. See
[maintenance and release instructions](../MAINTENANCE.md) for the release process.
