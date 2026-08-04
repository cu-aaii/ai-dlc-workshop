# Services — `dashboard` Blueprint

**Stage**: INCEPTION → Application Design (artifact 3 of 5)
**Date**: 2026-08-03

A *service* here is a unit of behaviour with its own trigger, lifecycle, and failure domain — not a
deployment artifact. Two of them exist, and the whole design rests on their being separate.

---

## Service map

| ID | Service | Trigger | Components | Failure domain |
|---|---|---|---|---|
| S-01 | Collection Service | EventBridge schedule | C-01, C-04, C-02 (write) | Own. Failure leaves the last good snapshot in place. |
| S-02 | Query Service | HTTP request via C-07 | C-07, C-03, C-04, C-05, C-02 (read), C-06 | Own. Failure means no answers, but no data loss. |

They share exactly one thing: the snapshot object (C-02). That is the entire coupling surface.

---

## S-01 — Collection Service

**What it is for**: the account's tagged inventory becomes knowable without anyone opening a console.

**Lifecycle**
1. EventBridge fires on the configured interval (a stack parameter — FR-2.3)
2. C-01 paginates the Tagging API to exhaustion
3. C-04 normalizes, stamps, and serializes
4. One `PutObject` to C-02
5. Metrics emitted; the invocation ends

**Success** is a complete snapshot written. **Failure** is an exception — no partial write, ever.

**Why failure is designed this way**: the alternative — write what you got — produces a snapshot that
looks fresh and is wrong. A viewer cannot tell. A stale snapshot, by contrast, is *labelled* stale
(FR-2.2, US-05), so the user knows what they are looking at. Preferring visible staleness to
invisible incompleteness is the central resiliency choice in this blueprint, and it is what
RESILIENCY-15's graceful-degradation intent means concretely here.

**Bounded on purpose**: concurrency 1 (RESILIENCY-09), explicit SDK timeouts, bounded retries with
backoff (RESILIENCY-10), and a page limit whose breach is an error rather than a truncation. A
scheduled job with no bounds is a cost incident waiting for an upstream slowdown.

**Upstream dependency it does not control**: the Resource Groups Tagging API. It can throttle, and it
is eventually consistent — a resource created seconds ago may not appear. This is a property of the
data source, not a defect, and the design's answer is the visible `collected_at` rather than a
promise of real-time accuracy the blueprint cannot keep.

---

## S-02 — Query Service

**What it is for**: turning the stored snapshot into the four views, on demand, for anyone inside the
allowlist.

**Lifecycle**
1. Request arrives at C-07; WAF evaluates it — **default block** (FR-5.1)
2. Path routes: `/api/*` → API Gateway → C-03; everything else → S3 (C-06)
3. C-03 matches the route table; unmatched paths 404 without reading S3
4. C-03 reads the snapshot once and classifies the outcome into three states
5. C-05 derives the requested view; C-03 shapes the response with status code **and** body status
6. C-06 renders it, including the degraded cases

**Read-only by construction.** No method on any component in this service writes anything. FR-2.1 and
US-07 are satisfied by there being no write path to omit, rather than by a check that could be
removed later.

**The cache obligation, again**: `/api/*` no-cache, site behaviour cached. This service is where an
inverted cache policy does its damage — CloudFront would serve a stale JSON body carrying a stale
`collected_at`, and the staleness notice would be correct about the *snapshot* while lying about
*when the reader last looked*. Two viewers would then disagree, which is exactly what Q8 = A's
server-side judgement was chosen to prevent.

**Bounded on purpose**: API Gateway throttling (FR-3.5, SECURITY-12), Lambda concurrency capped
(RESILIENCY-09), SDK timeouts explicit (RESILIENCY-10). The rate limit is not anti-abuse theatre —
the allowlist admits a whole network, so an accidental refresh loop from one workstation is the
realistic threat, not an attacker.

---

## The invariant between them

> **A read never causes a write. A write never waits for a read.**

Which yields:

- Load on S-02 cannot increase Tagging API cost or trip its throttles
- S-01 failing does not make S-02 fail — it makes S-02 *report* staleness
- S-02 failing does not lose data; the snapshot keeps being written
- Neither service needs to know the other is running

The single shared object is the seam, and it is a plain S3 key. That is what makes each one testable
alone: S-01 against a bucket, S-02 against a fixture object, and C-04/C-05 against neither.

---

## Deployment services (supporting, not runtime)

Not services of the blueprint, but the blueprint does not exist without them.

| Concern | Where it lives | Note |
|---|---|---|
| Container image build | New Build stage action in `pipeline/pipeline.yml` | `ContainerBuildProject` and `ContainerRepository` are defined and known-good but **no stage invokes them** — `CLAUDE.md` states this outright, so the finding raised at Workflow Planning is corroborated by the repo's own documentation, not just by my reading of the template. Wiring is a Build stage action plus a Dockerfile. **⚠️ SUPERSEDED — see `inception/amendments/repo-baseline-2026-08-03.md` §A1.2.** A `Build` stage now exists and invokes `ArmContainerBuildProject`; the dashboard adds an **action to an existing stage**, not a new stage. A root `Dockerfile` with one named target per component is the established pattern. |
| Site build + upload | The **same** Build stage action | Q10 = A. Vite build, then `aws s3 sync` to the site bucket. One `pipeline.yml` edit for both, per the execution plan's coordination point. |
| Stack deployment | New BlueprintDeploy action + `pipeline/stacks.yml` entry | FR-7. A registry entry without a matching action deploys nothing while reporting success. |
| Pre-push validation | `tools/check` | Stays `uv`-only. Node is **not** added to it, so template-only contributors are unaffected. |

**Ordering constraint**: the images and the site bundle must exist before the stack that references
them deploys. The Build stage therefore precedes BlueprintDeploy. Getting this backwards yields a
CloudFormation failure about a missing image tag, which reads like a template bug rather than a stage
ordering bug — worth stating because that misdiagnosis is expensive.

**One open sequencing question, deferred to Infrastructure Design**: `aws s3 sync` needs the site
bucket to exist, but the bucket is created by the stack the Build stage precedes. Either the bucket
moves to a separately-deployed stack, or the sync moves after BlueprintDeploy, or the bucket name is
resolved at sync time from a known convention. This is genuinely an infrastructure-topology decision
and is recorded rather than guessed here.
