# Personas — `dashboard` Blueprint (Cost & Usage Dashboard)

**Stage**: INCEPTION → User Stories, Part 2 (Generation)
**Date**: 2026-08-03
**Persona set**: single persona, per story plan Q1 = D

---

## P-01 — Dashboard viewer

**Label**: Dashboard viewer

**Role**: Anyone reaching the dashboard from an allowlisted Cornell network connection. In practice
this covers platform/AI Platform team engineers, workshop organizers, and campus builders — but
**v1 draws no distinction between them**, because everyone inside the WAF allowlist sees exactly
the same data with exactly the same permissions.

**Goals**
- See which AWS resources the platform has deployed, and how they're tagged
- Attribute resources to a deployment, an owner, or a blueprint via the `cornell:*` tags
- Find resources that are missing required tags, since an untagged resource is invisible to
  inventory and cost attribution
- Know how old the data is before drawing a conclusion from it
- Pull the same data as JSON when a browser isn't the right tool

**Motivations**
- Tag hygiene is the precondition for cost attribution — a gap found now is cheaper than a gap
  found in a bill
- During the workshop (Aug 3–4, 2026) many people deploy into one shared account, and the only
  thing distinguishing their resources is the `cornell:*` tag set
- Nobody in this population has an AWS console login for the deployment account, so without this
  dashboard there is no way to see what's there

**Characteristics**
- Technically literate, but not necessarily an AWS expert
- Reads the dashboard occasionally and briefly, not as a monitoring surface
- Will act on what they see (fix a tag, chase an owner), so wrong data is worse than absent data

**Technical access level**
- **No AWS console access** to the deployment account, and no AWS credentials for it
- **No CLI/SigV4 capability** assumed — this is why the requirements rejected an
  IAM-authenticated-only API (see the supersession chain in `requirements.md` §2)
- Write access to the platform is PR-only, via GitHub, and is not exercised through this dashboard —
  the dashboard is strictly read-only

**How they reach the dashboard**
- A browser, over HTTPS, to a CloudFront distribution
- Admission is decided by **network position, not identity**: an AWS WAF web ACL with an IP-set
  allowlist of Cornell's known ranges, default action **block**
- There is **no login**. No Cognito user pool, no identity pool, no per-user session, no roles.
  The dashboard cannot tell one viewer from another, and does not try to

---

## What this persona set deliberately excludes

**Audiences knowingly excluded in v1**
- Anyone off Cornell's allowlisted network ranges — **including a legitimate Cornell user on a
  non-allowlisted connection** (home ISP without VPN, conference wifi, a phone on cellular). This
  is a real usability cost of choosing a network boundary over an identity boundary, accepted
  deliberately.
- Anyone outside Cornell entirely.
- Automated callers from outside the allowlist — a CI job or hosted integration on a
  non-allowlisted egress IP cannot reach the API, even if it is legitimately Cornell's.

**Distinctions v1 does not make**
Because there is one persona and no identity layer, the dashboard cannot and does not:
- Show a campus builder only their own resources
- Give platform engineers a view that organizers don't have
- Attribute a page view or an API call to a person
- Support any per-user or per-role access control

Collapsing to one persona is coherent with v1's design, not a simplification of it: with a network
boundary and no identity, there is genuinely nothing to differentiate. It does mean that **the
moment a requirement appears for "builders see only their own resources", both this persona set and
the access model need revisiting together** — that requirement cannot be met by a CIDR list.

## Relationship to the deferred identity work

`requirements.md` §4.6 records "no application-level authentication" as an accepted exception to
SECURITY-13, compensated by the WAF allowlist, and driven by `CLAUDE.md` listing the Azure/Entra
Terraform stage as deliberately not built. This persona is the shape that exception takes in
practice: one undifferentiated viewer, admitted by IP.

If Entra federation is built later, this persona is expected to split along the lines v1 collapsed
— platform operator, workshop organizer, campus builder — and the enabler stories' operator-facing
concerns (logging, alarms, monitoring) would gain a persona to attach to, which in v1 they lack.

---

## Amendment (2026-08-07) — the telemetry/cost pass adds goals, not a persona

`inception/amendments/telemetry-fr9-2026-08-07.md` adds FR-9 (usage telemetry) and FR-10 (cost).
The natural reading is that this introduces a new audience — someone justifying spend, or judging
whether a deployed application is worth keeping. **It does not add a persona**, and the reason is
structural rather than a simplification: admission is still by network position with no identity
(FR-4.5, the SECURITY-13 exception), so the dashboard still cannot tell a budget owner from a
builder. One undifferentiated viewer remains correct.

What it does add is **two goals** to P-01, from the Round-1 Q4 answer *"usage metrics to justify
cost; feedback for business processes; metrics to determine value / how useful the system is"*:

- Know what the platform is costing, broken down by application and deployment, without a Billing
  console login — which nobody in this population has, exactly as they have no AWS console login
- Judge whether a deployed application is actually used, and at what cost per unit of use

Both are read-only and both are satisfied by the same undifferentiated view, so the persona's
technical access level, admission path, and excluded audiences are all unchanged.

**One caution this sharpens.** "Wrong data is worse than absent data" was already recorded above as
a characteristic. It matters more now: this viewer will act on a *money* figure, and FR-10.6's model
cost is an **estimate** derived from token counters, not billed spend. That is why NFR-T1 requires
estimates to remain visually distinguishable from billed figures — the persona's disposition to act
on what they see is the reason the labelling is a requirement rather than a courtesy.
