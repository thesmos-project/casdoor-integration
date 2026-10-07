# Automated validation coverage

This document describes checks provided by the builder and workflows for
`v4.15.0-thesmos.1-rc.3`. It is not a certification of production security or
compatibility with every OIDC, SAML or SCIM client.

| Check | Coverage |
| --- | --- |
| Source preparation | Exact Casdoor commit/tag, ordered patch checksums and modified-source provenance. |
| Backend build | Selected object, SCIM and certificate regressions under the Go race detector, plus LDAP package tests and compilation. |
| Frontend build | Type checking, compilation and agreement between normal and dependency-inventory build output. |
| Distribution | Installed system packages match their lock; required dependency notices and corresponding source archives are present; an SPDX inventory is generated. |
| Container startup | Missing mounted configuration is refused. A fresh database without a bootstrap administrator secret is refused; with one, the default password no longer signs in, and changing the secret file does not reset the password on restart. |
| Configurable runtime | Served frontend, saved organization theme, theme persistence across restart and rejection of a protected claim override. |
| Runtime restrictions | Nonroot execution with a read-only filesystem and dropped capabilities. |
| Upgrade and recovery | [upgrade-acceptance.py](../scripts/upgrade-acceptance.py) starts the latest published release on the same PostgreSQL/TLS recipe, creates an organization, client, user, theme and tokens, then upgrades to the candidate, rolls back, upgrades again, rotates the signing key with a retained previous key and restores a database backup into a new database. After each step it checks settings, signing keys, earlier tokens and refresh tokens. |
| HTTPS recipe | [https-acceptance.py](../scripts/https-acceptance.py) runs `recipes/compose.https.yaml` with Caddy's local authority: HTTP redirect, verified certificate and HSTS, HTTPS OIDC issuer, `Secure` and `HttpOnly` session cookies, a forged `X-Forwarded-For` ignored, and uploaded files and sessions surviving a restart. |
| Capacity | [capacity-acceptance.py](../scripts/capacity-acceptance.py) loads the recipe within its limits; see [measured capacity](#measured-capacity). |
| Deployment recipe | [recipe-acceptance.py](../scripts/recipe-acceptance.py) runs the unchanged Compose recipe against disposable PostgreSQL with a restricted role and verified TLS: refusal without the bootstrap secret, rejection of `admin/123`, TOTP MFA enrollment and enforced second factor, wrong-code rejection, one-time recovery code, MFA and password kept across restart and secret rotation, and lockout after five wrong passwords. |
| Publication | Registry upload probe, image signing, SPDX attestation verification and a smoke test of the pulled digest. An optional public mirror must also pass anonymous pull and signature/attestation verification. |

## Measured capacity

16 concurrent clients for 20 seconds per workload, recipe limits of 384 MiB and
one CPU, `dbMaxOpenConns=20`, PostgreSQL 16 with TLS on the same host:

| Workload | Requests/s | p95 latency | Errors |
| --- | --- | --- | --- |
| Password sign-in (bcrypt) | 15 | 1.7 s | 0 |
| Client-credentials token | 50 | 0.53 s | 0 |
| Introspection | 152 | 172 ms | 0 |
| Discovery and JWKS | 308 | 66 ms | 0 |

Peak memory was 73 MiB and peak database connections 22. Figures depend on the
host CPU; CI reruns the test and fails on errors, an out-of-memory kill, a
restart, memory above 80% of the limit or more than 24 connections.

The runtime smoke test uses a disposable SQLite database on loopback; the recipe
acceptance test adds PostgreSQL over TLS and the HTTPS test adds the proxy. A
complete Thesmos stack is tested in a separate evaluation environment. Publication checks run when publishing; passing a source build alone
does not establish that an image is available in a registry.

The [Check candidate workflow](../.github/workflows/check.yml) produces build,
distribution, source-provenance and runtime reports as GitHub Actions artifacts.
Consult a successful run for the exact source revision being evaluated in the
[Actions history](https://github.com/thesmos-project/casdoor-integration/actions).
The [publishing workflow](../.github/workflows/publish.yml) performs its own
checks before a digest can be advertised as verified.

Candidate distribution has a separate policy from stable releases. The
machine-readable [release policy](../release-policy.json) records candidate
scope and the build-input fingerprint. [Production limitations](RELEASE-STATUS.md)
remain open regardless of these automated checks.
