# Configure this version

The container runs Casdoor with its administrator UI/API. Organization and
application settings are stored in the configured database; server configuration
is supplied at deployment. See the [local Compose recipe](../recipes/README.md)
for the required PostgreSQL configuration and [release limitations](RELEASE-STATUS.md)
before exposing any endpoint.

The same Casdoor settings apply when integrating another application. Configure
its client credentials, redirect URI, SAML service-provider settings or SCIM
mappings. The Thesmos examples below describe one integration of these interfaces.

## SCIM provisioning

The Thesmos directory SCIM API requires Enterprise. Use a SCIM provisioner
to transfer directory changes between the two applications.

### Send Thesmos users and groups to Casdoor

Use a SCIM provisioner to deliver changes from the Thesmos directory to Casdoor's
SCIM API. Casdoor receives requests to create, update and deactivate users and
to manage groups and memberships. Configure the Casdoor SCIM credentials,
organization and attribute mappings on the provisioner.

For example, the provisioner can disable a Casdoor account by sending a SCIM
PATCH to its user resource:

```http
PATCH <Casdoor SCIM base>/Users/<user-id>
Content-Type: application/scim+json
```

```json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {"op": "replace", "path": "active", "value": false}
  ]
}
```

The active-state patch applies that boolean to Casdoor's forbidden-user state.
A full replacement (`PUT`) updates the attributes SCIM maps and retains
Casdoor-only account state; include `active` to change whether the account is
enabled.
The group identifier patch retains the source's `externalId`. The lookup and
pagination patches help the provisioner locate and reconcile existing records.

### Send Casdoor users and groups to Thesmos

Configure the provisioner to read Casdoor's SCIM Users/Groups and write them to
Thesmos's SCIM API. Choose an authoritative directory for each user/group scope.
If both directions run, use distinct ownership scopes and define how conflicting
changes are handled.

The provisioner runs as a separate component. The Casdoor image supplies the
Casdoor SCIM endpoints for both receiving writes and serving reads.

### Lookup fields

Users accept single string equality filters on `userName` and `externalId`.
Groups accept them on `displayName`. Pagination reports the matching total,
with a service-provider maximum of 100 results per page.

`userName` and `displayName` match case-insensitively. On PostgreSQL, add
expression indexes for large directories so these lookups avoid full scans
(table names shown for the default empty `tableNamePrefix`):

```sql
CREATE INDEX user_lower_name ON "user" (LOWER(name));
CREATE INDEX group_lower_display_name ON "group" (LOWER(display_name));
```

### Import remote users with Casdoor's syncer

Casdoor also has a built-in SCIM user import syncer. Configure a remote SCIM
server and mappings to fetch its Users into Casdoor. The request-lifetime patch
allows the HTTP requests to complete under the client's 30-second timeout.
See [version limitations](RELEASE-STATUS.md) for its supported operations.

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

`initDataNewOnly=true` is the image default and preserves existing records during
initialization. Use the [bootstrap guidance](RELEASE-STATUS.md#initial-administrator-setup)
when setting up a fresh database.

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

These upstream Casdoor settings are saved in the database and take effect through
administrator configuration. Changes to
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
to emit. Merge this fragment into an existing application configuration.

The upstream field mappings remain available. Added `JSON` attributes are
configured through the authenticated application API. Static roles apply to every user of that application, so use
appropriate per-user mappings when authorizations differ by user. Only trusted
administrators should select claim fields and values. See [version limitations](RELEASE-STATUS.md) for the customization scope.

Configuration limits: at most 64 `tokenFields` and 64 `tokenAttributes`, claim
names of 1–256 bytes, and attribute values up to 8192 bytes. Invalid JSON,
duplicate names and protected protocol names are rejected on save. A name that
matches a Casdoor user field, compared case-insensitively, must carry a value
of that field's type: `roles` must hold role objects, so emit role names under
another name such as `role_names`. Protected
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
longer authorize verification. Organization administrators can still save the
application after a retained certificate is removed; the next global
administrator save must remove the stale entry. Keep the signing algorithm
unchanged during an overlap, because older tokens must use the application's
current algorithm. Without it, the existing single-key behavior is
preserved. Configure relying-party key distribution separately; see the
[rotation and upgrade limits](RELEASE-STATUS.md#upgrade-considerations).
