# Patch series

Casdoor authorship, copyright headers and project identity are preserved.
The exact revision and ordered SHA-256 checksums are in `upstream.lock.json`.
The source preparer verifies them before applying any patch.

| Layer | Purpose |
| --- | --- |
| Integration | SCIM request lifetime, supported equality filters and pagination, group external IDs, active-state revocation, typed JSON claims, persistent SAML NameIDs, redirect binding, introspection/refresh application binding and opt-in retained signing certificates |
| Security candidate | Go dependency updates, maintained ACME library, ACME and SAML regression coverage |
| Frontend candidate | Runtime dependency updates and official SheetJS distribution |
| Build chain candidate | Frontend build dependency updates |
| Claim configuration candidate | Validate custom claim configuration before persistence and restrict partial application writes to selected fields |
| LDAP licence candidate | Pin the LDAP message module to the author's MIT release; its parent is the previously pinned revision and only LICENSE changes |

These are candidate changes, with regression tests included in the patches.
They are not upstream-supported features or a production approval.
JSON claims use a literal administrator-configured value; there is no arbitrary
JWT lambda. The current upstream UI does not offer the added JSON value type.
Persistent SAML NameIDs and retained signing certificates are opt-in API settings.
SCIM filters are bounded equality expressions, not a complete SCIM filter engine.

For existing deployments, authorization codes minted before redirect binding
may require fresh login. Refresh-token content and signing-certificate policy
changes also require explicit upgrade acceptance. Keep the matching source and
patch list available for every distributed image.

Modified Go source carries modification notices and original headers. Generated
Go and Yarn dependency manifests and the frontend package manifest also change;
the source provenance lists every modified path and identifies the responsible
integration patch layer. Dependencies retain their own licences.
