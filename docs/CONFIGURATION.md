# Configure this version

The container runs Casdoor with its administrator UI/API. Organization and
application settings are stored in the configured database; server configuration
is supplied at deployment. See the [local Compose recipe](../recipes/README.md)
for the required PostgreSQL configuration and [release limitations](RELEASE-STATUS.md)
before exposing any endpoint.

## Server configuration and persistence

Mount a readable file at `/conf/app.conf`. The container refuses to start without
it and runs as UID/GID `1000:1000`. The recipe mounts `/conf` read-only and provides
a writable temporary directory at `/tmp`. Casdoor's supported environment
configuration overrides remain available, such as `initDataNewOnly` and `logConfig`.

Use a persistent database for users, clients, providers and theme configuration.
A shared PostgreSQL server can host both applications with separate databases
and roles; the Casdoor role should have no access to the Thesmos database.
Media uploads and other writable storage require a configured volume or external
storage provider. The supplied recipe does not configure that storage or a
durable session store.

`initDataNewOnly=true` is the image default. It avoids replacing existing records
on startup, but does not replace Casdoor's demonstration administrator credentials
on a fresh database. Setting it to `false` with a replacement import can recreate
users and certificates on subsequent starts. It is not a safe one-time bootstrap
mechanism.

## Themes and branding

Use Casdoor's organization/application editors for supported theme and branding
settings. The following is an example `themeData` value for an organization:

```json
{
  "themeType": "default",
  "colorPrimary": "#457b6a",
  "borderRadius": 7,
  "isCompact": false,
  "isEnabled": true
}
```

These are upstream Casdoor settings. They can be changed without rebuilding the
image, and saved theme configuration persists with the database. Changes to
frontend components or styles outside the supported settings require rebuilding
the frontend. Logo/media files need persistent storage separately from their
configuration records.

## Typed JWT claims

Configure a Casdoor application with `tokenFormat: "JWT-Custom"`. The following
fragment adds a literal JSON claim to its `tokenAttributes`:

```json
{
  "tokenFormat": "JWT-Custom",
  "tokenAttributes": [
    {
      "name": "https://app.example/authorization",
      "category": "Static Value",
      "type": "JSON",
      "value": "{\"roles\":[\"reader\"],\"enabled\":true}"
    }
  ]
}
```

The emitted claim is an object, rather than a JSON-encoded string. The `value`
is a JSON string in the application configuration, containing the JSON literal
to emit. This fragment illustrates fields to merge into an existing application;
it is not a complete application-creation request.

The upstream field mappings remain available. Added `JSON` attributes are
configured through the authenticated application API; the UI dropdown has not
been extended. Static roles apply to every user of that application, so use
appropriate per-user mappings when authorizations differ by user. Only trusted
administrators should select claim fields and values. There is no lambda or
other executable JWT customization hook.

Configuration limits: at most 64 `tokenFields` and 64 `tokenAttributes`, claim
names of 1–256 bytes, and attribute values up to 8192 bytes. Invalid JSON,
duplicate names and protected protocol names are rejected on save. Protected
names are `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`, `tokenType`, `azp`,
`nonce`, `scope` and `cnf`. Custom refresh tokens retain protocol claims without
the application's custom claim payload.

## Persistent SAML identity

Set `usePersistentSamlNameId: true` through the application API to use the user's
ID as the SAML NameID with format
`urn:oasis:names:tc:SAML:2.0:nameid-format:persistent`. It takes precedence over
`useEmailAsSamlNameId`; ensure every affected user has a nonempty ID. Disabling
it restores upstream NameID selection.

Enable it before linking accounts at the service provider where possible.
Changing an existing deployment's NameID policy can require relinking accounts.
Thesmos SAML integration requires Enterprise and its corresponding licence.

## JWT signing-key overlap

A global administrator can configure `retainedSigningCerts` on an application.
Each entry contains `cert` as an exact `owner/name` and `expiresAt` as an absolute
Unix timestamp in seconds. The certificate must exist, have JWT scope and belong
to the application's owner or organization. Certificate names, including the
current signing certificate, must be distinct.

At most two previous certificates are allowed, with deadlines no more than
24 hours ahead. They authorize verification only; issuance uses the current
certificate. With this option enabled, incoming JWTs need an authorized `kid`
and the application's signing algorithm. Expired or removed certificates no
longer authorize verification. Without it, the existing single-key behavior is
preserved. This option does not add retained keys to application-specific JWKS; relying
parties need verified key-distribution and rotation configuration.

## SCIM provisioning

Configure Casdoor's SCIM server when another system provisions Casdoor, or its
SCIM syncer when Casdoor provisions another system. Select one authoritative
writer for a given user/group scope and configure credentials, organization and
attribute mappings. Enabling both directions does not define conflict resolution
or prevent synchronization loops.

This version accepts single string equality filters for Users (`userName`,
`externalId`) and Groups (`displayName`). Other operators and compound filters
are rejected. Group external IDs are retained, but are not a supported group
list-filter field. Pagination reports the matching total, with a service-provider
maximum of 100 results per page.

SCIM `active: false` maps to Casdoor's forbidden-user state. It cannot immediately
invalidate tokens at clients that only verify JWT signatures offline; configure
token lifetime and the client's revocation/introspection behavior accordingly.
