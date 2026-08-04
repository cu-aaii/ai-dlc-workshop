# Teams Bot Setup — Findings 2026-04-06

## What We Set Out to Answer

Can a developer without elevated Entra or Teams admin privileges stand up a working Teams bot, and what does the minimal admin involvement look like? Specifically: we wanted to understand the registration plumbing, the user/admin split, and whether **n8n** (a self-hosted workflow automation tool) can serve as the bot's messaging backend in place of the scaffolded TypeScript code.

Short answer: **yes to all three**, with some important nuances.

---

## Architecture

A Teams bot is not a single thing — it's a stack of four connected pieces:

```
Teams App (manifest in Developer Portal)
    └── Bot ID → Entra App Registration (App ID + client secret)
                    └── Azure Bot Service resource
                            └── MsTeamsChannel + messaging endpoint URL
                                        └── Your actual bot logic (n8n, code, etc.)
```

The **Teams app manifest** is the front door for users — it tells Teams the bot's name, description, and which scopes it supports (personal, group chat, channel). The **Entra app registration** and **Azure Bot Service** are the backend plumbing that authenticate messages and route them to your endpoint. The **messaging endpoint** is just an HTTPS URL that receives POST requests.

This means you can swap out the bot logic for anything that can receive an HTTP POST — including n8n.

---

## Tools and Portals Required

A simple list of every place you need to go:

- **`portal.azure.com`** — create the Entra app registration (any tenant member can do this at Cornell); create the Azure Bot Service resource (requires Azure Contributor on the resource group)
- **`dev.teams.microsoft.com`** (Teams Developer Portal) — create the Teams app manifest; sideload the app; submit for org-wide publish
- **`admin.teams.microsoft.com`** (Teams Admin Center) — enable "Upload custom apps" in Setup policies; approve submitted app; set who can install it
- **`teams.microsoft.com`** or the Teams desktop client — test the bot as an end user
- **Azure CLI (`az`)** — useful for inspecting tenant policies (e.g. `allowedToCreateApps`) and creating test users; not required for the main flow

---

## Who Does What

These four privilege axes are **independent** — they can be held by the same person or split across different people.

| Step | Who needs it | What they actually need | Confirmed |
|---|---|---|---|
| Create Entra app registration + client secret | Any tenant member | Nothing special — Cornell's tenant has `allowedToCreateApps: true` | ✓ |
| Create Teams app manifest in Developer Portal | Any tenant member with a Teams license | Teams license (grants access to dev.teams.microsoft.com) | ✓ |
| Create Azure Bot Service resource | Azure Contributor on the resource group | Azure RBAC role — not an Entra or Teams admin role | ✓ |
| Enable sideloading for a user | Teams admin | Teams Admin Center access | ✓ |
| Approve app for org-wide publish + set availability scoping | Teams admin | Teams Admin Center access | ✓ |
| Grant admin consent to MS Graph API permissions | Entra Application Admin or Global Admin | Only required if the bot calls MS Graph APIs | not tested* |

\* Our demo bot has no MS Graph permissions. The consent flow for those is the same as any other Entra app registration — not specific to Teams bots.

**The handoff point** between the developer and whoever has Azure access is the "Use existing app registration" option in the Azure Bot creation form. The developer creates the app registration and provides the App ID (client ID). The Azure-access holder creates the Bot Service resource referencing it. The client secret stays with whoever runs the bot backend — it never needs to pass through Azure portal.

**Note on "admin":** The Azure Contributor role and the Teams admin role are separate things. At Cornell, a developer could have resource group Contributor access without being any kind of tenant admin. Similarly, Teams Admin Center access is its own role. Don't assume these travel together.

---

## Sideloading vs. Org Publish

Two deployment paths exist, and they have different scopes:

**Path 1 — Sideload (developer self-installs)**
- Admin enables "Upload custom apps" in Teams Admin Center → Setup policies (off by default)
- This can be scoped per-user or per-group, so you can grant it to developers without opening it tenant-wide
- Once enabled, the developer can sideload from the Developer Portal or by uploading a zip file directly in Teams
- **Critical limitation:** sideloaded apps are personal-scope only. The app does not appear in group chat app search, channel app search, or "Built for your org." It is not discoverable by other users.

**Path 2 — Publish to org (admin-approved distribution)**
- Required for group chat and channel use — there is no workaround via sideloading
- Developer submits from Developer Portal (Publish → Publish to your org)
- Admin approves in Teams Admin Center → Manage apps → publishes it
- **Important:** the default availability after publishing is "Everyone" including external/guest users. Admin should immediately set it to "Specific users or groups" before walking away.
- Once published, the app appears in "Built for your org" in the Teams App Store

**Availability policy controls installation, not interaction.** The policy gates who can *add* the bot to a new chat or channel. Once it's installed somewhere, all members of that channel can see its messages and @mention it regardless of whether they're in the scoped group. To restrict who can interact with the bot, control channel membership — not the app policy.

**Teams admins bypass availability scoping** — an admin can always install any org-catalog app, even if their account isn't in the scoped group. Expected behavior, but worth knowing.

---

## Bot Framework Activity Format

Teams does not have a Teams-specific messaging protocol. It uses the **Bot Framework Activity** format, which is a standard JSON payload POSTed to your endpoint over HTTPS. The key fields:

```json
{
  "type": "message",
  "text": "the user's message",
  "serviceUrl": "https://smba.trafficmanager.net/amer/<tenantId>/",
  "from": { "id": "29:...", "name": "Display Name", "aadObjectId": "<entra-user-id>" },
  "conversation": { "id": "<conversationId>", "conversationType": "personal" },
  "id": "<activityId>"
}
```

Three activity types you'll receive:

| Type | When | Has `text`? |
|---|---|---|
| `message` | User sends a message | Yes |
| `conversationUpdate` | Members added/removed, team/channel renamed | No — check `membersAdded` / `membersRemoved` |
| `installationUpdate` | App installed or uninstalled | No |

Your endpoint must respond `200 OK` quickly (before doing any async work) or Teams will retry. Send replies by POSTing back to the Bot Framework API using a token obtained with the app registration credentials.

**Reply URL patterns:**
- Reply to a specific message: `{serviceUrl}/v3/conversations/{conversationId}/activities/{activityId}`
- Post a new message proactively: `{serviceUrl}/v3/conversations/{conversationId}/activities` (no activity ID at the end)

**Sender identity:** `from.aadObjectId` is the sender's Entra object ID — useful for looking up the user in MS Graph if needed.

---

## n8n as the Bot Backend

We built a working bot using n8n with no custom code deployment. The workflow:

1. **Webhook** — receives Bot Framework Activity POSTs at a fixed URL
2. **Respond 200 OK** — fires immediately to unblock Teams before doing async work
3. **Fetch Bot Framework JWKS** — HTTP GET to `https://login.botframework.com/v1/.well-known/keys`
4. **Validate JWT** — Code node verifies the `Authorization: Bearer` token (see below)
5. **Switch** — routes by `body.type` (message / conversationUpdate / installationUpdate)
6. **message branch** — sends echo reply; n8n handles Bot Framework token acquisition automatically via the OAuth2 credential
7. **conversationUpdate branch** — Code node checks `membersAdded` / `membersRemoved` and constructs a greeting or farewell; sends message via same OAuth2 credential
8. **installationUpdate** — silently dropped

The demo workflow is at: `https://n8n-dev.lcmain.aaii.cucloud.net/workflow/UpYSG156S63vb4HZ`

For outbound auth, n8n's built-in **OAuth2 API** generic credential type handles token acquisition automatically. The credential ("JCB Teams Bot Experiment dev tenant") is configured with `client_credentials` grant, the tenant token URL, and `scope: https://api.botframework.com/.default`. Both reply nodes reference it directly — no separate "Get Token" step is needed in the workflow. The client secret is encrypted at rest in n8n and never appears in the workflow JSON.

**This pattern generalizes cleanly.** Any tool that can receive an HTTP POST and make authenticated HTTP requests can serve as a Teams bot backend. n8n is a good fit for rapid prototyping; it makes the Bot Framework payload structure directly visible without any SDK abstraction.

---

## JWT Validation of Inbound Messages

Every inbound Bot Framework message carries an `Authorization: Bearer <jwt>` header. Validating this token confirms the request genuinely came from the Bot Framework service and is intended for your bot. Without it, anyone who discovers your webhook URL can POST arbitrary messages to it.

**Token structure:** RS256-signed JWT with claims:

| Claim | Expected value |
|---|---|
| `iss` | `https://api.botframework.com` |
| `aud` | Your bot's client ID (Entra app registration ID) |
| `exp` / `nbf` | Standard expiry / not-before, checked with ±5 min clock skew |
| `serviceurl` | Should match `body.serviceUrl` in the activity (note: lowercase `u` in the JWT claim) |

**Signing keys:** Published at `https://login.botframework.com/v1/.well-known/keys` (JWKS format). The JWT header contains a `kid` that identifies which key to use.

**Implementation in n8n:** n8n's Code node sandbox strips `crypto` from the global scope (`globalThis.crypto` is `undefined`), but `require('crypto')` works for Node.js built-in modules. The Web Crypto API is accessed via:

```javascript
const subtle = require('crypto').webcrypto.subtle;
```

`Buffer` is also available as a Node.js global (no require needed), which simplifies base64url decoding:

```javascript
// Decode JWT header/payload
const header = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8'));
// Decode signature bytes
const signatureBytes = Buffer.from(parts[2], 'base64url');
```

**Validation is a gate, not a transform.** The Validate JWT Code node runs in `runOnceForAllItems` mode and either passes the request through (`return [{ json: { _validated: true } }]`) or drops it silently (`return []`). Downstream nodes use cross-node references back to `Receive Teams Activity` to get the original payload — the validated item itself carries only the `_validated` flag.

---

## What's Not Covered

**Secrets management** — ~~resolved~~. Bot credentials (client ID + secret) are stored in n8n's built-in **Credentials** store using the "OAuth2 API" generic credential type. The reply nodes reference the credential directly; n8n fetches and caches the token automatically (client credentials grant, `scope: https://api.botframework.com/.default`). The secret is encrypted at rest in n8n and does not appear in the workflow JSON. **This is the correct pattern for any future n8n bot work:** configure an OAuth2 API credential and attach it to HTTP Request nodes — do not add a separate "Get Token" node.

**MS Graph API permissions** — if the bot needs to call MS Graph (e.g. read calendar, send email, query user directory), those permissions must be configured on the app registration and may require admin consent. The admin consent flow for this is identical to any other Entra app registration — nothing Teams-specific. Not tested here.
