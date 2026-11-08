<!-- Generated mirror of SECURITY.md; edit canonical source first. -->

# Security policy

[Documentation home](https://github.com/NewBww/knowledge-hub/wiki/Home) · [Status and limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation)

**On this page**

- [Supported scope](#supported-scope)
- [Report privately](#report-privately)
- [Boundaries worth reporting](#boundaries-worth-reporting)
- [Secrets and incident response](#secrets-and-incident-response)

## Supported scope

Security fixes target the current maintained source/default branch and explicitly supported releases. There is no promised support window for historical local previews. A local-first design is not a sandbox against malicious software running as your OS account.

## Report privately

Do **not** post credentials, private knowledge, databases, exploit payloads with personal content or sensitive logs in public issues. Use this repository's **Security → Report a vulnerability** option if private vulnerability reporting is enabled. If it is unavailable, open a minimal public issue requesting a private contact channel **without vulnerability details**, and wait for a maintainer-provided private route. No email address or response-time SLA is invented here.

Include the affected version/commit, installation mode, impact, minimal synthetic reproduction and any relevant sanitized error. Clearly identify whether a test used source, a frozen app or a live provider. Do not test against someone else's knowledge, account, endpoint or production service without authorization. Coordinate disclosure and remediation with the maintainer; no bounty is promised.

## Boundaries worth reporting

Human-only approval bypass; agent capture-access bypass; secret exposure; Host/Origin/session failures; unsafe file traversal/symlinks; active-content execution; provider/tool isolation failures; unsigned or wrong-publisher update acceptance; unsafe migration or bundle leakage.

## Secrets and incident response

If a credential is exposed, stop processing, revoke/rotate it with the issuing service and review downstream access. Removing a Git file or capture does not revoke a credential or remove historical/remote copies. Preserve necessary evidence privately and sanitize reports. Signing-key compromise requires a reviewed authenticated recovery plan, never silent replacement of the pinned publisher key.

See [privacy boundaries](https://github.com/NewBww/knowledge-hub/wiki/Privacy-and-Context), [connections](https://github.com/NewBww/knowledge-hub/wiki/Connections) and [release trust gates](https://github.com/NewBww/knowledge-hub/blob/main/docs/releasing.md). Application MIT licensing does not certify third-party binary redistribution or account/provider privacy.
