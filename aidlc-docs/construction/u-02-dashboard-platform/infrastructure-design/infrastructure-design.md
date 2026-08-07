# Infrastructure Design — U-02 Dashboard Platform

**Phase**: CONSTRUCTION → Infrastructure Design (artifact 1 of 2)
**Date**: 2026-08-04
**Decisions**: `construction/plans/u-02-dashboard-platform-infrastructure-design-plan.md` (Q1–Q7 all **A**)

This maps the 12 logical components of `nfr-design/logical-components.md` to concrete `us-east-1` CloudFormation
across **two templates**. It is the resource inventory and the properties that carry an NFR requirement — not the
YAML. The YAML is Code Generation; where a property value is a Code-Generation choice it is called out as such.

**Scope note carried from the survey**: the Lambda/IAM/tagging/`HasImage` shapes mirror `tiny-chatbot.yml`; the
**entire serving layer (CloudFront, WAFv2, API Gateway HTTP API, OAC, ResponseHeadersPolicy) is net-new to this
repo** — there is no template to copy, so each is specified from the AWS resource reference, not a local precedent.

---

## 1. Template split (Q1) and the stateful boundary

| Template | Owns | Why here |
|---|---|---|
| **`dashboard-storage.yml`** | `SnapshotBucket`, `SiteBucket`, the snapshot bucket's TLS-only policy | The **stateful data**. A separate stack so an app-stack update that replaces a resource can never threaten the buckets (the reason `dashboard-marker.yml` already records). |
| **`dashboard.yml`** | Both Lambdas + roles + log groups, HTTP API, CloudFront + OAC + ResponseHeadersPolicy, WAF (WebACL + 2 IPSets), EventBridge schedule, alarms, **the site bucket's OAC+TLS policy** | Everything replaceable. The site `BucketPolicy` lives here (Q2) so the OAC→distribution reference is *local*, needing no export. |

Both templates carry the standard parameter set from `tiny-chatbot.yml` — `Application` (`[a-z0-9-]{1,10}`),
`Environment` (`[a-z0-9]{1,4}`), `Owner`, `BlueprintVersion` (default bumped in the PR that changes the blueprint),
`DeploymentName` (default `dashboard`) — and derive `cornell:deployment-id` as
`!Sub '${Application}-${Environment}-${DeploymentName}'`. Every taggable resource carries the four `cornell:*` tags
as a **list** of `Key`/`Value` (list form — these are not `SSM::Parameter`/`Bedrock::KnowledgeBase`, which take a map).

---

## 2. `dashboard-storage.yml` — the two buckets (L-2, L-7)

| Logical | Resource | Key properties | Carries |
|---|---|---|---|
| **L-2 Snapshot bucket** | `AWS::S3::Bucket` | Name `!Sub '${Application}-${Environment}-dashboard-snapshot'`; `VersioningConfiguration: Enabled`; `BucketEncryption` SSE-S3; `PublicAccessBlockConfiguration` all true; `LifecycleConfiguration`: **noncurrent versions expire 30 d, current never expires** (TSD-13) | SR-01, SR-02, D-1, D-2, D-7, SEC-1, SEC-9 |
| — | `AWS::S3::BucketPolicy` (snapshot) | Single statement: **deny** any request where `aws:SecureTransport = false` | SEC-9 (TLS-only) |
| **L-7 Site bucket** | `AWS::S3::Bucket` | Name `!Sub '${Application}-${Environment}-dashboard-site'`; `VersioningConfiguration: Enabled`; SSE-S3; **BPA all true** (private — served only via OAC); `LifecycleConfiguration`: **objects not modified for 30 d expire** (TSD-13, D-4). **No website hosting, no public policy.** | ER-05, D-3, D-4, FR-4.2 |

The **site bucket's policy is not here** — it grants CloudFront (OAC) and must reference the distribution ARN, so it
lives in `dashboard.yml` (§3.5). One `AWS::S3::BucketPolicy` per bucket, so that policy also carries the site
bucket's TLS-only deny.

Outputs: `SnapshotBucketName`, `SiteBucketName` as **plain outputs, not `Export:`ed** (the repo has no exports; the
app stack reconstructs both names by convention anyway).

---

## 3. `dashboard.yml` — the application stack

### 3.0 Parameters and conditions (net additions over the skeleton)

- **`CollectorImageUri`**, **`ApiImageUri`** — two image params (the collector/api Dockerfile-target split), each
  `Default: ''`, pattern `.{0,512}`, fed the digest from its Build action.
- **`AllowedIpv4Cidrs`**, **`AllowedIpv6Cidrs`** — `CommaDelimitedList`, the WAF allowlist (Q5). `AllowedIpv6Cidrs`
  may be empty.
- **`LogLevel`** — `Default: INFO` (drives `os.environ["LOG_LEVEL"]`, NFR §4).
- `Conditions`: **`HasCollectorImage`** / **`HasApiImage`** — `!Not [!Equals [!Ref …, '']]`, applied independently so
  a partial build still deploys (TSD-14). The API GW integration and schedule are also `HasImage`-gated.

### 3.1 Compute — the two Lambdas (L-1, L-3)

| Logical | Resource | Key properties | Carries |
|---|---|---|---|
| **L-1 Collector** | `AWS::Lambda::Function` (`Condition: HasCollectorImage`) | `PackageType: Image`, `Code.ImageUri: !Ref CollectorImageUri`, `Architectures: [arm64]`, `MemorySize: 512`, `Timeout: 120` (TSD-8), **`ReservedConcurrentExecutions: 1`** (S-1), `LoggingConfig.LogGroup: !Ref CollectorLogGroup`, env `LOG_LEVEL`, `SNAPSHOT_BUCKET`, `PAGE_LIMIT`, `DEADLINE_SAFETY_MS` | CR-01..CR-06, P-1, P-3, S-1, R-1 |
| **L-3 Read API** | `AWS::Lambda::Function` (`Condition: HasApiImage`) | as above but `Timeout: 10`, **`ReservedConcurrentExecutions: 10`** (Q6, S-2), env `LOG_LEVEL`, `SNAPSHOT_BUCKET`, `STALE_THRESHOLD_S` | AR-01..AR-08, P-2, P-4, R-2 |

Each has an explicit `AWS::Logs::LogGroup` — `/aws/lambda/${Application}-${Environment}-${DeploymentName}-collector`
and `-api` — `RetentionInDays: 30` (TSD-12, D-5), tagged, deleted with the stack.

### 3.2 IAM — two least-privilege roles (SR-02, SEC-6)

| Role | Grants (nothing more) |
|---|---|
| **Collector role** | `logs:CreateLogStream`+`logs:PutLogEvents` on **its own** log group ARN; `tag:GetResources` (Resource Groups Tagging API — resource `*`, the API takes no resource-level scoping); `s3:PutObject` on the **single** snapshot object ARN `…:${snapshot-bucket}/<key>` only |
| **API role** | logs on its own group ARN; `s3:GetObject` on the **same single** snapshot object ARN only |

Both reference the snapshot bucket by convention name (`!Sub`), not import. Neither is bucket-wide — the asymmetric,
key-scoped pair is the SR-02 / SEC-6 boundary. EMF metrics need **no** IAM (NFR §5) — they are log lines.

### 3.3 Messaging — the collector schedule (L-8)

`AWS::Events::Rule`, `ScheduleExpression: rate(1 hour)`, `Target` → collector `Arn` with
**`RetryPolicy.MaximumRetryAttempts: 0`** and **no DLQ** (Q6/NFR §7). An `AWS::Lambda::Permission` lets
`events.amazonaws.com` invoke the collector. Rule and permission are `HasCollectorImage`-gated.

### 3.4 Networking — API Gateway HTTP API (L-4)

- `AWS::ApiGatewayV2::Api` — `ProtocolType: HTTP`.
- `AWS::ApiGatewayV2::Integration` — `AWS_PROXY`, `PayloadFormatVersion: 2.0`, target the API Lambda
  (`HasApiImage`-gated).
- `AWS::ApiGatewayV2::Route` — routes the API's closed five-route table; **the API owns the `/api` prefix** so
  CloudFront can forward `/api/*` verbatim (Part A2 finding 4).
- `AWS::ApiGatewayV2::Stage` — `$default`, `AutoDeploy: true`, `DefaultRouteSettings` **`ThrottlingRateLimit: 20`,
  `ThrottlingBurstLimit: 40`** (TSD-10, P-5), `AccessLogSettings` → an access log group (30 d).
- `AWS::Lambda::Permission` for `apigateway.amazonaws.com`.

### 3.5 Networking — CloudFront + OAC + response headers (L-5) and the site bucket policy

- `AWS::CloudFront::OriginAccessControl` — `SigningBehavior: always`, `OriginAccessControlOriginType: s3`.
- `AWS::CloudFront::Distribution` — **two origins**:
  1. **Site origin** — the site bucket regional domain (`!Sub '${…}-dashboard-site.s3.${AWS::Region}.amazonaws.com'`),
     `OriginAccessControlId` set, no public access. **Default cache behavior** → this origin, caching **on** (P-6):
     hashed assets long-TTL, `index.html` short (TSD-11).
  2. **API origin** — the HTTP API default endpoint (`!Sub '${HttpApi}.execute-api.${AWS::Region}.amazonaws.com'`),
     `CustomOriginConfig` HTTPS-only. **`/api/*` cache behavior** → this origin, **caching disabled**
     (`CachePolicyId` = managed *CachingDisabled*), all headers/query forwarded (ER-03).
  - `ResponseHeadersPolicyId` on both behaviors → the policy below.
  - `WebACLId` → the WAF WebACL ARN (§3.6).
  - `ViewerCertificate`: **default CloudFront certificate** (`*.cloudfront.net`) — no custom domain in scope
    (Part A2 finding 5); `ViewerProtocolPolicy: redirect-to-https`.
- `AWS::CloudFront::ResponseHeadersPolicy` (Q7) — `ContentSecurityPolicy`:
  `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'`;
  plus `StrictTransportSecurity` (`max-age=63072000; includeSubDomains; preload`), `ContentTypeOptions: nosniff`,
  `ReferrerPolicy: no-referrer`. **Imposes on Code Generation**: the UI emits no inline `<script>`/`<style>` and no
  inline `style=` attributes; true compliance is a **`deployed`-only** check (SEC-2, P-6 — §9 of the patterns doc).
- **`AWS::S3::BucketPolicy` on the site bucket** (here, Q2): allow `s3:GetObject` to principal
  `cloudfront.amazonaws.com` **only when** `aws:SourceArn` equals **this** distribution's ARN (local `!Sub` /
  `!GetAtt` — the reason the policy is in this stack); plus the `aws:SecureTransport = false` deny. One policy, both
  statements (Part A2 finding 3).

### 3.6 Networking — WAF (L-6, Q5)

- `AWS::WAFv2::IPSet` **IPv4** — `Scope: CLOUDFRONT`, `IPAddressVersion: IPV4`, `Addresses: !Ref AllowedIpv4Cidrs`.
- `AWS::WAFv2::IPSet` **IPv6** — `Scope: CLOUDFRONT`, `IPAddressVersion: IPV6`, `Addresses: !Ref AllowedIpv6Cidrs`
  (may be empty; the set still exists so future CIDRs are a param change, not a template change).
- `AWS::WAFv2::WebACL` — `Scope: CLOUDFRONT` (**must be us-east-1** — it is), `DefaultAction: Block`, one allow rule
  matching an **OR** of the two IPSets, `VisibilityConfig` with sampled requests + CloudWatch metrics, WAF logging to
  a 30-day log group (TSD-12 — source IPs are personal data). CLOUDFRONT-scoped WebACLs attach via the
  distribution's `WebACLId`.

### 3.7 Monitoring — alarms (L-9) and the EMF metric namespace (L-11)

- **Metrics (L-11)** — emitted by handler code as **EMF** log records (NFR §5); no CloudFormation resource, no IAM.
  Alarms reference the resulting metrics by namespace/name.
- **Alarms (L-9)** — `AWS::CloudWatch::Alarm`, each `AlarmActions`/`OKActions` → the **reconstructed notify-topic
  ARN** (Q4): `!Sub 'arn:${AWS::Partition}:sns:${AWS::Region}:${AWS::AccountId}:${Application}-${Environment}-notify-topic'`.

| Alarm | Fires on | `TreatMissingData` | Carries |
|---|---|---|---|
| Collector failure | collector `Errors ≥ 1` in an hour, or the collector-failure EMF metric | `breaching` | R-3, OR-01 |
| Stale snapshot | snapshot-age metric > `3 × interval` | `breaching` (R-4) | R-4, A-4 |
| API 5xx | API `5xx`/Lambda `Errors` over threshold | `notBreaching` | R-5 |
| WAF-blocked spike *(optional)* | WAF `BlockedRequests` anomaly | `notBreaching` | R-6 |

`TreatMissingData: breaching` on the collector/stale alarms is load-bearing: a collector that never runs is itself
the failure, so "no data" must alarm (R-4).

---

## 4. Component → resource coverage (reverse check)

| Logical (from `logical-components.md`) | Template · resources |
|---|---|
| L-1 Collector | `dashboard.yml` · Lambda + role + log group + schedule |
| L-2 Snapshot bucket | `dashboard-storage.yml` · bucket + TLS policy |
| L-3 Read API | `dashboard.yml` · Lambda + role + log group |
| L-4 HTTP API | `dashboard.yml` · Api + Integration + Route + Stage + permission |
| L-5 Distribution | `dashboard.yml` · Distribution + OAC + ResponseHeadersPolicy |
| L-6 WAF | `dashboard.yml` · WebACL + 2 IPSets + WAF log group |
| L-7 Site bucket | `dashboard-storage.yml` · bucket; **policy in `dashboard.yml`** |
| L-8 Schedule | `dashboard.yml` · Events::Rule + Lambda permission |
| L-9 Alarms | `dashboard.yml` · CloudWatch::Alarm ×3–4 → notify-topic |
| L-10 Log groups | both Lambda groups + API access + WAF (all 30 d) |
| L-11 Metric namespace | *code-emitted EMF* — no resource |
| L-12 Marker | `dashboard-marker.yml` (exists) — flipped to `pipeline` (deployment-architecture §4) |
| D-a notify-topic | **not created** — ARN reconstructed (Q4) |
| D-b `dashboard.core` | **not created** — imported into both images |

Every logical component lands on a resource (or is explicitly code-emitted / a dependency). No resource exists
without a logical component.

---

## 5. What this stage did **not** decide (routed to Code Generation)

- The two templates' **YAML** and the `blueprint.yaml` manifest naming `dashboard.yml`.
- The **Dockerfile** with `collector` + `api` targets and the UI build.
- Handler/UI **code**, including the CSP-driven "no inline styles/scripts" constraint (Q7) and the API's `/api`-prefixed
  route table (Part A2 finding 4).
- The `pipeline.yml` **actions** and the `stacks.yml` **entries** — specified in `deployment-architecture.md`, written in
  Code Generation.
- Concrete env-var **values** (`PAGE_LIMIT`, `DEADLINE_SAFETY_MS`, `STALE_THRESHOLD_S`) — passed as pipeline
  ParameterOverrides, defaults for hand-deploy only.
