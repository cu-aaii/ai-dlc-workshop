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

**Almost all of it is scriptable. None of the Teams-facing parts are app-only.** Those are different
questions and conflating them is the easiest way to misread this document. There are really three
tiers, not two:

- **App-only (client credentials)** — a service principal with a secret or certificate, no human
  ever. Covers the Entra app registration **and its service principal**, the Azure Bot Service
  resource, its Teams channel, the messaging endpoint, push-installing an already-published app
  (**live-tested**), and — notably — **Teams App Setup Policies**, which are driven from Teams
  PowerShell rather than Graph and still need no human at all (**live-tested**).
- **Delegated + refresh token** — one interactive login, then silent token renewal for weeks or
  months with no browser. Covers the Graph app-catalog and tenant-settings calls. **Live-tested.**
  Not credential-only-forever: the refresh token rotates on every use and dies on inactivity or a
  conditional-access re-auth prompt.
- **Delegated only, no unattended path at all** — the `*-M365TeamsApp` cmdlets that do availability
  scoping. App-only certificate auth connects fine and then fails **401** on the cmdlet itself;
  granting Teams Administrator to the service principal does not fix it; and the one documented
  workaround (`-AccessTokens`, handing the module pre-minted delegated tokens) fails structurally.
  **All three live-tested.** This is now a closed question, not an open one.

The other axis: **the App Catalog and tenant app settings are reachable via Microsoft Graph — but
not via `az rest`.** Setup Policies (sideloading) and the legacy per-app Permission Policy have **no
Graph REST API at all**, but *are* scriptable via the Teams PowerShell module (`MicrosoftTeams`),
which is a genuine CLI, not the GUI. So the real split is Graph vs. Teams PowerShell vs. GUI —
crossed with the three auth tiers above.

### Summary — the core pipeline

Everything needed to get a bot published and available to a restricted audience, which is this org's
actual deployment model rather than a generic minimal bot. The last column is the auth tier above, not
a yes/no; that distinction is the whole point of this document.

| # | Step | Mechanism | Confirmed live? | Auth tier |
|---|---|---|---|---|
| 1 | Entra app registration + credential | `az ad app create`, `az ad app credential reset` | Not re-tested | **App-only** |
| 2 | Service principal for that app | `az ad sp create` | Not re-tested | **App-only** |
| 3 | Azure Bot Service resource | `az bot create` | `--help` only | **App-only** |
| 4 | Teams channel on the bot | `az bot msteams create` | `--help` only | **App-only** |
| 5 | Messaging endpoint | `az bot update --endpoint` | Not tested | **App-only** |
| 6 | Manifest + icons + zip | Plain files, no API | ✓ hand-authored, zero Developer Portal | n/a |
| 7 | **Publish to org catalog** | Graph `POST /appCatalogs/teamsApps` (zip body) | ✓ | Delegated + refresh — app-only **not supported** |
| 8 | **Availability scoped to an AD group** | `Update-M365TeamsApp -Groups …` | ✓ | **No unattended path** — conclusively |

**Step 2 is the easy one to miss.** The Azure Portal creates the service principal implicitly when you
register an application; the CLI and Graph do not. A script that runs `az ad app create` and stops has
produced an application object that cannot authenticate — and the resulting failure appears later, at
the bot's first outbound token request, nowhere near the cause.

**Step 8 is the one that matters most, and it is the confirmed dead end.** Every other step is
scriptable and all but one are fully app-only.

**Deliberately not in this list: Graph API permissions and admin consent for the bot itself.** Replying
to a Teams message never touches Microsoft Graph. The bot mints its own outbound token with
`client_credentials` against `api.botframework.com` — Bot Framework's own token service — authenticated
by nothing more than the app ID and credential from step 1. There is no API-permissions entry to add
and no admin-consent screen to click. That changes only if the bot itself starts calling Graph, to read
a calendar or send mail.

### Summary — extras

Established along the way, none of it required for the core pipeline. E-numbers match the source
research notes so the two documents can be read side by side. **E8 is the load-bearing one**: it is the
positive evidence that step 8's wall is endpoint-specific rather than module-wide.

| # | What it does | Mechanism | Confirmed live? | Auth tier |
|---|---|---|---|---|
| E1 | Graph permissions + admin consent, *if* the bot ever calls Graph | `az ad app permission add` / `admin-consent` | Not tested — ours needs none | App-only¹ |
| E2 | Directory role → service principal | Graph `POST /roleManagement/directory/roleAssignments` | ✓ | App-only¹ |
| E3 | Entra security / M365 group creation | `az ad group create` | Not tested | App-only |
| E4 | Update / resubmit / approve a catalog app | Graph `POST`/`PATCH …/appDefinitions` + `If-Match` | documented only | Delegated + refresh — app-only **not supported** |
| E5 | Tenant-wide app settings | Graph `GET`/`PATCH /teamwork/teamsAppSettings` | ✓ | Delegated + refresh — app-only **not supported** |
| E6 | Push-install into a **user's** scope | Graph `POST`/`DELETE /users/{id}/teamwork/installedApps` | ✓ 201/204, zero human | **App-only** |
| E7 | Push-install into a **team** | Graph `POST /teams/{id}/installedApps` | documented only | App-only, unverified |
| E8 | **Setup Policy** (sideloading grant) | `New-`/`Grant-`/`Get-`/`Remove-CsTeamsAppSetupPolicy` | ✓ full round trip, **app-only, zero human** | **App-only** |
| E9 | Legacy Permission Policy | `New-`/`Grant-CsTeamsAppPermissionPolicy` | Not re-tested | Probably app-only; **no group targeting at all** |
| — | List / delete catalog apps | Graph `GET`/`DELETE /appCatalogs/teamsApps` | ✓ | Delegated + refresh |
| — | Bot backend logic (webhook, JWT, replies) | Whatever hosts it (n8n in the prototype) | ✓ end-to-end | n/a |

¹ Assumes a bootstrap identity already privileged enough to grant privilege onward — someone, at some
point, was human-provisioned. Standard IAM bootstrapping, not Teams-specific.

**E8 changes how to read the wall.** Previously the strongest statement available was that
`Connect-MicrosoftTeams` *accepts* app-only certificate auth without complaint. Now a Teams PowerShell
cmdlet has been driven end to end under app-only auth with zero human involvement — created a policy,
granted it to a user, verified, reverted, deleted. So the limitation on `*-M365TeamsApp` is not the
module, not PowerShell, and not OAuth. It is those specific Unified App Management endpoints.

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

Then use the `access_token` as a normal bearer token with `curl` for every call below. Token lasted
~70 minutes, and no refresh token was requested — **single-shot by choice, not by Microsoft's
limitation.** See *Delegated but still unattended* for the `offline_access` variant.

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

## The App-Only Wall

This is the part that decides whether any of it can live in `pipeline.yml`. Checked directly against
Microsoft's API reference, per endpoint:

| Endpoint | Application (app-only) permission |
|---|---|
| `POST /appCatalogs/teamsApps` (publish) | **Not supported.** |
| `POST /appCatalogs/teamsApps/{id}/appDefinitions` (new version) | **Not supported.** |
| `PATCH /teamwork/teamsAppSettings` (tenant settings) | **Not supported.** |

Both catalog endpoints show the same table, and it is **identical in `beta` as well as `v1.0`** —
checked specifically, because "it's coming in beta" is the usual escape and here it isn't:

| Permission type | Least privileged | Higher privileged |
| --- | --- | --- |
| Delegated (work or school account) | `AppCatalog.Submit` | `AppCatalog.ReadWrite.All`, `Directory.ReadWrite.All` |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| **Application** | **Not supported.** | **Not supported.** |

Two further constraints from the same docs:

- `AppCatalog.Submit` **submits for review only** — it cannot publish. Publishing needs
  `AppCatalog.ReadWrite.All` or `Directory.ReadWrite.All`, delegated.
- The update API adds: *"Only Teams Service admins or a higher privileged role can call this API."*

This is hard-coded per endpoint. No amount of admin-consented Application permission works around it.

On the PowerShell side, the Teams module's app-based-authentication doc says *"All cmdlets are
supported now, except…"* and the exclusion list names:

- `Get-AllM365TeamsApps`
- **`[Get|Update]-M365TeamsApp`** ← the availability-scoping cmdlets
- `Get-M365UnifiedCustomPendingApps`, `Update-M365UnifiedCustomPendingApp` ← approving pending apps
- `[Get|Update]-M365UnifiedTenantSettings`

**Live testing confirms that exclusion list is accurate in both directions**, which makes it usable as
a predictor rather than just a warning:

- A cmdlet **on** the list — `Get-M365TeamsApp` — fails under app-only certificate auth. See
  *App-only auth for `Update-M365TeamsApp`* below, where the service principal connects successfully
  and then 401s.
- A cmdlet **absent from** the list — `Grant-CsTeamsAppSetupPolicy` — works under app-only certificate
  auth, driven end to end with zero human involvement. See *What does run unattended*.

So the list can be trusted when deciding whether some other Teams cmdlet is worth attempting.

**This is an endpoint-specific limitation, not a Teams-module one and certainly not a generic OAuth
one.** Client-credentials flow needs no human at all and works fine for the rest of the chain;
`Connect-MicrosoftTeams` accepts app-only certificate auth without complaint; and at least one Teams
PowerShell cmdlet has now been exercised app-only from connect through to a verified write and cleanup.
It is these specific Teams catalog and Unified App Management endpoints that decline it.

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

## Delegated but Still Unattended: the Refresh-Token Pattern

"Delegated" does **not** mean "a human clicks something on every run." If the initial interactive
login requests `offline_access`, you get a **refresh token** that silently mints new access tokens
with zero browser interaction — until it expires from inactivity, a conditional-access /
sign-in-frequency policy forces re-auth, or something revokes it. **Confirmed live, 2026-08-03:**

```bash
# One-time interactive step, WITH offline_access this time
curl -sS -X POST "https://login.microsoftonline.com/<tenantId>/oauth2/v2.0/devicecode" \
  -d "client_id=14d82eec-204b-4c2f-b7e8-296a70dab67e" \
  -d "scope=https://graph.microsoft.com/AppCatalog.ReadWrite.All https://graph.microsoft.com/TeamworkAppSettings.ReadWrite.All offline_access"
# ... complete interactively, exchange for tokens as before ...

# Store the refresh_token somewhere durable (Keychain, in this PoC):
security add-generic-password -s "m365-agents-sdk-devtenant" -a "GRAPH_CLI_TOOLS_REFRESH_TOKEN" -w "<refresh_token>" -U

# Later, with NO browser interaction at all:
REFRESH_TOKEN=$(security find-generic-password -s "m365-agents-sdk-devtenant" -a "GRAPH_CLI_TOOLS_REFRESH_TOKEN" -w)
curl -sS -X POST "https://login.microsoftonline.com/<tenantId>/oauth2/v2.0/token" \
  -d "grant_type=refresh_token" \
  -d "client_id=14d82eec-204b-4c2f-b7e8-296a70dab67e" \
  -d "refresh_token=$REFRESH_TOKEN" \
  -d "scope=https://graph.microsoft.com/AppCatalog.ReadWrite.All https://graph.microsoft.com/TeamworkAppSettings.ReadWrite.All"
# -> new access_token, works immediately for a real Graph call
#    (verified: GET /appCatalogs/teamsApps succeeded)
```

**Gotcha, confirmed live: refresh tokens rotate on every use.** The refresh call returns a *new*
`refresh_token`, and the old one may stop working. An unattended script must overwrite the stored
token after every refresh, not reuse one value forever. The Keychain entry was updated immediately
after testing and the rotated token confirmed.

Net effect: **"log in once, run unattended for weeks or months,"** not "credential-only, forever."
How long depends on this tenant's token lifetime and conditional-access policies — not measured.

For this repo, that reframes the CodeBuild question rather than closing it. A refresh token in
Secrets Manager, rewritten by the build on every run, would let the pipeline publish to the catalog.
It is still **a user's identity living in CI**, it still breaks on a CA policy change, and the
rotate-on-use requirement means a failed write leaves the pipeline unable to authenticate until a
human logs in again. Viable; not obviously wise. See *Escape hatches*.

---

## App-Only Auth for `Update-M365TeamsApp`: Tested, and It Does Not Work

`Connect-MicrosoftTeams` genuinely supports certificate-based app-only auth
(`-ApplicationId`/`-Certificate`, no user ever) — that part is real and confirmed live. The question
was whether the `*-M365TeamsApp` cmdlets work under it. Microsoft's own exclusion list says no; some
secondhand sources claim yes (GA since May 2024). **Direct testing sides with the exclusion list.**

**Test setup (2026-08-03):** a throwaway App Registration + service principal
(`m365-agents-sdk-unattended-poc`), a self-signed cert (30-day validity, PoC only) uploaded via
`az ad app credential reset --cert`, granted **both** `AppCatalog.ReadWrite.All` and
`Organization.Read.All` (Application, admin-consented) — the latter because `Connect-MicrosoftTeams`
itself failed with `Authorization_RequestDenied` until it was added, confirming the connect step needs
a baseline permission beyond the target cmdlet's own scope.

```powershell
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($pfxPath, $securePassword)
Connect-MicrosoftTeams -ApplicationId $appId -Certificate $cert -TenantId $tenantId
# -> succeeds, zero human interaction, Account column shows the appId itself

Get-M365TeamsApp -Id $catalogId
# -> ApiException, empty message. Introspecting $_.Exception directly (Get-Member/PSObject.Properties,
#    since the module's own error surfacing swallows the detail) reveals: ErrorCode: 401
```

**401, not 403 — that's the tell.** A 403 would mean "authenticated fine, wrong scope." A 401 means
the underlying call rejects the token itself, most likely because this Unified App Management endpoint
expects a token audienced for a different resource than app-only mode acquires — one the SDK may only
know how to obtain via a delegated flow.

**Escalating didn't help:** the **Teams Administrator** directory role
(`roleDefinitionId: 69091246-20e8-4a56-aa4d-066075b2a7a8`, assigned via
`POST /roleManagement/directory/roleAssignments` — service principals can hold directory roles
directly) was assigned to the service principal. Same 401, unchanged. **This rules out insufficient
permission as the cause**, and it disproves the "directory-role-based auth might succeed where Graph
application permissions are refused" theory for these cmdlets specifically.

**Cleaned up afterward:** directory role assignment removed, throwaway app registration deleted
(which also removes its service principal and permission grants), local cert/key files and the
Keychain-stored PFX password deleted.

**Conclusion: the AD-group-scoping step — the one flagged as most critical — has no path to true
app-only automation.** Treat "GA app-only support" claims for these two cmdlets as incorrect; the test
above sides with Microsoft's own exclusion list, so whatever source claimed otherwise was simply wrong.

### The documented workaround, also tested and also closed

The same official page documents `Connect-MicrosoftTeams -AccessTokens @($graphToken, $teamsToken)` —
handing the module pre-minted tokens instead of letting it run its own auth flow. That is the obvious
escape from the 401 above, because the tokens supplied can be genuinely **delegated** ones rather than
app-only, minted silently from the refresh-token pattern already proven for the Graph endpoints. It was
tested. It does not work either, and the reason is more fundamental than a permission problem.

Minting the tokens needed the real first-party **"Microsoft Teams PowerShell"** client,
`1fec8e78-bce4-4aaf-ab1b-5451cc387264` — verified empirically against the tenant. Worth recording that a
web-search-suggested alternative, `5170baac-d33f-4ab5-bc04-6ac2a602c700`, **does not exist in the tenant
at all** and was most likely fabricated by whatever produced it. Verify client IDs against the directory
before building anything on them.

With genuinely delegated tokens the call got further — no 401 this time — and surfaced the real blocker:

- `Get-M365TeamsApp` internally needs a **third** resource token, `https://substrate.office.com`, which
  it looks up from an internal dictionary populated only by whatever `-AccessTokens` supplies.
- `-AccessTokens` **hard-validates for exactly two tokens**, failing with *"Please provide the both
  MsGraph and Teams Configuration Resource token"*. It structurally cannot carry a third.
- A valid delegated Substrate token *was* minted from the same refresh token, confirming the gap is the
  parameter's shape and not the ability to obtain the token.

So no combination of tokens or scopes fixes this. The module's own native
`-UseDeviceAuthentication`/interactive/certificate connect flow is the only mechanism that juggles all
three resources internally — which is precisely why the original delegated device-code test worked
without anyone having to think about Substrate tokens — and the certificate variant of that same flow is
the one path Microsoft explicitly blocks for these cmdlets.

**That closes the loop.** There is currently no way to run `Update-M365TeamsApp`/`Get-M365TeamsApp` with
zero human involvement: not app-only, not via pre-minted delegated tokens, and not via any Terraform
provider, since none covers the feature.

The least-bad remaining idea is to keep the *same* PowerShell process alive as a long-running script
rather than a fresh one-shot invocation, relying on the module's own in-session token refresh. Whether
that survives long enough to be useful, and whether a session can be persisted across a process
restart, is **untested** — worth an hour only if this ever needs to run as a recurring job instead of an
interactive one-off.

### What remains genuinely open

**`New-TeamsApp` / `Set-TeamsApp` under app-only auth** — one question, and it is now more interesting
than it was, because the evidence points both ways.

These publish and update catalog apps from PowerShell, and unlike `*-M365TeamsApp` they are **not** on
the exclusion list. They have never been exercised: publishing went through Graph, and every PowerShell
call used device-code.

- **Reason to expect success:** E8 established that absence from the exclusion list *predicts* app-only
  support — `Grant-CsTeamsAppSetupPolicy` isn't listed and works app-only end to end. The list has now
  been verified in both directions.
- **Reason to expect failure:** the Graph endpoint these cmdlets presumably front,
  `POST /appCatalogs/teamsApps`, refuses Application permissions outright. If they are a thin wrapper
  over it, they inherit that.

The Substrate finding is what makes this genuinely open rather than merely unknown: it proves Teams
PowerShell does **not** simply proxy Graph — it talks to its own resources with their own auth rules. So
the Graph permission table may not govern these cmdlets at all.

**This is the highest-value remaining test in the whole investigation.** If `New-TeamsApp` works
app-only, catalog publish moves from "delegated, one human step per bot" to fully unattended, which
would change the escape-hatch ranking below and remove the last human step from the core pipeline
except availability scoping. It is cheap — the certificate PoC harness that produced the 401 is exactly
what is needed, and the test is a single cmdlet call.

---

## What *Does* Run Unattended, App-Only

### Entra app registration + client secret ✓

| API | Application permission (least privileged) |
| --- | --- |
| `POST /applications` | `AppRegistration.Create` (also `Application.ReadWrite.OwnedBy`, `Application.ReadWrite.All`) |
| `POST /applications/{id}/addPassword` | `Application.ReadWrite.OwnedBy` |

`Application.ReadWrite.OwnedBy` is the right choice: it lets the pipeline's service principal manage
only applications it owns, not every app in Cornell's tenant. Worth insisting on — a CI credential
holding `Application.ReadWrite.All` over Cornell's tenant is a far bigger blast radius than this
blueprint warrants.

- **CLI:** `az ad app create`, then **`az ad sp create`**, then `az ad app credential reset`
- **Terraform:** `azuread_application`, `azuread_service_principal`, `azuread_application_password`

**`az ad sp create` is a separate, mandatory step, and it is the one people leave out.** Registering an
application and creating its service principal are two distinct directory objects. The Azure Portal
does both when you click through the app-registration blade, so anyone who has only ever done this in
the GUI will reasonably assume `az ad app create` is sufficient. It isn't: the application object
describes the app, the service principal is the identity that can actually authenticate in the tenant.
Omit it and everything appears to succeed — the app registration exists, the secret is issued, the Bot
Service resource accepts the app ID — and the failure surfaces much later at the bot's first outbound
`client_credentials` call, with nothing pointing back at the missing object. Terraform users get this
right by accident, because `azuread_service_principal` is the documented companion resource.

**Caveat on Terraform for the secret.** `azuread_application_password` puts the generated secret in
Terraform **state**, which collides with "secrets live only in AWS Secrets Manager." Either generate
the secret in a script step that writes straight to Secrets Manager and never lands it in state, or
treat state as a secret store and protect it accordingly. The first fits this repo better.

**Prefer a certificate over a secret if the Entra side allows it** — it removes R-3 (secrets expire,
tracked by a person). Not free: the bot's outbound `client_credentials` call would need to sign a
client assertion instead of sending a secret, which is more code in the Lambda.

### Azure Bot Service + Teams channel + endpoint ✓

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

### Push-installing a published app ✓ — live-tested

`POST /users/{id}/teamwork/installedApps` supports Application permissions
(`TeamsAppInstallation.ReadWriteSelfForUser.All` and friends), and this is now **confirmed live rather
than documented only**: install and uninstall both exercised against a real user, returning 201 and 204,
under pure client-credentials auth with zero human involvement. The wall is publication and scoping, not
installation.

This enables a useful hybrid: **publish once by hand, then let the pipeline push-install app-only.**
Caveat — availability defaults to Everyone after publish, so if discovery needs restricting, the
`Update-M365TeamsApp` step comes back and with it a human. Push-install controls who *has* the app;
availability controls who can *find and self-install* it. They are not substitutes.

*(The team-scoped equivalent, `POST /teams/{id}/installedApps`, has the same Application permission in
its published table but was **not** independently live-tested — the user-scoped call was the one
exercised. Confirm before relying on it.)*

### Setup Policies — sideloading grants ✓ — live-tested, app-only

This one flipped from "unknown" to a clean yes. The full lifecycle of a Teams App Setup Policy was
driven under **certificate-based app-only auth with no human involvement at any point**: create the
policy, grant it to a user, read it back to verify, revert the grant, delete the policy.

```powershell
Connect-MicrosoftTeams -ApplicationId $appId -Certificate $cert -TenantId $tenantId
New-CsTeamsAppSetupPolicy   -Identity <name> ...
Grant-CsTeamsAppSetupPolicy -Identity <user> -PolicyName <name>
Get-CsTeamsAppSetupPolicy   -Identity <name>          # verify
Grant-CsTeamsAppSetupPolicy -Identity <user> -PolicyName $null   # revert
Remove-CsTeamsAppSetupPolicy -Identity <name>
```

`New-`/`Grant-`/`Get-`/`Remove-CsTeamsAppSetupPolicy` are **not** on Microsoft's app-only exclusion list,
and this test confirms the absence is meaningful rather than an oversight — which is what makes the list
usable as a predictor for other cmdlets.

Two things follow. First, the significance for this document is evidential more than practical: it is
the proof that the `*-M365TeamsApp` wall is endpoint-specific, not module-wide. Second, the practical
value for this blueprint is close to zero — Setup Policies grant *sideloading*, the "Upload custom apps"
permission, which stops mattering the moment an app is published to the org catalog. Recorded because it
was tested and because it moves the `New-TeamsApp` question, not because the blueprint needs it.

The legacy per-app **Permission Policy** cmdlets (`New-`/`Grant-CsTeamsAppPermissionPolicy`) are
**very likely** app-only too — the same `PolicyRp` backend showed up in this test's stack trace, and they
are absent from the exclusion list as well — but they were not re-tested, and they support no group
targeting at all regardless, so nothing here depends on it.

---

## Confirmed NOT Automatable via Graph: Setup Policies & Permission Policies

No Graph endpoint exists for assigning **Setup Policies** (the "Upload custom apps" sideloading
grant, per-user/per-group) or the legacy per-app **Permission Policy**. These remain Teams PowerShell
(`Connect-MicrosoftTeams`, `Set-CsTeamsAppSetupPolicy`, `Grant-CsTeamsAppSetupPolicy`,
`Set-CsTeamsAppPermissionPolicy`) or the Teams Admin Center GUI.

**"No Graph API" is not the same as "not automatable," and here the distinction is favourable:** the
Setup Policy cmdlets have since been live-tested and work under **app-only** auth, which is a stronger
result than the Graph-reachable catalog endpoints manage. See *Setup Policies* above. The absence of a
Graph endpoint costs nothing when the PowerShell path needs no human at all.

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
client in this investigation, after "Azure CLI" and "Microsoft Graph Command Line Tools." Each `pwsh`
process needed its own fresh device-code auth; no persistent token cache was observed the way `az`
has one.

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
`Mandatory: True`, which cannot simultaneously be true — a doc bug, not a subtlety.

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

**Conclusion: the full pipeline is scriptable end to end, under a delegated admin identity.** It is
not app-only at any point that touches Teams, and for group scoping specifically there is no known
unattended path at all yet.

---

## Escape Hatches, Ranked

For the steps that require a delegated identity:

1. **Accept them as manual, one-time per bot.** Cheapest and honest. A runbook step performed once at
   bot onboarding by whoever holds Teams Administrator. Everything per-deployment stays app-only
   automated.
2. **Delegated + `offline_access` refresh token in Secrets Manager.** Live-tested for the Graph calls.
   Gets "log in once, unattended for weeks." Costs: a user identity in CI, a rotate-on-every-use write
   that bricks the pipeline if it fails, and breakage on any conditional-access change. Reasonable for
   publish; **confirmed unavailable for group scoping** — `Connect-MicrosoftTeams` cannot be handed
   pre-minted tokens for these cmdlets, because `-AccessTokens` takes exactly two and the module needs
   three. That is a structural limit, not an untested gap, so this option cannot be extended to cover
   step 8 later.
3. **ROPC with a dedicated service account.** A delegated token from username/password against a
   no-MFA account. It *works technically*. **Do not propose this to Cornell without expecting a no** —
   it means a Teams-admin-capable account exempted from MFA and Conditional Access with its password
   in a secret store, which is a worse posture than a manual step and should be described that way
   rather than as a clever workaround. Option 2 dominates it: same "no human per run" outcome, no MFA
   exemption.

Recommendation: **option 1 for v1**, with option 2 as the considered upgrade if per-bot onboarding
volume ever makes the manual step painful.

---

## What This Means for the Blueprint

The important reframing: **nothing on the Microsoft side is per-deployment except the messaging
endpoint**, and that one *is* app-only automatable.

```
ONE-TIME, per bot                          EVERY DEPLOYMENT
─────────────────────                      ────────────────
Entra app + sp + secret   [app-only ✓]     Lambda + AgentCore   [CloudFormation]
Azure Bot + MsTeams ch.   [app-only ✓]     Messaging endpoint   [az bot update ✓]
Publish to catalog        [delegated]
Availability scoping      [delegated, no unattended path]
```

Text alternative: of the six pieces of work, four are one-time per bot and two happen on every
deployment. The one-time column is the Entra app registration with its service principal and credential
and the Azure Bot Service resource with its Teams channel — both fully app-only automatable — followed
by publishing to the catalog and scoping availability, which both need a delegated identity and the
second of which has no unattended path at all. The every-deployment column is the Lambda and AgentCore
resources, deployed by CloudFormation, and the messaging endpoint, pushed with `az bot update`; both are
app-only.

- **`requirements.md` §9's "manual runbook covers v1" is the right call, for a sharper reason than
  was recorded** — not "Terraform is out of scope for time," but "the Teams catalog and Unified App
  Management endpoints are delegated-only by design, live-tested, and the rest is one-time anyway."
  Worth recording, because it changes whether anyone should revisit the decision. **Revisit on exactly
  two triggers**: Microsoft shipping application permissions for `appCatalogs/teamsApps`, or
  `New-TeamsApp` turning out to work under app-only auth (the one open question above). The
  refresh-token route is no longer a third trigger — it is structurally closed for availability
  scoping.
- **FR-7 can be tightened.** It says "it is accepted that deleting and recreating the stack requires
  one manual update of the messaging endpoint in Azure." It doesn't: a post-deploy step can read the
  Lambda function URL from the stack output and push it with `az bot update --endpoint`.
- **The Terraform stage still looks not worth building, and the provider mapping now says why more
  precisely.** Every app-only row has a provider resource, and **no provider covers the two rows that
  need a human** — so Terraform would automate exactly the part a twenty-line script automates trivially,
  while adding remote state and the secret-in-state problem, and would still leave both delegated steps
  outside itself.

  | Step | Provider resource |
  |---|---|
  | 1 Entra app + credential | `azuread_application` + `azuread_application_certificate` / `azuread_application_password` |
  | 2 Service principal | `azuread_service_principal` |
  | 3 Bot Service | `azurerm_bot_service_azure_bot` — schema matches our live resource field for field (`microsoft_app_id`, `microsoft_app_type`, `microsoft_app_tenant_id`) |
  | 4 Teams channel | `azurerm_bot_channel_ms_teams` |
  | E1 Graph permissions | `azuread_app_role_assignment` |
  | E2 Directory role | `azuread_directory_role_assignment` |
  | E3 Group creation | `azuread_group` |
  | E6 Push-install | generic `msgraph_resource` (`microsoft/terraform-provider-msgraph`) |
  | **7 Publish to catalog** | **none** |
  | **8 Availability scoping** | **none** |

  The generic msgraph provider is what would otherwise plug the gap at rows 7 and 8, and it cannot:
  it supports **only app-only auth modes**, which are exactly what those two endpoints refuse. So the
  limitation is structural rather than a matter of the provider maturing — it is the same wall,
  reached from a different direction. (It is also "a very thin layer on top of the MSGraph REST APIs"
  and unlikely to handle a `Content-Type: application/zip` binary body, but that hardly matters given
  the auth mode already rules it out.)

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

- **This document is dated 2026-08-03 but incorporates a second round of live testing carried out
  2026-08-04**, folded in rather than filed separately so there is one place to look. The later round
  produced: the `-AccessTokens`/Substrate dead end, Setup Policies confirmed app-only, push-install
  confirmed live, and the `az ad sp create` gotcha. Where a claim's date matters it is stated inline.
- Live tests ran on a Mac against the **dev tenant**, as a global admin (device-code) and as a
  throwaway certificate-authenticated service principal (since deleted). Rows marked "documented only"
  or "not tested" were not executed.
- The unattended-auth PoC created and then removed: an app registration + service principal, a
  self-signed cert, a Teams Administrator directory role assignment, a Teams App Setup Policy and its
  user grant, a push-installed app on a real user, and local cert/key material.
  A refresh token for the Microsoft Graph Command Line Tools client remains in the operator's local
  Keychain. The `-AccessTokens` test additionally minted delegated tokens for three separate resources
  (Graph, Teams configuration, and Substrate); these were short-lived access tokens, not persisted.
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
- [`Update-M365TeamsApp`](https://learn.microsoft.com/en-us/powershell/module/teams/update-m365teamsapp), [`New-TeamsApp`](https://learn.microsoft.com/en-us/powershell/module/teams/new-teamsapp), [`Connect-MicrosoftTeams`](https://learn.microsoft.com/en-us/powershell/module/teams/connect-microsoftteams) — the last for `-AccessTokens`, which documents the two-token limit that closes the workaround
- [`New-CsTeamsAppSetupPolicy`](https://learn.microsoft.com/en-us/powershell/module/microsoftteams/new-csteamsappsetuppolicy) / [`Grant-CsTeamsAppSetupPolicy`](https://learn.microsoft.com/en-us/powershell/module/microsoftteams/grant-csteamsappsetuppolicy) — the app-only-confirmed sideloading grant
- [`az ad sp create`](https://learn.microsoft.com/en-us/cli/azure/ad/sp) — the separate service-principal step
- [Install app for user](https://learn.microsoft.com/en-us/graph/api/userteamwork-post-installedapps) / [Add app to team](https://learn.microsoft.com/en-us/graph/api/team-post-installedapps) — push-install permission tables
- [`microsoft/terraform-provider-msgraph`](https://registry.terraform.io/providers/microsoft/msgraph/latest/docs) — generic Graph provider; app-only auth modes only, which is why it cannot cover catalog publish or availability scoping
- [`az bot`](https://learn.microsoft.com/en-us/cli/azure/bot?view=azure-cli-latest) / [`az bot msteams`](https://learn.microsoft.com/en-us/cli/azure/bot/msteams?view=azure-cli-latest)
- [`azurerm_bot_service_azure_bot`](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/bot_service_azure_bot)
- [Teams app CI/CD templates](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/use-cicd-template)
- [Verify first-party Microsoft applications in sign-in reports](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/governance/verify-first-party-apps-sign-in) — confirms the Graph CLI Tools client ID

Doc-based claims checked 2026-08-03. Live-tested claims are marked as such inline.
