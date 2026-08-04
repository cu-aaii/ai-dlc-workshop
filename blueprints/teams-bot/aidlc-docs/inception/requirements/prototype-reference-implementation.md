# Prototype Reference Implementation — Analysis of the n8n Exploration Workflow

**Created**: 2026-08-03
**Stage**: INCEPTION - Requirements Analysis (research input)
**Source**: `docs/teams bot exploration.json` — n8n workflow `UpYSG156S63vb4HZ`, 8 nodes, exported
**Status**: n8n is **not** the target. Confirmed by the user: *"We are NOT using n8n anymore."*

This workflow is the only end-to-end thing that has actually worked. Its value is not its code —
it is a record of which Bot Framework mechanics were **proven against a live Teams tenant**, which
is exactly the information a from-scratch AWS implementation would otherwise have to rediscover by
trial and error.

Two defects were found in it. Both are the kind that a rewrite would faithfully reproduce if
nobody looked, and one of them is a security control that silently does nothing. They are the most
important content in this note.

---

## 1. The proven flow

```
+--------------------------------------+
|  POST /jdw5-teams-bot-exploration    |   n8n webhook
+------------------+-------------------+
                   |
                   v
+--------------------------------------+
|  Respond 200 OK  (noData, code 200)  |   <-- FIRST, before any work
+------------------+-------------------+
                   |
                   v
+--------------------------------------+
|  Fetch Bot Framework JWKS            |   GET login.botframework.com/v1/.well-known/keys
+------------------+-------------------+
                   |
                   v
+--------------------------------------+
|  Validate JWT                        |   return [] on any failure == drop silently
+------------------+-------------------+
                   |
                   v
+--------------------------------------+
|  Route by body.type                  |
+---+--------------+---------------+---+
    |              |               |
    v              v               v
 message    conversationUpdate  installationUpdate
    |              |             (unwired, ignored)
    v              v
 Send Echo    Build Greeting/Farewell
 Reply              |
                    v
              Send Welcome Message
```

**Text alternative.** An HTTP POST arrives at the n8n webhook. The very first action is to respond
`200 OK` with no body — before any validation or work. Only then does the workflow fetch the Bot
Framework JWKS, validate the inbound JWT (returning an empty result on any failure, which drops
the request silently), and switch on `body.type`. A `message` activity goes to an echo reply. A
`conversationUpdate` goes to a code node that builds a greeting or farewell, then to a send node.
`installationUpdate` has a switch output but no downstream connection — deliberately ignored.

### The single most useful thing this establishes

**`Respond 200 OK` runs first, before validation and before any work.** The prototype is a working
confirmation of the acknowledge-then-continue pattern — which answers **Q8** empirically rather
than theoretically. Teams got its fast acknowledgement; everything else happened after the
response was already sent.

Note the consequence, which is correct but worth stating explicitly: **a forged or invalid request
also receives `200 OK`.** That is not a flaw. The `200` is transport-level acknowledgement to
Azure Bot Service, not an authorization decision. Authorization decides whether to *act*, and a
failed validation simply produces no action. An AWS implementation must preserve this ordering —
returning `401` to Azure Bot Service would cause it to retry a request that will never succeed.

---

## 2. Defect 1 — the `serviceurl` check never executes

This is the important one.

The prototype's validation code contains:

```js
const activityServiceUrl = $('Receive Teams Activity').first().json.body.serviceUrl;
if (payload.serviceUrl && payload.serviceUrl !== activityServiceUrl) return [];
```

The repository's own research document, `docs/teams-chatbot-docs/Teams Bot Setup - Findings
2026-04-06.md:150`, states:

> `serviceurl` — Should match `body.serviceUrl` in the activity (note: lowercase `u` in the JWT
> claim)

The claim is **`serviceurl`**. The code reads **`payload.serviceUrl`**, which is always
`undefined`. And because the condition is guarded by `payload.serviceUrl &&`, an undefined value
makes the whole expression false — so the check is **skipped rather than failed**.

The result is a validation step that reads correctly, passes review, and does nothing.

**Why it matters.** This is the control that prevents an attacker holding a valid Bot Framework
token from POSTing an activity with a `serviceUrl` they control, causing the bot to send its
replies — potentially including retrieved course content — to their endpoint instead of Microsoft's.
Every other check in the function (`iss`, `aud`, `exp`, `nbf`, signature) is a standard OIDC
assertion. This one is the Bot Framework-specific correlation, and it is the reason the
`agentcore-placement-note.md` conclusion holds: a generic JWT authorizer cannot perform it.

**Requirement for the AWS implementation**, and it is a requirement rather than a suggestion:

1. Read the claim as **`serviceurl`**, lowercase.
2. Treat **absence of the claim as a failure**, not a pass. No `claim &&` guard.
3. Compare after normalisation — Bot Framework `serviceUrl` values carry a trailing slash
   inconsistently (see defect 2).
4. This specific behaviour needs a test. It is the one check whose failure mode is invisible, so
   it is the one check that must be proven to reject.

### Related: the app registration must be treated as compromised

The prototype hardcodes the Entra application ID directly in the validation code as the expected
`aud` value. The application ID is not itself a secret — client IDs are public in OAuth. But **the
client secret paired with that application ID is one of the credentials found exposed in the
working tree** and reported at the start of this workflow. Whatever the AWS implementation
validates `aud` against, it should be a **newly issued registration**, not the one from the
research spike, and the value must arrive as a stack parameter or SSM lookup rather than be baked
into code.

---

## 3. Defect 2 — reply URL construction relies on an unguaranteed trailing slash

Both send nodes build the target URL by string concatenation:

```js
body.serviceUrl + 'v3/conversations/' + body.conversation.id + '/activities/' + body.id
```

There is no separator between `serviceUrl` and `v3/`. This works only because Bot Framework
`serviceUrl` values in practice end with `/` — e.g. `https://smba.trafficmanager.net/amer/`. It is
undocumented behaviour being relied upon. If a `serviceUrl` ever arrives without the trailing
slash, the URL becomes `.../amerv3/conversations/...` and every reply fails.

**Requirement**: normalise the base URL — strip any trailing slash, then join with an explicit
`/`. Do this in one place, and use the same normalised value for the `serviceurl` claim comparison
in defect 1, so the two cannot disagree.

---

## 4. Mechanics confirmed correct, and worth carrying over unchanged

These were validated against a live tenant and should be treated as known-good.

| Mechanic | Prototype behaviour | Verdict |
| --- | --- | --- |
| Fast acknowledgement | `200 OK`, `noData`, before any work | Correct. Preserve the ordering. |
| Silent drop on auth failure | Returns empty, no error to caller | Correct. Do not return 4xx to Azure Bot Service. |
| Algorithm confinement | Never reads `header.alg`; hardcodes `RSASSA-PKCS1-v1_5` + `SHA-256` at key import | **Correct, and better than it looks.** This structurally prevents algorithm-confusion attacks. An AWS rewrite using a JWT library must explicitly pin `RS256` to keep this property. |
| `kid` selection | Matches `header.kid` against the JWKS key set | Correct. |
| Clock skew | 300s tolerance on both `exp` and `nbf` | Acceptable. Generous but within normal practice. |
| Bot-vs-human filtering | `membersAdded`/`membersRemoved` filtered on `!id.startsWith('28:')` | Correct, and matches the documented ID convention. Without it the bot greets itself on install. |
| Activity type routing | Explicit switch on `body.type` for `message`, `conversationUpdate`, `installationUpdate` | Correct. `installationUpdate` deliberately unwired. |
| Missing `text` tolerance | `conversationUpdate` path never reads `body.text` | Correct. Only `message` activities carry `text`; a handler that assumes otherwise crashes on install. |
| Reply-to-activity vs new activity | Echo uses `.../activities/{body.id}`; welcome uses `.../activities` | Correct — both forms exercised, and the distinction matters for threading. |
| Outbound auth | OAuth2 client-credentials against the dev tenant | Correct shape. Becomes: secret from Secrets Manager, token from Entra, cached. |

---

## 5. What does not carry over

| Prototype element | Replacement in the AWS target |
| --- | --- |
| n8n webhook node | Lambda function URL — **confirmed acceptable by DevOps, 2026-08-03** |
| n8n Code nodes | Handler code in the Lambda container image |
| n8n Credentials store (`oAuth2Api`, `microsoftTeamsOAuth2Api`) | AWS Secrets Manager — hard constraint |
| Hardcoded client ID in code | Stack parameter or SSM parameter |
| JWKS fetched on **every** request | Cached, with TTL. See below. |
| n8n `Switch` node | Explicit dispatch in the handler |
| Echo response text | Whatever Q3 selects |

### JWKS caching is a new requirement, not a port

The prototype fetches `https://login.botframework.com/v1/.well-known/keys` on **every inbound
activity**. In n8n, at exploration volume, that was invisible. On a per-request Lambda it adds a
full round trip to Microsoft inside the critical path before the bot can act, and it is a
dependency on an external endpoint being reachable on every single message.

Cache the key set with a TTL, and refresh on `kid` miss rather than on a timer alone — a `kid`
that isn't in the cached set is the signal that Microsoft has rotated keys.

### Leftover to not copy

The `Send Echo Reply` node carries **two** credential references — `microsoftTeamsOAuth2Api` and
`oAuth2Api` — but `genericAuthType` selects only `oAuth2Api`. The Teams credential is vestigial
from an earlier iteration. Mentioned only so that nobody reading the export concludes two
credentials are required.

---

## 6. Requirements this analysis contributes

Carried into `requirements.md` when the gate clears:

1. The front door **must** return `200 OK` before performing work, and **must not** return an
   error status on authentication failure.
2. Inbound JWT validation **must** check the `serviceurl` claim, lowercase, against a normalised
   `body.serviceUrl`, and **must fail closed** when the claim is absent.
3. The signature algorithm **must** be pinned to `RS256`; `header.alg` must not be trusted.
4. `serviceUrl` **must** be normalised once and reused for both the claim comparison and reply URL
   construction.
5. Handlers **must** tolerate activities with no `text` field.
6. `membersAdded`/`membersRemoved` **must** be filtered on the `28:` bot prefix.
7. The JWKS key set **must** be cached, with refresh triggered by `kid` miss.
8. The expected `aud` value **must** arrive as configuration, not literal code.
9. A negative test **must** exist proving a mismatched `serviceurl` is rejected.

---

## Provenance note

`docs/teams bot exploration.json` was checked for credentials before analysis and contains none.
It holds an Entra application ID, n8n internal credential identifiers, and an n8n instance hash —
none of which is a secret. The application ID is not reproduced in this note regardless, since the
secret paired with it is among the exposed credentials pending rotation.
