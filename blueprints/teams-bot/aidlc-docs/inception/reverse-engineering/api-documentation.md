# API Documentation

## REST APIs

**None.** The repository defines no HTTP API, no API Gateway, no Lambda function URL, and no
load balancer. Nothing in it accepts an inbound request.

This is the single most consequential finding for the Teams chatbot work: Azure Bot Service
delivers Bot Framework activities by **POSTing to a public HTTPS messaging endpoint**, and no
such ingress exists anywhere in this repository. It would be the first.

## Internal APIs

The only executable code with a callable surface is `pipeline/validate_stacks.py`. It is a
script, not a library — nothing imports it — but its functions constitute the contract that
every new template must satisfy.

### `pipeline/validate_stacks.py`

- **`load_registry(path) -> dict`**
  - **Parameters**: path to `pipeline/stacks.yml`.
  - **Returns**: the parsed registry mapping stack keys to their metadata.
  - **Purpose**: Read the declared set of templates and how each is deployed.

- **`discover_templates(root) -> set[str]`**
  - **Parameters**: repository root.
  - **Returns**: repository-relative paths of every `.yml`/`.yaml` file whose contents
    include the literal `AWSTemplateFormatVersion`.
  - **Purpose**: Establish ground truth from the filesystem. Note the detection rule — a
    CloudFormation template that omits `AWSTemplateFormatVersion` is invisible to the
    validator and will silently escape registration.

- **`pipeline_deployed_templates(pipeline_yml) -> set[str]`**
  - **Parameters**: path to `pipeline/pipeline.yml`.
  - **Returns**: template paths extracted by regex from `GitRepositoryArtifact::([^\s\'"]+)`
    occurrences.
  - **Purpose**: Discover which templates the pipeline actually deploys, without
    interpreting CloudFormation intrinsics. Because it is a regex over text, a `TemplatePath`
    assembled dynamically (via `!Sub`, for instance) would not be seen.

- **`check_pipeline_actions(registry, pipeline_paths) -> list[str]`**
  - **Parameters**: the registry, and the set of pipeline-referenced template paths.
  - **Returns**: error strings; empty on success.
  - **Purpose**: Enforce the registry/pipeline mirror in **both** directions — a
    `deployed_by: pipeline` entry with no matching action, and an action with no registry
    entry. The first direction is the important one: without it, a blueprint can be
    registered, pass review, produce a fully green pipeline run, and deploy nothing.

- **`main() -> int`**
  - **Returns**: process exit code; non-zero fails `tools/check` and therefore the pull
    request.

### `tools/check`

- **Invocation**: `tools/check`, no arguments.
- **Behaviour**: Runs `cfn-lint` over all templates (with the mandatory literal `--`
  separator before the paths), then `validate_stacks.py`. Non-zero exit on any failure.
- **Contract**: This is the only supported form. The bare `cfn-lint` and
  `python pipeline/validate_stacks.py` forms fail on a clean machine and must not be
  documented or run.

## Data Models

The repository's "data models" are CloudFormation parameter contracts and one YAML registry
schema. There are no application data models, no database schemas, and no serialization
formats.

### Blueprint Template Parameter Contract

Derived from `blueprints/hello-world/infra/hello-world.yml`. Every blueprint template
declares these; the pipeline passes every one explicitly.

| Field | Type | Constraint | Source | Purpose |
| --- | --- | --- | --- | --- |
| `Application` | String | `AllowedPattern` caps at 10 characters | pipeline | Deployment family; always `aidlc`. The 10-character cap is why it is not the repository name. |
| `Environment` | String | `[a-z0-9]{1,4}` — 4 chars, no hyphens | pipeline | The tracked branch name. Part of every stack name and of the IAM resource prefix. |
| `Owner` | String | — | pipeline | Accountable human or team; becomes `cornell:owner`. |
| `BlueprintVersion` | String | `[0-9]+\.[0-9]+\.[0-9]+`, default `0.1.0` | template default, bumped in the PR that changes the blueprint | Becomes `cornell:blueprint-version`. |
| `SourceCommitId` | String | — | pipeline, via `#{GitRepository.CommitId}` | Provenance; recorded in the deployment marker. |

- **Validation**: Enforced by CloudFormation `AllowedPattern` at deploy time and by
  `cfn-lint` at review time. The `Environment` pattern is the tightest and the most
  load-bearing: it is deliberately narrow because the value is interpolated into IAM resource
  ARNs.

### Required Tag Set

Every resource in every blueprint carries all four. `cornell:blueprint` is hardcoded per
template; the rest derive from parameters.

| Tag | Value | Notes |
| --- | --- | --- |
| `cornell:owner` | `!Ref Owner` | From the stack parameter. |
| `cornell:blueprint` | literal, e.g. `hello-world` | Hardcoded in the template. |
| `cornell:blueprint-version` | `!Ref BlueprintVersion` | Bumped in the PR that changes the blueprint. |
| `cornell:deployment-id` | `!Sub '${Application}-${Environment}-<name>'` | Matches the stack name. |

- **Relationships**: These four feed campus inventory and the cost dashboard; an untagged
  resource is invisible to both.
- **Validation**: Convention only — no automated check enforces tag presence today. This is a
  gap the validator does not cover.
- **Serialization asymmetry**: most resources take `Tags` as a **list** of `Key`/`Value`
  objects; **`AWS::SSM::Parameter` takes `Tags` as a map**. The reference blueprint carries an
  inline comment at that spot for exactly this reason.

### `pipeline/stacks.yml` Registry Entry

| Field | Type | Purpose |
| --- | --- | --- |
| stack key | String | Logical name, e.g. `hello-world`. |
| `template` | String | Repository-relative path to the CloudFormation template. |
| `deployed_by` | Enum: `pipeline` \| `manual` | `pipeline` requires a matching action in `pipeline.yml`; `manual` means an administrator deploys it by hand, once. |

- **Validation**: `validate_stacks.py`. A template on disk with no entry fails; an entry with
  no file fails; a `pipeline` entry with no action fails; an action with no entry fails.

## Bot Framework API Surface (external, not yet implemented)

Documented here because it is the API contract the Teams chatbot must satisfy, and because
nothing in the repository speaks it today. Sourced from the research documents in
`docs/teams-chatbot-docs/`. **No credential values are reproduced.**

### Inbound: messaging endpoint (to be built)

- **Method**: `POST`
- **Path**: the bot's messaging endpoint — a public HTTPS URL registered on the Azure Bot
  Service resource.
- **Purpose**: Receive Bot Framework `Activity` objects from Teams.
- **Request**: JSON `Activity`. Relevant types: `message` (carries `text`),
  `conversationUpdate` (carries `membersAdded`/`membersRemoved`, no `text`), and
  `installationUpdate` (no `text`). Any handler must tolerate an activity with no `text`.
- **Response**: `200 OK`, returned quickly. A slow or non-200 response causes Teams to retry.
- **Authorization**: `Authorization: Bearer <JWT>`, which must be validated, not trusted:
  RS256 signature against the JWKS at
  `https://login.botframework.com/v1/.well-known/keys`; `iss` equal to
  `https://api.botframework.com`; `aud` equal to the bot's client ID; `exp`/`nbf` within a
  five-minute skew; and the `serviceurl` claim (lowercase `u`) matching the request body's
  `serviceUrl`.

### Outbound: reply to an activity

- **Method**: `POST`
- **Path**: `{serviceUrl}/v3/conversations/{conversationId}/activities/{activityId}`
- **Purpose**: Reply in the thread of the received activity. Omitting the trailing
  `/{activityId}` starts a new (proactive) message instead.
- **Request**: JSON `Activity` with `type: "message"` and `text`.
- **Authorization**: A bearer token obtained via the OAuth 2.0 `client_credentials` grant
  with `scope: https://api.botframework.com/.default`. The client secret must be resolved
  from AWS Secrets Manager at runtime and must never appear in any repository file.

### Identifier conventions

- Bot IDs are prefixed `28:`; human user IDs are prefixed `29:`.
- Personal conversation IDs look like `a:xxx`; channel and group conversation IDs look like
  `19:xxx@thread.tacv2`.

### Known constraints carried forward from the research

- Multi-tenant bot creation is unavailable after 31 July 2025; single-tenant or a
  user-assigned managed identity is required.
- Bot Framework SDK v4 support ended 31 December 2025; the successor is the Microsoft 365
  Agents SDK. `dev.botframework.com` is legacy — Azure Bot Service is the supported path.
- Sideloading reaches personal scope only. Group chat and channel use require publishing to
  the organization with Teams admin approval — a hard prerequisite, not an optimization.
- Manifest v1.25 requires a top-level `"supportsChannelFeatures": "tier1"` when `team` scope
  is used. The Developer Portal GUI does not expose it, and the portal validator wrongly
  rejects it when placed inside the `bots` object.
- The Developer Portal's "Application (client) ID" field under Basic information maps to
  `webApplicationInfo.id` (single sign-on) and must be left blank; populating it causes a
  silent Teams install failure.
- Replying in a channel thread without an `@mention` requires the resource-specific consent
  permission `ChannelMessage.Read.Group`, declared in the manifest and consented by a team
  owner at install time. Adding it **requires reinstalling the app** in the team. It needs no
  Entra admin consent.
- The alternative delivery mechanism, Microsoft Graph change notifications, has a maximum
  subscription lifetime of 4,320 minutes (three days), requires a `lifecycleNotificationUrl`
  for anything over an hour, requires a synchronous `validationToken` echo within ten
  seconds, and optionally an RSA certificate for `includeResourceData: true`. The research
  recommends resource-specific consent with Bot Framework delivery instead.
