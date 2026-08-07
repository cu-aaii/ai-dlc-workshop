# Security Test Instructions

**Date**: 2026-08-04. Applicable from U-02 (U-01's security was the boundary grep + no-leak assertion,
both in the normal gate).

## What runs in the gate now

| Control | Requirement | Test / check | Result |
|---|---|---|---|
| No tag value (NetID) in logs | CR-04, SEC-4 | `test_collector_logging.py` | ✅ |
| No exception leaks internals; generic 503 | AR-06 | `test_api_boundary.py` | ✅ |
| Closed route allowlist; unknown → 404 pre-S3 | AR-01, SEC-5 | `test_api_routing.py` | ✅ |
| CSP has no `unsafe-inline` / `unsafe-eval` | SEC-2, ER-04 | `test_template_invariants.py` + built `dist/index.html` has no inline script | ✅ |
| Least-privilege, key-scoped IAM | SEC-6, SR-02 | cfn-lint + review of the two roles in `dashboard.yml` | ✅ (review) |
| TLS-only bucket policies | SEC-9 | present in both templates; cfn-lint clean | ✅ |
| Dependency pinning | US-09, SECURITY-10 | `uv.lock` (hashed) + `ui/package-lock.json` committed; base image digest-pinned | ✅ |

## Dependency posture (US-09 / Q11 = B, stated not hidden)

- **Python**: `uv.lock` with hashes, scanned by the runtime image scan; boto3 is the only added
  runtime dep.
- **npm**: `package-lock.json` pinned, but **not scanned and no SBOM** — the deliberate Q11 = B
  asymmetry (`tech-stack-decisions.md`): React+Vite is the largest tree and gets the least scrutiny,
  defensible because it is build-time only and pinning is the main lever against a *changed* dep.
- The repo default branch's **51 Dependabot findings (20 high)** are the live backdrop to the still-open
  Q13 (whether US-09's fourth acceptance criterion narrows to match Q11 = B). Not this blueprint's, but
  the posture it ships into.

## Deployed-only security checks

- **SEC-7 — the WAF actually admits the right people and blocks the rest.** Deny-by-default with the
  two IPSets is in the template and fails *closed* (placeholder CIDRs admit no one). Whether it admits
  the intended campus ranges is only confirmable against the live distribution from an allowlisted and a
  non-allowlisted client.
- **SEC-2 delivered** — that the CSP header is actually served (not just present in the template) is a
  live-response check; a page with no CSP header is non-conformant even with nothing inline.

No penetration testing is in scope for a WAF-restricted internal dashboard with no identity system
(SEC-8/-13 N/A by construction — no CORS, no credentials, no token).
