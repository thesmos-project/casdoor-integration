# What the Casdoor patches bring

The patches improve Casdoor's SCIM provisioning, SAML identity and JWT/OAuth
behavior for compatible applications and provisioners. Thesmos is the integration
example below. The base is Casdoor `v4.15.0`, commit
`2301694036cbdcf932b3b1cbef02fb61d9820429`.

## Provision users and groups through SCIM

**Thesmos → Casdoor:** a SCIM provisioner sends user/group changes to Casdoor's
SCIM API. This version improves how Casdoor finds and updates those records:

| Change | Why it matters |
| --- | --- |
| Apply equality filters to user/group lookups. | The provisioner can find an existing account or group before creating or updating it. |
| Count all matching records and paginate the returned results. | The provisioner can traverse a directory without mistaking a page's length for the total. |
| Preserve group `externalId` through creation and updates. | The provisioner can retain the source group's identity across synchronization. |
| Map SCIM `active` to Casdoor's account state, including PATCH. | A deactivation sent by the provisioner disables the corresponding Casdoor account. |
| Serialize updates to a user's session record. | Concurrent sign-ins of one user no longer fail with a duplicate-key error or drop a session id, which sign-out everywhere relies on. |
| Limit a full replacement (`PUT`) to the attributes SCIM maps. | Administrator status, MFA, linked sign-in providers, groups and properties survive a replacement, and a disabled account stays disabled unless the request sets `active`. |

**Casdoor → Thesmos:** a provisioner reads Casdoor's SCIM Users/Groups and writes
them to Thesmos's SCIM API. Filtered responses, correct pagination and retained
identifiers also support this direction.

There is also a fix for Casdoor's built-in remote-user import syncer: its HTTP
request remains usable after the request helper returns. The HTTP client retains
its 30-second timeout.

See [SCIM setup and a deactivation request](CONFIGURATION.md#scim-provisioning).

## Keep SAML account linking stable

The optional application setting `usePersistentSamlNameId` uses the user's ID
as a persistent SAML NameID. An email or username change therefore keeps the
same subject at the service provider. A deleted and recreated account receives
its own identity.

This supports stable linking when Casdoor provides SAML sign-in to Thesmos
Enterprise. Enable the setting before linking accounts where possible.
See [persistent SAML identity](CONFIGURATION.md#persistent-saml-identity).

## Add structured JWT authorization claims

The `JSON` token attribute type lets an administrator configure an object,
array, boolean or other JSON literal as a custom claim. This supports structured
application authorization data alongside Casdoor's existing field mappings.

Application saves validate claim names, types, JSON values and size limits.
They also reject a claim whose value Casdoor could not read back, such as role
names under `roles`, which Casdoor reserves for its own role objects.
Protected protocol claims retain their issuer-controlled values. Partial updates
preserve omitted claim settings, and custom refresh tokens carry their protocol
claims separately from the application's custom payload.

See the [typed JWT claim example](CONFIGURATION.md#typed-jwt-claims).

## Bind tokens to the correct client

Authorization-code exchange checks the exact redirect URI used to issue the
code. Introspection and refresh match the stored token's application owner,
name and organization to the authenticated client. A token issued to one client
therefore reports `active: false` when another client introspects it.

Applications can also retain up to two previous JWT signing certificates for
verification during a bounded overlap. Newly issued refresh tokens include a
key ID. Organization administrators can keep editing an application after a
global administrator removes a retained certificate. See
[JWT signing-key overlap](CONFIGURATION.md#jwt-signing-key-overlap).

## Start safely on a new database

Upstream Casdoor creates a built-in `admin` account with the password `123` on a
fresh database. The secure-startup patch replaces it from a bootstrap secret file
before any listener starts and refuses to serve while it remains a default. It
never resets a password that has already changed. It also refuses development
mode, a default RADIUS secret and a missing initialization file, and disables the
RADIUS server when no port is configured; an empty port previously opened a
random public UDP port. The image enables these checks with `secureStartup=true`.

The same patch adds `dbMaxOpenConns` to limit the database connection pool, and
keeps the built-in policy adapters on two connections each. Without a limit,
16 concurrent clients exhausted a PostgreSQL server's connections, which would
also block other applications sharing it.
See [secure startup](CONFIGURATION.md#initial-administrator-and-secure-startup).

## Close redirect and SSH tunnel gaps

Upstream Casdoor accepts every subdomain of a redirect URI registered as a full
URL, so `https://app.example.com/callback` also accepts
`https://evil.app.example.com/callback`. Whoever controls such a subdomain could
receive authorization codes. A full URL now matches only its own host. Host
patterns without a scheme, such as `.example.com`, still allow subdomains.

Database syncers that connect through an SSH tunnel accepted any server key. A
syncer now has an **SSH host key** setting; Casdoor verifies the server against
it and refuses to connect without it. See
[database syncers through an SSH tunnel](CONFIGURATION.md#database-syncers-through-an-ssh-tunnel).
The [security review](SECURITY-REVIEW.md) lists the advisories checked for this version.

## Update dependencies and distribution material

Backend changes update Go dependencies, including the Coraza web application
firewall library, and use the maintained `go-acme/lego` ACME implementation.
Frontend changes update runtime/build dependencies and use the official SheetJS
distribution. Related regression tests are included.

The LDAP message library uses its author's MIT revision
[`8d785c64d1c87d6fa9c95591edf9d8abc603a34c`](https://github.com/lor00x/goldap/commit/8d785c64d1c87d6fa9c95591edf9d8abc603a34c).
Only its licence changed from the previously pinned revision. The original
notice is included with the other [distribution sources and notices](DISTRIBUTION.md).

## Patch files

[upstream.lock.json](../upstream.lock.json) records the application order and
SHA-256 checksums. Original Casdoor headers and authorship are preserved.

| File | Changes |
| --- | --- |
| [Integration](../patches/casdoor-integration.patch) | SCIM, JSON claims, persistent SAML identity, redirect/client binding and retained JWT certificates. |
| [Backend security](../patches/casdoor-security-candidate.patch) | Go, ACME and Coraza updates, exact redirect hosts, SSH host key verification and SAML regression tests. |
| [Frontend](../patches/casdoor-frontend-candidate.patch) | Browser runtime dependencies, SheetJS distribution and the syncer SSH host key field. |
| [Build dependencies](../patches/casdoor-build-chain-candidate.patch) | Frontend build/test dependencies. |
| [Claim configuration](../patches/casdoor-claim-configuration-candidate.patch) | Save-time validation and selected-field application updates. |
| [LDAP licence](../patches/casdoor-ldap-license-candidate.patch) | Author-provided MIT dependency revision. |
| [Secure startup](../patches/casdoor-secure-startup-candidate.patch) | Bootstrap administrator password, unsafe-setting refusal and RADIUS port handling. |

Before deploying or upgrading, read [version limits and compatibility changes](RELEASE-STATUS.md).
