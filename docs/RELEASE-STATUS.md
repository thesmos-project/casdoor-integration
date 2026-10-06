# Current version and limitations

| Item | Status |
| --- | --- |
| Version | `v4.15.0-thesmos.1-rc.1` |
| Source | Casdoor `v4.15.0` plus the [six published patches](PATCHES.md) |
| Platform | `linux/amd64` |
| Local use | Buildable evaluation image and loopback Compose recipe |
| Registry distribution | Pending; no verified image digest is available yet |
| Production release | None; this candidate is not approved for production |

The [README](../README.md) describes the available capabilities. The
[validation summary](VALIDATION.md) explains what automated checks cover.
Users may inspect, modify and build the published source under its licences.

## Initial administrator setup

A fresh database still receives Casdoor's built-in demonstration administrator
with password `123`. Its signing certificate is generated during initialization;
it is not a shared key taken from this repository. The container does not yet
provide a secure one-time administrator bootstrap.

Keep evaluation endpoints on loopback. A bootstrap import with
`initDataNewOnly=true` does not override already-created default records.
Changing it to `false` can recreate users and signing certificates on restart.
Neither setting alone provides production-safe initialization.

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

Enabling retained JWT certificates requires tokens with an authorized `kid`;
older keyless refresh tokens may require reauthentication. Retention applies to
Casdoor's verification policy. Application-specific JWKS still returns the current
certificate, so relying-party key distribution needs separate configuration.

Changing an existing SAML NameID policy can require service-provider account
relinking. Test these changes against the existing deployment before upgrading.

## Production work still required

Production approval remains open for secure bootstrap, MFA/recovery and abuse
controls; exact-source advisory analysis and independent security review;
live protocol and key-rotation acceptance; upgrade/rollback and backup recovery;
public HTTPS/proxy configuration and durable storage; and deployment capacity.
Dependency and asset licensing also require review for the accepted release.

Passing compilation, regression tests or an image signature does not close those
requirements. Stable publication is blocked by [release-policy.json](../release-policy.json).
See [maintenance and release instructions](../MAINTENANCE.md) for the release process.
