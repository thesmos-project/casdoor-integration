# Why this version patches Casdoor

This version builds Casdoor `v4.15.0` at commit
`2301694036cbdcf932b3b1cbef02fb61d9820429`. Casdoor's original authorship and
copyright headers are preserved. [The source lock](../upstream.lock.json) lists
the six patches in application order with SHA-256 checksums.

Themes, OIDC, SAML, the SCIM server and SCIM syncer are existing Casdoor features.
The following changes adapt specific behavior and dependencies in that release.

## 1. Protocol and claim integration

Patch: [casdoor-integration.patch](../patches/casdoor-integration.patch).

| Reason | Change in this version | Scope or limitation |
| --- | --- | --- |
| Outbound SCIM requests were canceled when the request-building helper returned, before the HTTP client could send them. | Remove the prematurely canceled context; keep the caller's 30-second HTTP client timeout. | Applies to outbound HTTP requests used to import remote users into Casdoor; it does not add SCIM push support. |
| Provisioners need filtered lookups and a total count independent of the returned page. | Apply supported equality filters to both count and page queries; return the full matching total. | Users: `userName eq` and `externalId eq`. Groups: `displayName eq`. Unsupported expressions are rejected. |
| A provisioning system needs to retain its own identifier for a group. | Store and return group `externalId`, including updates. | Does not add a group `externalId` list filter. |
| SCIM deactivation needs to affect Casdoor's account state. | Map the boolean `active` attribute to Casdoor's forbidden-user state on import/update, including PATCH. | Does not revoke an already-issued JWT at a relying party that validates it offline. |
| Application authorization claims may need nested objects, arrays or booleans. | Add literal `JSON` token attributes and prevent custom attributes/properties from overriding protected protocol claims. Custom refresh tokens omit application custom claims. | JSON values are administrator configuration; no arbitrary code execution. |
| Email addresses and usernames can change. | Add `usePersistentSamlNameId`, which uses the user's ID and the persistent SAML NameID format. | Opt-in application API setting; requires a nonempty user ID. |
| Authorization-code exchange must use the redirect URI that created the code. | Store that URI and reject an exchange with an absent or different `redirect_uri`. | Existing clients must send the exact URI; previously issued codes may require fresh login. |
| A token must belong to the client performing introspection or refresh. | Match application owner, name and organization before accepting the stored token. | Does not grant cross-application introspection. |
| JWT key changes need a bounded overlap for previously issued tokens. | Add opt-in `retainedSigningCerts` for verification of explicitly retained keys. New refresh tokens carry `kid`. | At most two previous certificates, deadlines within 24 hours, configured by global administrators. This does not add retained keys to application-specific JWKS or implement SAML certificate rollover. |

See [configuration examples](CONFIGURATION.md) for the added application fields.

## 2. Backend dependencies

Patch: [casdoor-security-candidate.patch](../patches/casdoor-security-candidate.patch).

Updates the Go toolchain/dependencies and replaces the earlier ACME dependency
with the maintained `go-acme/lego` implementation. Included ACME and SAML
regressions check affected behavior. These updates do not establish that every
advisory or authentication path has been cleared; see [release limitations](RELEASE-STATUS.md).

## 3. Frontend runtime dependencies

Patch: [casdoor-frontend-candidate.patch](../patches/casdoor-frontend-candidate.patch).

Updates frontend dependencies, including cookie handling, routing and fetching,
and obtains SheetJS from its official distribution. The purpose is to update the
browser dependency set while retaining the Casdoor application and its branding
configuration. It does not introduce a replacement user interface.

## 4. Frontend build dependencies

Patch: [casdoor-build-chain-candidate.patch](../patches/casdoor-build-chain-candidate.patch).

Updates Vite, Cypress and related build dependencies. These changes affect how
the frontend is built and tested; they do not add a user-facing authentication
feature. The container ships the compiled frontend.

## 5. Custom claim configuration

Patch: [casdoor-claim-configuration-candidate.patch](../patches/casdoor-claim-configuration-candidate.patch).

Rejects invalid claim configuration when an application is saved: reserved or
duplicate names, unknown fields/types, malformed JSON and oversized values.
Partial application updates write only selected fields, so an unrelated edit
cannot overwrite omitted claim settings. Explicitly clearing selected claim
settings still works. Token issuance also tolerates legacy null attribute rows.

This protects the configuration boundary; administrators still control which
user data is exposed to clients. The JSON attribute type is available through
the API and has no added dropdown option in the current UI.

## 6. LDAP dependency licence

Patch: [casdoor-ldap-license-candidate.patch](../patches/casdoor-ldap-license-candidate.patch).

Selects the LDAP message library author's MIT revision
[`8d785c64d1c87d6fa9c95591edf9d8abc603a34c`](https://github.com/lor00x/goldap/commit/8d785c64d1c87d6fa9c95591edf9d8abc603a34c).
Its parent is the previously pinned GPLv2 revision and only `LICENSE` changed;
the library's other files are identical. This uses the author's licence change
and preserves that notice in the distribution.

## Upgrade considerations

Test redirect URI handling, refresh-token contents and key policy before upgrading
an existing deployment. Enabling retained certificates requires JWTs with `kid`;
older keyless refresh tokens may require reauthentication. Persistent SAML NameIDs
change the subject seen by a service provider and can require account relinking.

All patches are independently maintained candidate changes. Upstream support is
not implied. [Maintenance instructions](../MAINTENANCE.md) describe how they are
reviewed against later Casdoor releases and removed when upstream equivalents
are verified.
