# Configuration

Casdoor keeps organization and application settings in its database; you change
them in the administrator UI or API. Server settings come from `app.conf`, which
you supply when you deploy; the [recipes](../recipes/README.md) show how.

The examples use Thesmos. Another application uses the same Casdoor settings:
its client credentials, redirect URI, SAML service-provider settings or SCIM
mappings.

## SCIM provisioning

The Thesmos directory SCIM API requires Thesmos Enterprise. A SCIM provisioner,
run as a separate component, copies directory changes between the two
applications.

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

Setting `active` to `false` disables the account; `true` enables it again. A
full replacement (`PUT`) updates the attributes SCIM maps and keeps Casdoor-only
account state, such as MFA and administrator status; include `active` to change
whether the account is enabled. Groups keep the `externalId` the provisioner
sends, and [lookup fields](#lookup-fields) let it find existing records before it
creates new ones.

### Send Casdoor users and groups to Thesmos

Configure the provisioner to read Casdoor's SCIM Users/Groups and write them to
Thesmos's SCIM API. Choose an authoritative directory for each user/group scope.
If both directions run, use distinct ownership scopes and define how conflicting
changes are handled.


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

Casdoor also has a built-in SCIM syncer that imports users from a remote SCIM
server. Configure the server and attribute mappings on the syncer. Each request
to the remote server has a 30-second timeout. The syncer imports users only;
see [limits](RELEASE-NOTES.md#limits).

### Database syncers through an SSH tunnel

A database syncer can reach its database through SSH. Casdoor verifies the SSH
server against the syncer's **SSH host key** and refuses to connect without it.
Paste one or more public key lines, for example the output of:

```sh
ssh-keyscan -p 22 db-gateway.example.com
```

Check the scanned key against the server itself, such as
`/etc/ssh/ssh_host_ed25519_key.pub`, before you save it. Casdoor accepts
`authorized_keys` lines and `known_hosts` lines; it ignores the host name in a
`known_hosts` line and always connects to the syncer's SSH host.

## Server configuration and persistence

Mount a readable file at `/conf/app.conf`; the container refuses to start without
it. Casdoor runs as UID/GID `1000:1000`. The recipes mount `/conf` read-only, keep
sessions in a volume at `/tmp` and uploaded files in a volume at `/files`. An
environment variable with the same name overrides an `app.conf` setting, for
example `initDataNewOnly`, `logConfig` or `dbMaxOpenConns`.

Use a persistent database for users, clients, providers and theme configuration.
A shared PostgreSQL server can host both applications with separate databases
and roles; the Casdoor role should have no access to the Thesmos database.
To store uploads locally, add a storage provider of type `Local File System` with
its domain set to the public origin; files are served from `/files`. An object
storage provider works too. Casdoor keeps sessions as files, so run one instance
per database, or configure `redisEndpoint` for shared sessions.

`dbMaxOpenConns` limits the database pool (`20` in the image). Built-in policy
adapters add at most two connections each.

Behind an HTTPS proxy or Ingress, set `sessionCookieSecure = true` (or the
environment variable `sessionCookieSecure=true`). Casdoor receives plain HTTP from
the proxy and otherwise sends its session cookie without `Secure`, so a browser
could send it over an unencrypted request. The [Kubernetes recipe](../recipes/kubernetes/README.md)
sets it. Leave it unset when you open Casdoor directly over HTTP, such as
`http://localhost:19080`, or sign-in stops working.

`initDataNewOnly=true` is the image default: an initialization file only adds
records that do not exist yet. With `false`, Casdoor replaces the users and
certificates the file defines on every restart.

## Initial administrator and secure startup

The image sets `secureStartup=true`. Before Casdoor serves requests, it checks
the built-in `admin` account. While that account has a known default password,
Casdoor reads a new password from `bootstrapAdminPasswordFile`; without a valid
file it stops with `Secure startup refused`. Create the file before the first
start, readable by UID 1000:

```sh
openssl rand -base64 24 > .local/deployment/admin-password
chmod 0644 .local/deployment/admin-password
```

The recipe configuration reads it from `/conf/admin-password`. The password needs
at least 16 characters without surrounding whitespace. Sign in as `admin` in the
`built-in` organization with it, then enable MFA for the account. Casdoor uses
the file only while the password is a default, so changing the password in the
UI, or rotating the file, never resets the administrator's current password.
You can remove the file after the first start. Casdoor generates the JWT
signing certificate for each new database; no key is shared between deployments.

Enable TOTP MFA from the account page and store the recovery code offline. A
recovery code works once; after using it, remove and re-enroll MFA to obtain a
new one. Five wrong passwords or codes freeze sign-in for 15 minutes by default;
set `failedSigninLimit` and `failedSigninFrozenTime` on the application to change
this.

Secure startup also stops Casdoor when:

- `runmode` is not `prod`;
- `radiusServerPort` is set and `radiusSecret` is empty or `secret`;
- `initDataFile` is set but the file is missing.

An empty `radiusServerPort` disables the RADIUS server, as an empty
`ldapServerPort` disables LDAP. The container runs without privileges, so choose
ports above 1023 when enabling either server. Setting `secureStartup=false`
restores upstream behavior with a warning; use it only for local experiments.

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

Casdoor saves these settings in its database and applies them without a
restart. Changes beyond these settings, such as new frontend components, require
rebuilding the image. Uploaded logos and images need persistent storage; see
[server configuration](#server-configuration-and-persistence).

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

Casdoor's field mappings remain available. `JSON` attributes are set through the
application API. A fixed value applies to every user of the application; use
field mappings when authorizations differ by user. Only trusted administrators
should choose claim fields and values.

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
preserved. Application-specific JWKS publishes only the current key, so give
relying parties the previous key another way during the overlap.

## Upgrade, rollback and backup

Pin the image by digest and change the digest to upgrade. Casdoor updates its
tables on startup; settings, clients, signing keys and issued tokens carry over.
Rolling back to the previous release's digest is tested and keeps them too.
Authorization codes issued just before an upgrade may need a new sign-in. Read
the [release notes](RELEASE-NOTES.md) and back up the database before every
upgrade.

With a restricted role named `casdoor`, a consistent online backup and a restore
into a new database look like this:

```sh
pg_dump -Fc -f casdoor.dump casdoor
createdb -O casdoor casdoor_restore
pg_restore --no-owner --role=casdoor -d casdoor_restore casdoor.dump
```

Point `dbName` and `dataSourceName` at the restored database and start the same
image. The restored instance keeps its signing keys, so tokens issued before the
backup stay valid and refreshable. Keep the same `origin`, so the token issuer is
unchanged.

To rotate an application's signing key, create a JWT certificate, set it as the
application's `cert`, and list the previous certificate in `retainedSigningCerts`
for up to 24 hours; see [signing-key overlap](#jwt-signing-key-overlap). Remove
the retention after older tokens have expired.
