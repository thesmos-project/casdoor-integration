# Release status

The current source candidate has **scoped evaluation distribution acceptance**;
see [candidate evidence](CANDIDATE-ACCEPTANCE.md). It is **not approved for production**.
Users can inspect, modify and build it under the published licence. Stable
publishing remains blocked by `release-policy.json`. Candidate publication
requires fresh image checks and the configured release-environment owner review.

Remaining acceptance includes:

- Exact-source advisory review and independent security review.
- Continued dependency and bundled-asset notice/source review when build inputs change.
- Secure initial administrator setup, MFA, recovery and abuse controls.
- Protocol, key rotation, upgrade, rollback and recovery acceptance.
- Public HTTPS, trusted proxy configuration, durable sessions and media storage.
- Resource/capacity acceptance and supported consuming-product release artifacts.

The pinned upstream source initializes built-in demonstration credentials and a
built-in certificate on a new database. The container builder does not yet
replace that behavior. Keep evaluation access local and complete a reviewed
bootstrap process before external exposure. The loopback Compose recipe does
not constitute production deployment instructions.

The Go regressions and frontend checks are meaningful build gates. They do not
replace live OIDC/SAML/SCIM integration acceptance or prove absence of security
issues. No Enterprise implementation or commercial image is distributed here.

Candidate publishing has its own acceptance record under `candidate` in
`release-policy.json`: distribution review, source/patch provenance, and build/runtime
smoke checks. Record its reviewer, evidence and matching `accepted_build_inputs_sha256`
before `--candidate` can pass. RC tags always carry production approval `false`.
Candidate availability does not close any production gate above.

Before stable registry publishing, record all production acceptance gates as true,
identify the reviewer and evidence, and bind `accepted_build_inputs_sha256` to the exact
inputs checked by `scripts/validate-project.py --release`. Stable versions must not
have an RC suffix. Obtain the current
input fingerprint with `python3 scripts/validate-project.py --print-inputs-sha256`;
recording a fingerprint alone does not constitute acceptance. Registry configuration
alone does not open this gate. The accepted image still needs registry signing
and pull verification; a failed signing/verification step means the release must
not be advertised even if an image was pushed.
