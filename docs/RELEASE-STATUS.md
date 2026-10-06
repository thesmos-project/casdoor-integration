# Current version and limitations

| Item | Status |
| --- | --- |
| Version | `v4.15.0-thesmos.1-rc.2` |
| Source | Casdoor `v4.15.0` plus the [seven published patches](PATCHES.md) |
| Platform | `linux/amd64` |
| Local use | Buildable evaluation image and loopback Compose recipe |
| Registry distribution | `rc.2` publication pending. Signed `rc.1` image, without secure startup: `registry.thesmos.dev/thesmos/casdoor@sha256:afe7e0c8ece067a9b4ef4cf38e8e9cf108c5b7b4b96b97f335aa005b338f60d4` |
| Production release | None; this candidate is not approved for production |

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

MFA enrollment, account recovery and abuse controls still need acceptance
testing. With `initDataNewOnly=false`, initialization replaces defined users and
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
- The Compose recipe starts Casdoor only and has no production HTTPS endpoint,
  media storage or durable session-store configuration. No Kubernetes recipe is provided.
- Its memory/CPU limits are evaluation settings, not measured production capacity.
- Thesmos Enterprise features need the corresponding edition and licence; this
  repository does not distribute an Enterprise implementation or image.

## Upgrade considerations

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

## Production work still required

Production approval remains open for MFA/recovery and abuse-control acceptance; exact-source advisory analysis and independent security review;
live protocol and key-rotation acceptance; upgrade/rollback and backup recovery;
public HTTPS/proxy configuration and durable storage; and deployment capacity.
Dependency and asset licensing also require review for the accepted release.

Passing compilation, regression tests or an image signature does not close those
requirements. Stable publication is blocked by [release-policy.json](../release-policy.json).
See [maintenance and release instructions](../MAINTENANCE.md) for the release process.
