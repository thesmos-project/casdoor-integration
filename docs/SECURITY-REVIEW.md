# Security review of v4.15.0-thesmos.1-rc.4

Reviewed on 2026-10-07. The source is Casdoor `v4.15.0` (commit
`2301694036cbdcf932b3b1cbef02fb61d9820429`) with the
[seven patches](PATCHES.md). This review checks published advisories and
dependency scanners against that exact source and image. It is not a
penetration test, and an independent review is still pending.

## What was checked

| Area | Method | Result |
| --- | --- | --- |
| Casdoor advisories | Each of the 20 Casdoor records in the OSV database compared with the source code | Fixed upstream or by this version; see below |
| Go dependencies | `govulncheck` v1.8.0, vulnerability database of 2026-10-01 | No vulnerable code reached; three findings in modules whose affected packages are not compiled in |
| Image packages | Trivy 0.75.0, database of 2026-10-07 | Alpine 3.24.2 packages: none. Go binary: one module-level finding, below |
| Browser dependencies | OSV-Scanner 2.6.0 on `web/yarn.lock` (762 packages) | Two findings, below; neither affects the served pages |

## Fixed in this version

| Problem | Change |
| --- | --- |
| A redirect URI registered as a full URL, such as `https://app.example.com/callback`, also accepted every subdomain, such as `https://evil.app.example.com/callback`. Anyone who controls a subdomain could receive authorization codes. | A full URL now matches only its own scheme, host, port and path ([RFC 9700](https://www.rfc-editor.org/rfc/rfc9700#section-2.1)). Host patterns without a scheme, such as `example.com` or `.example.com`, still allow subdomains on purpose. |
| A database syncer connected through an SSH tunnel accepted any server key ([GO-2024-3026](https://pkg.go.dev/vuln/GO-2024-3026)). A machine on the network path could pose as the server, receive the SSH password and read the database traffic. | Syncers have an **SSH host key** setting and Casdoor verifies the server against it. Without a key, Casdoor refuses to open the tunnel. |
| The web application firewall library Coraza 3.3.3 could skip rules when a request had many parameters ([CVE-2026-41510](https://github.com/advisories/GHSA-6r3q-mjv7-xr8m)) and allowed forged audit log lines ([CVE-2026-41504](https://github.com/advisories/GHSA-prpw-wwv7-xjjr)). | Updated to Coraza 3.8.1. |

Regression tests cover the redirect rules and the SSH host key check with a
real SSH server. The image build runs them under the Go race detector.

## Casdoor advisories already fixed upstream

The OSV records list old Casdoor version numbers and often no fixed version, so
a scanner flags them for every release. The code of this version contains these
fixes:

| Advisory | Where the fix is |
| --- | --- |
| [Token exchange across organizations](https://github.com/advisories/GHSA-c9w5-qp6m-m395) | `object/token_oauth.go`: the subject token's user must belong to the application's organization, unless the application is shared. |
| [Revoked token accepted for exchange](https://github.com/advisories/GHSA-339w-3hqm-9pjc) | `object/token_oauth.go`: the stored token record must exist and be active. |
| [SAML signing certificate taken from the response](https://github.com/advisories/GHSA-fwgq-j9r9-qjgr) | `object/saml_sp.go`: only the provider's configured certificate is trusted. |
| [SAML audience not checked](https://github.com/advisories/GHSA-3w4h-g9f5-j84p), [SAML validity period not checked](https://github.com/advisories/GHSA-rgq2-93gj-ffxg) | `object/saml_sp.go`: the audience and the validity period are enforced. |
| [Unsolicited or replayed SAML response](https://github.com/advisories/GHSA-mfvp-7p3v-x9mh) | `object/saml_sp.go` and `controllers/auth.go`: the response must answer the request this browser session sent, the request ID is used once, and the provider is reloaded and must still be enabled. |
| [MFA skipped when linking a social account](https://github.com/advisories/GHSA-gv4m-v8c8-hr3g) | `controllers/auth.go`: the linking path checks MFA before signing in. |
| [File written outside the storage folder](https://github.com/advisories/GHSA-rmxx-v9rj-vpvg) | `storage/local_file_system.go` keeps every path inside the storage folder; `controllers/resource.go` keeps organization administrators inside their own upload paths. |
| [Script in application HTML](https://github.com/advisories/GHSA-w799-7525-rpr6) | `object/application_util.go`: only a global administrator can change custom HTML. Form CSS is inserted as a stylesheet, where it cannot run script. |
| [Webhook requests to internal addresses](https://github.com/advisories/GHSA-p8c7-hjc4-gwf8) | `object/webhook_util.go`: webhooks of organizations other than `built-in` can reach only public addresses. |
| [Open redirect](https://github.com/advisories/GHSA-mj24-pqx2-6788) | `object/application_util.go`: redirect URIs must match the application's list; this version also removes the subdomain match described above. |
| Older records (SQL injection, file write and deletion, SCIM authorization, CSRF, CORS, reflected script, organization editing) | Fixed in Casdoor versions between 1.13.1 and 2.63.0, all older than `v4.15.0`. |

## Remaining findings

| Finding | Why it is accepted |
| --- | --- |
| `golang.org/x/crypto` [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932) | Affects only the `openpgp` package, which Casdoor does not import. No fixed version exists yet. |
| `aws-sdk-go` [GO-2022-0635](https://pkg.go.dev/vuln/GO-2022-0635), [GO-2022-0646](https://pkg.go.dev/vuln/GO-2022-0646) | Affect only the S3 encryption client, which Casdoor does not import. |
| `braces` 3.0.3 [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | Used only by the frontend build tools; it is not in the served pages. No fixed version exists yet. |
| `xlsx` 0.20.3 [GHSA-4r6h-8v6p-xvw6](https://github.com/advisories/GHSA-4r6h-8v6p-xvw6), [GHSA-5pgg-2g8v-p4x9](https://github.com/advisories/GHSA-5pgg-2g8v-p4x9) | SheetJS fixed both in 0.19.3 and 0.20.2 through its own distribution. The npm records have no fixed version, so scanners report every version. |

## Limits

- Organization administrators can still style their login pages with CSS.
  The CSS cannot run script, but it can load images from other sites.
- A global administrator can configure webhooks of the `built-in`
  organization to reach internal addresses, and can choose the storage folder.
- Host patterns without a scheme match subdomains by design. Register full URLs
  when a client has a single callback.
- This review covers known advisories and the code paths they name. It does not
  replace an independent review of the whole application.

## Repeat the scans

```sh
python3 scripts/prepare-source.py
cd .local/source
go run golang.org/x/vuln/cmd/govulncheck@v1.8.0 ./...
osv-scanner scan source -L web/yarn.lock
trivy image casdoor-integration:candidate
```
