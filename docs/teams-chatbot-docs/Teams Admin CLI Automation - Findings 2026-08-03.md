# Teams Admin CLI Automation — Findings 2026-08-03

## What We Set Out to Answer

Given a global admin identity on the dev tenant, what Teams Admin Center work can actually be driven
from the CLI instead of clicking through `admin.teams.microsoft.com`, and what are the exact
incantations? This picks up where
[Teams Bot Setup - Findings 2026-04-06](./Teams%20Bot%20Setup%20-%20Findings%202026-04-06.md) left
off — that report flagged Graph API permissions as untested; this is the follow-up.

It also answers the related question the repo actually needs answered: can any of this run
**unattended from CodeBuild**, given the "everything is IaC, no click-ops" constraint?

## Short Answer, and the Distinction That Matters

**Almost all of it is scriptable. Roughly half of it is not *unattended*.** Those are different
questions and conflating them is the single easiest way to misread this document.

- **App-only (client credentials)** — a service principal with a secret or certificate, no human,
  works in CI. This covers the Entra app registration, the Azure Bot Service resource, its Teams
  channel, the messaging endpoint, and push-installing a published app.
- **Delegated (a signed-in user)** — needs interactive authentication to obtain a token. This covers
  **everything touching the Teams app catalog and Teams admin surface**: publishing, approving,
  availability scoping, tenant app settings, setup policies.

Everything below marked "confirmed live" was confirmed with a **delegated admin token acquired
interactively** — device-code flow for Graph, `Connect-MicrosoftTeams -UseDeviceAuthentication` for
PowerShell. That is a real result and it removes the GUI. It is not a pipeline step.

The other axis: **the App Catalog and tenant app settings are reachable via Microsoft Graph — but
not via `az rest`.** Setup Policies (sideloading) and the legacy per-app Permission Policy have **no
Graph REST API at all**, but *are* scriptable via the Teams PowerShell module (`MicrosoftTeams`),
which is a genuine CLI, not the GUI. So the real split is Graph vs. Teams PowerShell vs. GUI —
crossed with delegated vs. app-only.

### Summary

| Task | Mechanism | Confirmed live? | Works unattended (app-only)? |
|---|---|---|---|
| Entra app registration + client secret | `az ad app create` / Graph `POST /applications` | Not re-tested | **Yes** |
| Azure Bot Service resource | `az bot create` | `--help` only | **Yes** |
| Teams channel on the bot | `az bot msteams create` | `--help` only | **Yes** |
| Set/update messaging endpoint | `az bot update --endpoint` | Not tested | **Yes** |
| Author manifest + icons + zip | Plain files | ✓ hand-authored, zero Developer Portal | **Yes** |
| List org-catalog apps | Graph `GET /appCatalogs/teamsApps` | ✓ | **No** — delegated only |
| **Publish app to org catalog** | Graph `POST /appCatalogs/teamsApps` (zip body) | ✓ | **No** — delegated admin only |
| Approve a pending-review submission | Graph `PATCH .../appDefinitions/{id}` + `If-Match` | documented only | **No** — delegated only |
| Delete app from catalog | Graph `DELETE /appCatalogs/teamsApps/{id}` | ✓ | **No** — delegated only |
| Read/write tenant app settings | Graph `GET`/`PATCH /teamwork/teamsAppSettings` | ✓ | **No** — delegated only |
| Read availability/install state | `Get-M365TeamsApp` | ✓ | **No** — explicitly excluded |
| **Restrict availability to an AD group** | `Update-M365TeamsApp -Groups …` | ✓ | **No** — explicitly excluded |
| Grant sideloading (Setup Policy) | `Set-`/`Grant-CsTeamsAppSetupPolicy` | not tested | Untested; no Graph equivalent |
| Restrict to specific *users* (legacy Permission Policy) | `Set-`/`Grant-CsTeamsAppPermissionPolicy` | not tested | No group targeting at all — superseded |
| Push-install into a user's or team's scope | Graph `POST /users\|teams/{id}/…/installedApps` | documented only | **Yes** |
| Admin consent for extra Graph perms the bot needs | `az ad app permission admin-consent` | not tested — our PoC needs none | Yes |
| Bot backend logic (webhook, JWT, replies) | Whatever hosts it (n8n in our case) | ✓ end-to-end | n/a |

---

## The `az rest` Blocker (important, non-obvious)

`az rest` reuses whatever delegated Graph scopes are already consented for the **"Azure CLI"
first-party app** in the tenant. That app's permission set is fixed by Microsoft (not editable
per-tenant) and does **not** include `AppCatalog.*` or `TeamworkAppSettings.*`. Confirmed via direct
403:

```
ERROR: Forbidden({"error":{"code":"Forbidden","message":"Missing scope permissions on the request.
API requires one of 'AppCatalog.Submit, AppCatalog.Read.All, AppCatalog.ReadWrite.All,
Directory.Read.All, Directory.ReadWrite.All'. Scopes on the request 'Application.ReadWrite.All,
AppRoleAssignment.ReadWrite.All, ...'"}})
```

This is **not a privilege gap** — a global admin still can't reach these endpoints through `az rest`,
because the *client app* `az rest` authenticates as was never granted the right to *request* these
scopes in the first place. Admin consent only grants scopes an app has declared in its own manifest;
you can't add scopes to Microsoft's own "Azure CLI" app registration.

**Fix:** get a token from a different first-party client that already has these scopes available to
request — the **Microsoft Graph Command Line Tools** app (client ID
`14d82eec-204b-4c2f-b7e8-296a70dab67e`, the same public client `Connect-MgGraph` uses under the hood;
installing PowerShell adds no extra capability here, it's literally the same OAuth client). Device-code
flow, no PowerShell required:

```bash
# 1. Request a device code, scoped to exactly what's needed (no offline_access —
#    short-lived token only, nothing persisted)
curl -sS -X POST "https://login.microsoftonline.com/<tenantId>/oauth2/v2.0/devicecode" \
  -d "client_id=14d82eec-204b-4c2f-b7e8-296a70dab67e" \
  -d "scope=https://graph.microsoft.com/AppCatalog.ReadWrite.All https://graph.microsoft.com/TeamworkAppSettings.ReadWrite.All"
# -> returns a user_code + verification URL (login.microsoft.com/device); complete
#    interactively as the admin in a browser (one-time consent prompt)

# 2. Poll for the token once approved
curl -sS -X POST "https://login.microsoftonline.com/<tenantId>/oauth2/v2.0/token" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
  -d "client_id=14d82eec-204b-4c2f-b7e8-296a70dab67e" \
  -d "device_code=<device_code from step 1>"
# -> {"access_token": "...", "expires_in": 4247, "scope": "... AppCatalog.ReadWrite.All ..."}
```

Then use the `access_token` as a normal bearer token with `curl` for every call below.

**Token lasted ~70 minutes, and no refresh token was requested.** Worth being precise about what
that implies: the *consent* prompt is one-time per client per tenant, but the *authentication* is
per-session. A human re-authenticates every time, and each `pwsh` process needed its own fresh
device-code auth — no persistent token cache was observed the way `az` has one. To run this
unattended you would need `offline_access` and a durably stored refresh token, which is a different
security proposition (see *Escape hatches*).

---

## Confirmed Working: App Catalog Management (Graph API, delegated)

All tested live against the dev tenant, using the token above.

**List org-catalog apps** (note: query params need `curl -G --data-urlencode`, not inline
`?$filter=`, or the URL gets mangled by shell quoting):

```bash
curl -sS -G "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps" \
  --data-urlencode '$filter=distributionMethod eq '"'"'organization'"'"'' \
  --data-urlencode '$expand=appDefinitions' \
  -H "Authorization: Bearer $TOKEN"
```

**Publish a new app** (as global admin, this goes live immediately — no `requiresReview` needed):

```bash
curl -sS -X POST "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/zip" \
  --data-binary @app-package.zip
# -> 201 Created, body includes the new catalog "id" (distinct from the manifest's own "id"/externalId)
```

Confirmed the zip just needs `manifest.json` + `color.png` + `outline.png` at the zip root (no
subfolder) — `curl --data-binary` handles the binary body fine (the earlier concern about `az rest`
and binary bodies turned out to be moot since we're not using `az rest` at all here).

Why "no `requiresReview` needed" works, from the Graph docs: *"Users with admin privileges can submit
apps without triggering a review… A user who has admin privileges can opt not to set
**requiresReview** or set the value to `false` and the app is approved and immediately published."*
So an admin token publishes in one call and skips the review queue entirely — the two-step approve
dance documented in the 2026-04 findings is avoidable.

**Verify publishing state:**

```bash
curl -sS -G "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/<catalogId>" \
  --data-urlencode '$expand=appDefinitions' -H "Authorization: Bearer $TOKEN"
# -> appDefinitions[0].publishingState: "published"   (immediate, since admin + no requiresReview)
```

**Approve a pending-review submission** (documented from Microsoft Learn, not live-tested this
session — would need a non-admin identity to actually submit one first):

```bash
curl -sS -X PATCH "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/<id>/appDefinitions/<appDefinitionId>" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "If-Match: <etag>" \
  -d '{"publishingState":"published"}'
```

**Delete an app from the catalog** (confirmed — used to clean up the PoC test app):

```bash
curl -sS -X DELETE "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/<catalogId>" \
  -H "Authorization: Bearer $TOKEN"
# -> 204, then a GET on the same id returns 404
```

**Read/write tenant-wide app settings** (confirmed both directions):

```bash
curl -sS "https://graph.microsoft.com/v1.0/teamwork/teamsAppSettings" -H "Authorization: Bearer $TOKEN"
# -> {"allowUserRequestsForAppAccess": true, "isUserPersonalScopeResourceSpecificConsentEnabled": true}

curl -sS -X PATCH "https://graph.microsoft.com/v1.0/teamwork/teamsAppSettings" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"allowUserRequestsForAppAccess": true, "isUserPersonalScopeResourceSpecificConsentEnabled": true}'
# -> 204 No Content
```

PoC used a throwaway test app package (`cli-poc-test-app/`, referencing the existing real bot ID
`e6ee0253-8949-4eba-ba9f-f9d5da45fa1d`, personal scope only) so as not to disturb the live
GUI-published "JCB Teams Bot Test" app — published, verified, then deleted.

**Authoring the manifest as files beats the Developer Portal.** The 2026-04 research hit a portal bug
where `supportsChannelFeatures: "tier1"` — required by the v1.25 schema for `team` scope — was not
exposed in the UI and was *rejected by the portal's own validator* when placed correctly. A
hand-authored manifest in git sidesteps that entirely and makes the manifest reviewable like
everything else.

---

## The App-Only Wall — Why None of the Above Runs in CI

This is the part that decides whether any of it can live in `pipeline.yml`. The Graph permission
tables are explicit:

`POST /appCatalogs/teamsApps` (publish) and `POST /appCatalogs/teamsApps/{id}/appDefinitions`
(new version):

| Permission type | Least privileged | Higher privileged |
| --- | --- | --- |
| Delegated (work or school account) | `AppCatalog.Submit` | `AppCatalog.ReadWrite.All`, `Directory.ReadWrite.All` |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| **Application** | **Not supported.** | **Not supported.** |

**Identical in `beta` as well as `v1.0`** — checked specifically, because "it's coming in beta" is the
usual escape and here it isn't. Two further constraints from the same docs:

- `AppCatalog.Submit` **submits for review only** — it cannot publish. Publishing needs
  `AppCatalog.ReadWrite.All` or `Directory.ReadWrite.All`, delegated.
- The update API adds: *"Only Teams Service admins or a higher privileged role can call this API."*

And on the PowerShell side, the Teams module's app-based-authentication doc says *"All cmdlets are
supported now, except…"* and the exclusion list names:

- `Get-AllM365TeamsApps`
- **`[Get|Update]-M365TeamsApp`** ← the availability-scoping cmdlets below
- `Get-M365UnifiedCustomPendingApps`, `Update-M365UnifiedCustomPendingApp` ← approving pending apps
- `[Get|Update]-M365UnifiedTenantSettings`

So **group-scoped availability will never work app-only.** That is settled, from Microsoft's own
exclusion list, not inferred.

**This is a Teams-specific limitation, not a generic OAuth one.** Client-credentials flow needs no
human at all and works fine for the rest of the chain (below). The Teams catalog and admin surface
specifically declines application permissions.

### Corroboration: Microsoft's own CI/CD template stops at the same line

The official [CI/CD templates](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/use-cicd-template)
page for Teams apps is worth reading as evidence. Its GitHub Actions pipeline does:

1. `atk auth login azure --service-principal true --interactive false` ← **Azure, app-only**
2. `atk deploy --interactive false`
3. `atk package`
4. `actions/upload-artifact` — uploads `appPackage.zip` **as a build artifact**

There is **no publish step and no M365 login step in the pipeline at all.** Microsoft's own reference
automation produces the zip and hands it off to a human. Two independent sources — the permission
tables and the reference pipeline — land on the same boundary.

---

## What *Does* Run Unattended

### Entra app registration + client secret — app-only ✓

| API | Application permission (least privileged) |
| --- | --- |
| `POST /applications` | `AppRegistration.Create` (also `Application.ReadWrite.OwnedBy`, `Application.ReadWrite.All`) |
| `POST /applications/{id}/addPassword` | `Application.ReadWrite.OwnedBy` |

`Application.ReadWrite.OwnedBy` is the right choice: it lets the pipeline's service principal manage
only applications it owns, not every app in Cornell's tenant. Worth insisting on — a CI credential
holding `Application.ReadWrite.All` over Cornell's tenant is a far bigger blast radius than this
blueprint warrants.

- **CLI:** `az ad app create`, `az ad app credential reset`
- **Terraform:** `azuread_application`, `azuread_service_principal`, `azuread_application_password`

**Caveat on Terraform for the secret.** `azuread_application_password` puts the generated secret in
Terraform **state**, which collides with "secrets live only in AWS Secrets Manager." Either generate
the secret in a script step that writes straight to Secrets Manager and never lands it in state, or
treat state as a secret store and protect it accordingly. The first fits this repo better.

**Prefer a certificate over a secret if the Entra side allows it** — it removes R-3 (secrets expire,
tracked by a person). Not free: the bot's outbound `client_credentials` call would need to sign a
client assertion instead of sending a secret, which is more code in the Lambda.

### Azure Bot Service + Teams channel + endpoint — app-only ✓

```sh
az bot create \
  --app-type SingleTenant \
  --appid <client-id> \
  --tenant-id <tenant-id> \
  --name <bot-name> \
  --resource-group <rg> \
  --endpoint https://<lambda-url>/ \
  --sku F0 \
  --tags cornell:owner=... cornell:blueprint=...

az bot msteams create --name <bot-name> --resource-group <rg>
az bot update --name <bot-name> --resource-group <rg> --endpoint https://<new-url>/
```

`--app-type SingleTenant` is required: multi-tenant bot creation was deprecated after 2025-07-31.
`--tags` is supported, so the four `cornell:*` tags apply here too.

- **Terraform:** `azurerm_bot_service_azure_bot` (`microsoft_app_type = "SingleTenant"`,
  `microsoft_app_id`, `microsoft_app_tenant_id`, `endpoint`, `sku`, `tags`) and
  `azurerm_bot_channel_ms_teams`. The provider carries the same deprecation note: *"Creation of
  `azurerm_bot_service_azure_bot` resources using the `MultiTenant` type is no longer supported by
  Azure."*
- Requires Azure **Contributor on the resource group** — an Azure RBAC role, not an Entra or Teams
  admin role.
- Likely prerequisite on a fresh subscription: `az provider register --namespace
  Microsoft.BotService`. Not verified.

### Push-installing a published app — app-only ✓

`POST /users/{id}/teamwork/installedApps` **does** support Application permissions
(`TeamsAppInstallation.ReadWriteSelfForUser.All` and friends). The wall is publication, not
installation.

This enables a useful hybrid: **publish once by hand, then let the pipeline push-install app-only.**
Caveat — availability defaults to Everyone after publish, so if discovery needs restricting, the
manual `Update-M365TeamsApp` step comes back. Push-install controls who *has* the app; availability
controls who can *find and self-install* it. They are not substitutes.

*(The team-scoped equivalent, `POST /teams/{id}/installedApps`, was not verified for app-only support.
Confirm before relying on it.)*

---

## Confirmed NOT Automatable via Graph: Setup Policies & Permission Policies

No Graph endpoint exists for assigning **Setup Policies** (the "Upload custom apps" sideloading
grant, per-user/per-group) or the legacy per-app **Permission Policy**. These remain Teams PowerShell
(`Connect-MicrosoftTeams`, `Set-CsTeamsAppSetupPolicy`, `Grant-CsTeamsAppSetupPolicy`,
`Set-CsTeamsAppPermissionPolicy`) or the Teams Admin Center GUI. **These specific `*-Cs*` policy
cmdlets were not live-tested** — they'd need their own `Connect-MicrosoftTeams` session. (Teams
PowerShell itself *was* live-tested this session, for `Update-M365TeamsApp` below.)

Confirmed the Teams PowerShell module is genuinely cross-platform (PowerShell 7.2+, works on
macOS/Linux — not a Windows-only module), and that `pwsh` is available via Nix
(`nixpkgs#powershell` — no Homebrew deviation needed if this gets pursued).

**`TeamsAppPermissionPolicy` does not support group targeting at all**, dynamic or otherwise.
Verified against the cmdlet reference: *"As of May 2023, group policy assignment functionality in
Teams PowerShell Module has been extended to support all policy types used in Teams except for the
following: **Teams App Permission Policy**, Teams Network Roaming Policy, Teams Emergency Call
Routing Policy, Teams Voice Applications Policy, Teams Upgrade Policy."* It's also excluded from the
newer `Grant-Cs*` `-Group` parameter pattern. The only way to apply it to "a group of users" is to
loop `Grant-CsTeamsAppPermissionPolicy` over each member (or `New-CsBatchPolicyAssignmentOperation`
for scale) — a one-time snapshot, not a live membership binding.

**The modern per-app availability scoping is a different feature from the legacy Permission Policy.**
See below.

---

## "Publish to Org Catalog, Scoped to an AD Group" — Fully Scripted

The question: given a bot's app registration + manifest already exist, can we script the *entire*
remaining path — publish it so it appears in "Built for your org," discoverable so any user can find
and add it to a channel, **restricted to members of a specific Entra security group**? This is what a
Teams Admin does by hand in `admin.teams.microsoft.com` → Teams apps → Manage apps → select the app →
Availability → "Specific users or groups."

### First pass, and why it was wrong

Initial research (and live testing against the real "JCB Teams Bot Test" app, catalog id
`b8b3fa57-3343-43cf-94db-abab981be761`) confirmed **Microsoft Graph has no coverage at all** for this
feature:

```bash
# v1.0 and beta both — no availability/availableTo field anywhere on the resource
curl -sS -G "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/b8b3fa57-3343-43cf-94db-abab981be761" \
  --data-urlencode '$expand=appDefinitions' -H "Authorization: Bearer $TOKEN"
curl -sS "https://graph.microsoft.com/beta/appCatalogs/teamsApps/b8b3fa57-3343-43cf-94db-abab981be761" \
  -H "Authorization: Bearer $TOKEN"
```

Also ruled out a plausible workaround: that this might be backed by an Entra Enterprise Application's
`appRoleAssignedTo` (the mechanism that *does* Graph-automate "who can access this Enterprise App,"
including groups). This app has no associated service principal (`azureADAppId: null`, and a direct
`servicePrincipals` filter search returns empty) — a dead end for bot-only apps like this one.

**From this, the first-pass conclusion was: GUI-only, no CLI path at all.** That was incomplete — it
only ruled out *Graph*, not PowerShell.

### Corrected finding: it IS scriptable, via a dedicated cmdlet pair

**`Update-M365TeamsApp`** / **`Get-M365TeamsApp`**, part of the same `MicrosoftTeams` module (docs
current as of 2025-08-01, not deprecated). This is a **distinct API surface from the legacy
`TeamsAppPermissionPolicy` cmdlets** — it manipulates the app-centric "Available to" / "Installed
for" data model, field-for-field matching the GUI screen:

```powershell
# Read current state — matches the GUI's "Available to" / "Installed for" panels exactly
Get-M365TeamsApp -Id <catalogId>
# Returns: IsBlocked, AvailableTo { AssignmentType: Everyone|UsersandGroups|Noone, Users[], Groups[] },
#          InstalledFor { AppInstallType, InstallForUsers[], InstallForGroups[] }

# Write — restrict availability to specific users AND groups in one call
Update-M365TeamsApp -Id <catalogId> `
  -AppAssignmentType UsersAndGroups -OperationType Add `
  -Users <user-guid-1>,<user-guid-2> `
  -Groups <group-guid-1>,<group-guid-2>
```

`-Groups` takes Entra group IDs directly (not expanded member lists) — the "give it a group
reference, Teams evaluates membership live" behaviour the GUI advertises (dynamic groups, nested
groups), not the legacy Permission Policy's per-user-snapshot limitation.

### Live-tested and confirmed, 2026-08-03

`pwsh` via `nix shell nixpkgs#powershell` (v7.6.4, macOS/Unix — ran ephemeral, no permanent flake
change) + `Install-Module -Name MicrosoftTeams -Scope CurrentUser` (v7.9.0) +
`Connect-MicrosoftTeams -TenantId <devTenant> -UseDeviceAuthentication` — a *third* distinct OAuth
client in this investigation, after "Azure CLI" and "Microsoft Graph Command Line Tools."

**Resolved the `-Id` ambiguity:** `Get-M365TeamsApp` wants the app's **catalog id**
(`b8b3fa57-…`), not its manifest/external id — the latter fails with `NotAllowed: This app is not
available for admin management, or the app id … is invalid`. This matches the Graph docs' own warning
on the update API: *"Use the ID returned from the List published apps call… Don't use the ID from the
manifest of the zip app package."*

**The docs' generated parameter-set metadata is misleading**: it marks `-AppInstallType`,
`-InstallForOperationType`, `-InstallForUsers`, `-InstallForGroups` and `-InstallVersion` as mandatory
alongside the assignment params, but they're a separate, independent parameter set — passing them
alongside `-AppAssignmentType`/`-Groups` throws `Users and Groups should be null when
AppAssignmentType is Everyone or Noone`. Omit them when only touching availability (matching the
docs' own Example 2, which also omits them). The reference marks all three parameter sets
`Mandatory: True`, which cannot simultaneously be true — it's a doc bug, not a subtlety.

**Full live round trip against the real "JCB Teams Bot Test" app**, additively adding then removing
the existing "JCB Teams Bot Test Team" M365 group (`83daf24e-4a4f-4786-9ec1-31b95a8bf99a`) so the two
pre-existing user assignments were undisturbed:

```powershell
# BEFORE: AssignmentType=UsersAndGroups, Users=[2 users], Groups=null

Update-M365TeamsApp -Id 'b8b3fa57-3343-43cf-94db-abab981be761' `
  -AppAssignmentType UsersAndGroups -OperationType Add -Groups '83daf24e-4a4f-4786-9ec1-31b95a8bf99a'
# -> "Updated App with Id b8b3fa57-..., Successfully!."
# AFTER ADD: Groups now contains the group, Users unchanged

Update-M365TeamsApp -Id 'b8b3fa57-3343-43cf-94db-abab981be761' `
  -AppAssignmentType UsersAndGroups -OperationType Remove -Groups '83daf24e-4a4f-4786-9ec1-31b95a8bf99a'
# -> "Updated App with Id b8b3fa57-..., Successfully!."
# AFTER CLEANUP: back to Groups=null, Users unchanged — exactly matches BEFORE
```

**The group-scoping is real and works as the GUI feature does** — not a snapshot, not per-user
expansion, a direct group reference.

**Conclusion: the full pipeline is scriptable end to end, but not unattended.** The human step is
interactive authentication of an admin user for whichever Teams-facing client the script uses — and
per the exclusion list above, `Update-M365TeamsApp` can *never* be app-only, so this step cannot be
engineered away.

---

## The One Open Question — Needs a Test, Not More Reading

The Teams PowerShell module has `New-TeamsApp` and `Set-TeamsApp`:

```powershell
New-TeamsApp -DistributionMethod organization -Path ./appPackage.zip
Set-TeamsApp -Id <catalogId> -Path ./appPackage.zip   # "Updates an app in the Teams tenant app store"
```

**Neither is on the app-based-auth exclusion list**, and neither was exercised this session —
publishing went through Graph, and every PowerShell call used device-code (delegated). Read literally,
their absence from that list says catalog upload works with **certificate-based app-only** auth.

That contradicts the Graph table, and the contradiction may not be a doc bug, because **the two
authorization models are different**:

> "Teams PowerShell Module fetches the app-based token using the application ID, tenant ID and
> certificate thumbprint. The application object provisioned inside Microsoft Entra ID **has a
> Directory Role assigned to it**, which is returned in the access token. The session's role-based
> access control (RBAC) is configured using the directory role information that's available in the
> token."

Teams PowerShell app-only auth is **directory-role-based**, not Graph-app-permission-based. A service
principal holding the **Teams Administrator** directory role presents a token the Teams admin API may
treat as an admin principal — a path that could work where Graph application permissions are refused.

**This is worth 30 minutes, because it is the difference between "one manual step per bot" and "fully
automated publish."** The test:

1. Register an Entra app; attach a certificate; assign it the **Teams Administrator** directory role.
2. Grant Graph app permissions `Organization.Read.All` + `AppCatalog.ReadWrite.All` (per the app-auth
   doc's table for non-`*-Cs` cmdlets).
3. `Connect-MicrosoftTeams -CertificateThumbprint … -ApplicationId … -TenantId …`
4. `New-TeamsApp -DistributionMethod organization -Path ./appPackage.zip`

Prefer the `-Certificate` (X509Certificate2 object) variant over `-CertificateThumbprint` — the
thumbprint form requires the cert in the user certificate store, while the object form can be fetched
at runtime from Secrets Manager. **Run it in the dev tenant, not Cornell's.**

Note that even if this succeeds, availability scoping still can't be app-only, so the ceiling is
"publish automated, scoping manual."

---

## Escape Hatches, Ranked

For the steps that require a delegated identity:

1. **Accept them as manual, one-time per bot.** Cheapest and honest. A runbook step performed once at
   bot onboarding by whoever holds Teams Administrator. Everything per-deployment stays automated.
2. **ROPC with a dedicated service account.** A delegated token obtained non-interactively via
   username/password against a no-MFA account. It *works technically*. **Do not propose this to
   Cornell without expecting a no** — it means a Teams-admin-capable account exempted from MFA and
   Conditional Access with its password in a secret store, which is a worse security posture than a
   manual step and should be described that way rather than as a clever workaround.
3. **Device-code with a persisted refresh token** (`offline_access`). Human authenticates once,
   pipeline refreshes. Fragile — refresh tokens expire and CA policies revoke them — and it smuggles a
   user identity into CI. Not recommended.

Recommendation: **option 1**, after running the `New-TeamsApp` test above, which may shrink what
option 1 has to cover.

---

## What This Means for the Blueprint

The important reframing: **nothing on the Microsoft side is per-deployment except the messaging
endpoint**, and that one *is* app-only automatable.

```
ONE-TIME, per bot                          EVERY DEPLOYMENT
─────────────────────                      ────────────────
Entra app + secret        [app-only ✓]     Lambda + AgentCore   [CloudFormation]
Azure Bot + MsTeams ch.   [app-only ✓]     Messaging endpoint   [az bot update ✓]
Publish to catalog        [delegated ✗]
Availability scoping      [delegated ✗]
```

- **`requirements.md` §9's "manual runbook covers v1" is the right call, for a sharper reason than
  was recorded** — not "Terraform is out of scope for time," but "the Teams catalog boundary is
  delegated-only by documented design, and the rest is one-time anyway." Worth recording, because it
  changes whether anyone should revisit the decision. (They shouldn't, unless Microsoft ships
  application permissions for `appCatalogs/teamsApps`.)
- **FR-7 can be tightened.** It says "it is accepted that deleting and recreating the stack requires
  one manual update of the messaging endpoint in Azure." It doesn't: a post-deploy step can read the
  Lambda function URL from the stack output and push it with `az bot update --endpoint`.
- **The Terraform stage may not be worth building for this.** The automatable Microsoft surface is ~4
  resources created once. A small idempotent script from CodeBuild is arguably a better fit than a
  Terraform stage with remote state and the secret-in-state problem. If Terraform is wanted anyway:
  `azuread` + `azurerm` cover the app-only rows, and **no provider covers the catalog rows** —
  Microsoft's `microsoft/msgraph` provider (public preview) is "a very thin layer on top of the
  MSGraph REST APIs," so it inherits the delegated-only limitation *and* is unlikely to handle a
  `Content-Type: application/zip` binary body.

---

## Azure Bot Service Side (`az bot`)

`az bot` is a native Azure CLI command group (no extension needed), including
`az bot msteams create/delete/show` for the Teams channel specifically — confirmed via `--help`, not
live-exercised this session.

**Cross-tenant subscription, resolved:** the existing PoC's Bot Service resource
(`jcb-ai-test-azure-bot`, RG `jcb-it-webcloud`) lives in the **"JCB IT NSS" subscription**
(`03b81814-f558-40c5-ba49-d699810cf323`), whose home/Entra directory is Cornell's tenant
(`5d7e4366-1b9b-45cf-8e79-b14b27df46e1`) — **not** the dev tenant
(`3ce7e7fb-ef51-4972-bfd5-f43f6668ccca`) used for the Entra app registration and Teams testing. This
isn't a B2B guest/Lighthouse delegation — it's simpler: the ARM resource and subscription belong to
Jason's separate **Cornell staff identity** (`jdw5@cornell.edu`), distinct from the dev-tenant global
admin identity (`jdw5@8chzbf.onmicrosoft.com`) used everywhere else. `az` supports multiple cached
tenant logins side by side (`az login --tenant <cornellTenantId>` picked up an existing browser SSO
session instantly, no new credentials needed), and switching
`az account set --subscription "JCB IT NSS"` afterward gave full `az bot show` access:

```bash
az login --tenant 5d7e4366-1b9b-45cf-8e79-b14b27df46e1   # authenticates as jdw5@cornell.edu
az account set --subscription "JCB IT NSS"
az bot show --name jcb-ai-test-azure-bot --resource-group jcb-it-webcloud -o json
```

The `az bot show` output confirms the mechanism behind "configured to connect to the dev tenant": the
ARM resource's own `properties.tenantId` is Cornell's (`5d7e4366-…`, matching the
subscription/resource-group home), but nested under it, `properties.msaAppTenantId` is explicitly set
to the **dev tenant** (`3ce7e7fb-…`) with `properties.msaAppType: "SingleTenant"` and
`properties.msaAppId` = the dev-tenant Entra app registration's client ID (`e6ee0253-…`). So: **the
Bot Service ARM resource and its hosting subscription are Cornell's; the Bot Framework app it
authenticates as is pinned to the dev tenant.** Two independent tenant references on the same
resource — expected, documented Azure Bot Service behaviour for a "use existing app registration in
another tenant" setup, not a misconfiguration.

Practical takeaway: use `az login --tenant 5d7e4366-…` + the Cornell identity for anything touching
the ARM/Bot Service layer; use the dev-tenant global admin login for anything touching Entra app
registrations, the Teams app catalog, or tenant settings. The dev-tenant login stays cached
(`az account list` shows it as `N/A(tenant level account)`) — switching back is
`az account set --subscription 3ce7e7fb-…`, no re-login.

---

## az CLI Version Currency

Installed `az` (via the nix flake): **2.79.0**. Latest upstream release as of August 2026 reported as
**2.88.0** (2026-07-07) — *not independently verified.*

The 2.79.0 install is *not* drift/breakage — it's exactly what's locked: both the `nixpkgs`
(nixos-25.11) and `nixpkgs-unstable` inputs in `flake/flake.lock` resolve `azure-cli` to 2.79.0 at
their locked revisions. A fresher (unlocked) nixpkgs-unstable already provides 2.88.0. Notably
`flake/flake.nix` already declares `nixpkgs-unstable` as an input but never binds/uses it — only
`pkgs = nixpkgs.legacyPackages.${system}` is used in `buildInputs`. To pick up a newer az CLI while
keeping everything else on the stable 25.11 pin: run `nix flake update nixpkgs-unstable` inside
`flake/`, then bind `pkgs-unstable = nixpkgs-unstable.legacyPackages.${system}` and swap
`pkgs.azure-cli` → `pkgs-unstable.azure-cli` in `buildInputs`. Not applied — flagged for Jason to
decide whether the gap matters (nothing in this session required a newer az CLI; the blockers were
scope/permission issues, not version issues).

---

## Provenance and Caveats

- Live tests ran on a Mac against the **dev tenant**, as a global admin, 2026-08-03. Rows marked
  "documented only" or "not tested" were not executed.
- Supporting artifacts (`cli-poc-test-app/`, `test-m365-teams-app.ps1`,
  `test-m365-teams-app-write.ps1`, `flake/flake.nix`, `flake/flake.lock`) live in Jason's local
  working directories, **not in this repository** — the paths above won't resolve for a reader here.
- This document contains real tenant, subscription, group, catalog and bot IDs plus named identities.
  No credentials — but this repo is public, so that's worth a deliberate decision rather than a
  default.

## Sources

- Graph permission tables, read from doc source rather than rendered pages:
  [teamsapp-publish](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/teamsapp-publish-permissions.md),
  [teamsapp-update](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/teamsapp-update-permissions.md),
  [beta teamsapp-publish](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/beta/includes/permissions/teamsapp-publish-permissions.md),
  [applications](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/application-post-applications-permissions.md),
  [addPassword](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/application-addpassword-permissions.md),
  [user installedApps](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/userteamwork-post-installedapps-permissions.md)
- [Publish teamsApp](https://learn.microsoft.com/en-us/graph/api/teamsapp-publish?view=graph-rest-1.0) — `requiresReview` semantics, approve-via-PATCH
- [Application-based authentication in Teams PowerShell Module](https://learn.microsoft.com/en-us/microsoftteams/teams-powershell-application-authentication) — exclusion list, directory-role model
- [`New-CsGroupPolicyAssignment`](https://learn.microsoft.com/en-us/powershell/module/microsoftteams/new-csgrouppolicyassignment?view=teams-ps) — policy types excluded from group assignment
- [`Update-M365TeamsApp`](https://learn.microsoft.com/en-us/powershell/module/teams/update-m365teamsapp), [`New-TeamsApp`](https://learn.microsoft.com/en-us/powershell/module/teams/new-teamsapp), [`Connect-MicrosoftTeams`](https://learn.microsoft.com/en-us/powershell/module/teams/connect-microsoftteams)
- [`az bot`](https://learn.microsoft.com/en-us/cli/azure/bot?view=azure-cli-latest) / [`az bot msteams`](https://learn.microsoft.com/en-us/cli/azure/bot/msteams?view=azure-cli-latest)
- [`azurerm_bot_service_azure_bot`](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/bot_service_azure_bot)
- [Teams app CI/CD templates](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/use-cicd-template)
- [Verify first-party Microsoft applications in sign-in reports](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/governance/verify-first-party-apps-sign-in) — confirms the Graph CLI Tools client ID

Doc-based claims checked 2026-08-03. Live-tested claims are marked as such inline.
