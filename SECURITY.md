# Security Policy

## Supported versions

Only the latest published `cldc` minor version receives security fixes.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |
| < 0.1   | No        |

## Reporting a vulnerability

**Do not open public issues or PRs for security vulnerabilities.**

Send a private report to the repository owner via one of:
- GitHub private vulnerability reporting: https://github.com/AbdelStark/claude-md-compiler/security/advisories/new
- Email: Use the address on the repository owner's GitHub profile

Include:
1. A clear description of the issue.
2. Reproduction steps or a proof-of-concept.
3. The `cldc --version` affected.
4. The impact you believe the issue has (information disclosure, privilege escalation, denial of service, etc.).
5. Any suggested remediation.

We will acknowledge receipt within 7 days and provide a disclosure timeline.

## Scope

`cldc` is a local-first policy compiler and enforcer. It does not execute arbitrary code by itself, does not make network calls, and does not manage secrets. In-scope concerns include:
- Path traversal or repo-root escape via crafted policy sources or evidence payloads.
- Schema-validation bypass that causes a stale or malicious lockfile to be treated as fresh.
- Denial-of-service via pathological policy documents (unbounded rule counts, catastrophic backtracking in globs, etc.).

Out of scope:
- Third-party tools invoked via `require_command` rules. Those are the responsibility of the repo that chooses to enforce them.
- The contents of user-authored presets under `policies/`.

## Coordinated disclosure

We prefer coordinated disclosure. We will credit reporters in the `CHANGELOG.md` release notes unless you prefer to remain anonymous.
