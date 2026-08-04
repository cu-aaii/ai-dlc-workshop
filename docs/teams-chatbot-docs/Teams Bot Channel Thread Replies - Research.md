# Teams Bot Channel Thread Replies — Research 2026-04-06

## The Question

When a bot posts a message to a Teams channel (a "Post"), users can reply to it in-thread. By default, the bot only receives webhook events when @mentioned. Is there any way to make the bot receive all replies to its own channel posts, without requiring @mention?

---

## TODO

- [ ] **Investigate `webApplicationInfo.id` conflict** — Earlier in this project, setting "Application (client) ID" in the Developer Portal (which maps to `webApplicationInfo.id`) caused silent Teams install failures because Teams tried to do SSO and the app registration wasn't configured for it. RSC requires `webApplicationInfo.id`, but uses `resource: "https://AnyString"` to signal "RSC-only, not SSO." Test whether Teams respects this distinction with this app registration. If it causes the same install failure, investigate whether the app registration needs any SSO-related configuration added, or whether the manifest must be edited directly (bypassing the portal field) to set `webApplicationInfo` without triggering the SSO flow.
- [ ] **Update the Teams app manifest** — Add `webApplicationInfo` and `authorization.permissions.resourceSpecific` with `ChannelMessage.Read.Group` (see Implementation section below). Bump the version string. Republish via Developer Portal.
- [ ] **Reinstall the app in the team** — Remove and re-add the app in the test team. Verify the install dialog shows the new `ChannelMessage.Read.Group` permission. Team owner consent is required; no Entra admin action needed.
- [ ] **Validate delivery** — Send a message in a channel thread (not @mentioning the bot) and confirm the n8n webhook fires. Check the activity payload for `replyToId` to confirm it's populated on replies.
- [ ] **Implement n8n filtering** — Once delivery is confirmed, add logic to scope the bot's responses: (a) store the activity ID returned when the bot sends a channel post, (b) check incoming `body.replyToId` against stored IDs, (c) silently return 200 for unrelated channel traffic.

---

## Finding 1: The Default Behavior is Hard-Wired by Design

The Microsoft documentation states this explicitly and unambiguously:

> "Bots in a group or channel only receive messages when they're mentioned @botname. They don't receive any other messages sent to the conversation. The bot must be @mentioned directly. Your bot doesn't receive a message when the team or channel is mentioned, or when someone replies to a message from your bot without @mentioning it."

Source: [Channel and Group Conversation bots](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/channel-and-group-conversations)

There is no Bot Framework SDK configuration, no Azure Bot Service setting, and no Teams app manifest flag that changes this behavior without RSC (see below). The @mention requirement is not just a default — it is the only mode the Bot Framework Activity delivery pipeline supports for channels, unless RSC is used.

---

## Finding 2: RSC is the Official Solution — and It Works for n8n

Microsoft's supported mechanism to receive all channel messages (including replies to bot posts, without @mention) is **Resource-Specific Consent (RSC)**. The relevant permission is `ChannelMessage.Read.Group`.

### How it works

RSC is an authorization framework that lets a Teams app request scoped access to a specific resource (one team, one chat) rather than requiring tenant-wide Graph API permissions. When `ChannelMessage.Read.Group` is declared in the Teams app manifest and the app is installed in a team, the Bot Framework service will route all messages in all channels of that team to the bot's messaging endpoint — including replies to the bot's own posts, replies to other users' posts, and any message in the channel.

There is no `channelMessageReceived` manifest capability or similar named toggle. The mechanism is the RSC permission in the manifest, full stop.

### Manifest changes required

In the Teams app manifest (`manifest.json`, schema version 1.12 or later), add the following:

```json
{
  "webApplicationInfo": {
    "id": "<your-entra-app-id>",
    "resource": "https://AnyString"
  },
  "authorization": {
    "permissions": {
      "resourceSpecific": [
        {
          "type": "Application",
          "name": "ChannelMessage.Read.Group"
        }
      ]
    }
  }
}
```

The `webApplicationInfo.id` must match your bot's Entra app registration (the same ID used in the `bots` array). The `resource` field is vestigial — it has no operational effect but must be present with any non-empty string value to avoid an API error.

`ChannelMessage.Read.Group` is a **team-scoped RSC application permission** — it applies to the specific team where the app is installed, not to all teams in the tenant. The permission is declared in the manifest but actually granted when a team owner (or any member, depending on RSC configuration) installs the app. No Entra admin consent is required for RSC permissions; they are consented to at installation time by the team owner.

Source: [Get All Channel and Chat Messages for Bot and Agents](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/channel-messages-for-bots-and-agents)

### What the bot receives

With `ChannelMessage.Read.Group` enabled, the Bot Framework service delivers **every message in every channel of that team** to the bot's messaging endpoint, including:

- All new channel posts
- All replies to any post (including replies to the bot's own posts)
- Messages that do not @mention the bot

The activity format is identical to @mention-triggered activities — the same Bot Framework JSON payload POSTed to the same messaging endpoint URL. There is no special handling required. In n8n, the same Webhook node receives these activities.

The bot will need to filter out messages it does not care about. The canonical approach is to check whether `entities` contains a mention of the bot's ID. If it does, process it; if not, either process it (for "receive everything" use cases) or return 200 immediately without further action.

### Consent and admin involvement

RSC permissions are **not** governed by tenant-wide Entra admin consent. They are governed by the Teams RSC consent model:

- For `ChannelMessage.Read.Group` (Application type, team-scoped): the team owner grants consent at app installation time.
- The Teams admin center has a setting "Allow resource-specific consent" that controls whether RSC is enabled at the tenant level. This is enabled by default. If it has been disabled by a tenant admin, RSC will not work.
- Note on the Microsoft docs: the RSC page says "RSC permissions are available only to Teams apps installed on the Teams client and not part of the Microsoft Entra admin center" — meaning you manage and grant these permissions through the Teams app installation flow, not through Entra portal app consent pages.

Source: [Resource-specific Consent for Apps](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent)

### Effect on sideloaded vs. org-published apps

RSC works the same way for both sideloaded apps and org-published apps. The consent is granted at installation time in both cases. The team owner (or the person who installs the app) sees the permission request during the installation dialog.

---

## Finding 3: MS Graph Change Notifications — An Alternative Path

MS Graph change notifications provide a second, independent mechanism to receive channel messages. This path does not use the Bot Framework Activity delivery pipeline at all — it is a separate subscription-based webhook system.

### How it works

You create a subscription via the Graph API that tells Microsoft Graph to POST a notification to your webhook URL whenever messages change in a specified resource. For channel messages:

```http
POST https://graph.microsoft.com/v1.0/subscriptions
Content-Type: application/json

{
  "changeType": "created,updated",
  "notificationUrl": "https://<your-n8n-webhook-url>",
  "resource": "/teams/{team-id}/channels/{channel-id}/messages",
  "includeResourceData": false,
  "expirationDateTime": "2026-04-09T11:00:00.0000000Z",
  "clientState": "<secret-value>"
}
```

The resource path `/teams/{team-id}/channels/{channel-id}/messages` covers **all messages and replies in that channel** — including replies to threads. There is no filtering to "only replies to the bot's posts"; it is all-or-nothing at the channel level.

### Two modes: with or without resource data

**Without resource data** (`includeResourceData: false`): The notification payload contains only the message ID and a resource path. You must make a follow-up GET call to the Graph API to retrieve the actual message content. No encryption certificate is required.

**With resource data** (`includeResourceData: true`): The notification payload contains the full `chatMessage` object, encrypted with a public key you provide. This is the "rich notification" model. It requires:
- An RSA certificate (can be self-signed — Graph does not verify the CA)
- The public key provided as `encryptionCertificate` in the subscription request
- The private key stored securely by the subscriber, used to decrypt the `encryptedContent` field in each notification

For n8n as the receiver: the encryption/decryption requirement for rich notifications is a significant implementation burden. Without resource data is simpler — the notification triggers an n8n workflow, which then makes a Graph API GET call to fetch the message.

### Permissions required

For channel-level subscriptions (`/teams/{team-id}/channels/{channel-id}/messages`):

| Permission type | Permission |
|---|---|
| Application (no user) | `ChannelMessage.Read.All` |
| RSC (team-scoped) | `ChannelMessage.Read.Group` |
| Delegated | `ChannelMessage.Read.All` |

`ChannelMessage.Read.All` is a standard Entra application permission that requires admin consent. `ChannelMessage.Read.Group` as an RSC permission for Graph subscriptions is listed in the docs with a `*` noting it is supported for channel-level subscriptions.

For the tenant-wide path (`/teams/getAllMessages`), only `ChannelMessage.Read.All` (application, admin-consented) is supported.

Source: [Get change notifications for messages in Teams channels and chats](https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage)

### Subscription lifecycle — a critical operational concern

Teams `chatMessage` subscriptions have a **maximum lifetime of 4,320 minutes (3 days)**. After that, the subscription expires and notifications stop. You must renew (PATCH the subscription's `expirationDateTime`) before expiry, or create a new subscription.

For subscriptions with `expirationDateTime` more than 1 hour in the future, a `lifecycleNotificationUrl` is **required** (the subscription creation fails without it). This is a second HTTPS endpoint that receives lifecycle events (subscription expiring, reauthorization required).

The webhook validation requirement is also significant: when you create a subscription, Graph sends a POST to `notificationUrl` with a `?validationToken=...` query parameter. The endpoint must respond within 10 seconds with the plain-text token as the body and `200 OK`. This is a synchronous handshake, not an async event. n8n can handle this but the workflow must be structured to detect and respond to validation requests immediately.

Source: [Receive change notifications through webhooks](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks)

### Graph notifications vs. RSC Bot Framework delivery — key differences

| | RSC + Bot Framework | MS Graph Change Notifications |
|---|---|---|
| Delivery mechanism | Bot Framework Activity POSTed to bot's messaging endpoint | Graph POSTs notification to subscription notificationUrl |
| Payload format | Bot Framework Activity JSON | `changeNotificationCollection` JSON (or encrypted) |
| Subscription management | None — persists as long as app is installed in the team | Must be created and renewed every ≤3 days |
| Permission model | RSC consent at install time (no Entra admin) | Entra admin consent for `ChannelMessage.Read.All`, OR RSC for `ChannelMessage.Read.Group` |
| Resource data inline | Yes — full activity in the POST | Only if `includeResourceData: true` with encryption |
| Scope | All channels in the installed team | Per channel, or tenant-wide with `getAllMessages` |
| Validation handshake | None | Required — synchronous token echo on subscription creation |
| Reply context | Activity includes `replyToId` and `conversation.id` | `chatMessage.replyToId` in message body |
| Can filter to specific threads | No (filter in your code) | Yes — via `$filter` query parameter, but no "bot's posts only" built-in filter |

---

## Finding 4: Limitations and Workarounds for "Bot-Initiated Thread" Pattern

The core challenge: the bot posts a message to a channel (proactive messaging via Bot Framework API), which creates a thread. Users reply. The bot wants to receive those replies.

### What works

**RSC (`ChannelMessage.Read.Group`) is the cleanest solution.** Once the manifest is updated and the app is reinstalled in the team, all channel messages arrive at the bot's webhook. The bot can filter by `replyToId` to identify replies to its own posts. The activity payload includes:
- `conversation.id` — the channel conversation ID
- `replyToId` — the activity ID of the message being replied to (the bot's original post)

The bot knows its own post's activity ID because the Bot Framework API returns it in the response when the bot sent the original message. If the n8n workflow stored that activity ID at send time, it can match incoming `replyToId` values to identify replies to its own posts.

**MS Graph change notifications** also work but add operational overhead (subscription renewal, validation handshake, optional decryption).

### What does not work

- There is no way to subscribe to "only replies to this bot's posts" at the platform level, in either mechanism. Filtering to the bot's posts must be done in application code.
- There is no "conversationUpdate" or similar event that fires when a user replies to a bot post without @mentioning — in the absence of RSC, those replies are silently dropped by the Bot Framework delivery layer.
- The bot cannot retroactively fetch missed replies via Bot Framework. If RSC was not enabled at install time, those replies were never delivered. (They can be fetched retroactively via Graph API GET calls if the app has `ChannelMessage.Read.All` or `ChannelMessage.Read.Group` permissions.)

### The "re-install to activate RSC" gotcha

When you add RSC permissions to an existing app manifest, they only take effect after the app is **reinstalled** in the team. An in-place manifest update does not trigger re-consent. The team must remove the app and add it again (or a new installation must occur). This is a significant operational consideration for apps already deployed.

### Subscription renewal for Graph notifications in n8n

If using Graph change notifications from n8n:

1. The n8n workflow (or a separate scheduled workflow) must PATCH the subscription before it expires every 3 days.
2. The notificationUrl endpoint must respond to the initial validation token handshake synchronously — the n8n Webhook node must detect `?validationToken=` in the query string and echo it back immediately.
3. A `lifecycleNotificationUrl` endpoint is required if subscriptions last more than 1 hour. This can be the same URL with a different query param, or a separate webhook, as long as it echoes the lifecycle validation token correctly.

---

## Recommended Approach for n8n Bot

Given the single-tenant Entra app, Azure Bot Service, and n8n backend:

**Use RSC (`ChannelMessage.Read.Group`) + Bot Framework delivery.** Reasons:
- No subscription management — persists with app installation
- No encryption certificate management
- Payload arrives in the same Bot Framework Activity format the n8n workflow already handles
- Per-team consent model — no Entra admin consent needed
- Simple to filter: check `replyToId` against stored activity IDs of the bot's own posts

Steps:
1. Update the Teams app manifest to add `webApplicationInfo` and `authorization.permissions.resourceSpecific` with `ChannelMessage.Read.Group`.
2. Bump the manifest version string.
3. Republish the app via Developer Portal (or re-upload the zip).
4. **Reinstall the app in the team** — remove and re-add. The team owner will see a consent dialog listing the new permission.
5. In the n8n workflow, add filtering logic on the Switch or a Code node: check whether `$json.body.replyToId` matches any of the bot's post IDs that should be tracked. Silently return 200 for messages that don't match.

If broader Graph access is needed later (e.g., read/write other resources, retroactive message fetch), the same Entra app registration can have `ChannelMessage.Read.All` added with admin consent — and Graph change notification subscriptions can coexist with Bot Framework delivery.

---

## References

- [Channel and Group Conversation bots — Microsoft Docs](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/channel-and-group-conversations)
- [Get All Channel and Chat Messages for Bot and Agents (RSC)](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/channel-messages-for-bots-and-agents)
- [Resource-specific Consent for Apps](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent)
- [Get change notifications for messages in Teams channels and chats](https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage)
- [Set up change notifications with resource data](https://learn.microsoft.com/en-us/graph/change-notifications-with-resource-data)
- [Receive change notifications through webhooks](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks)
- [subscription resource type — max expiration times](https://learn.microsoft.com/en-us/graph/api/resources/subscription?view=graph-rest-1.0)
