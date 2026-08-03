# Entra / Microsoft-Side CLI Automation — Research 2026-08-03

## Question

Can the entire Microsoft side of the `teams-bot` blueprint be provisioned from a CLI —
non-interactively, from CodeBuild, with no human clicking in a portal? The repo's hard constraint is
"everything is IaC and deploys through GitHub; no click-ops," and `requirements.md` §9 currently
parks the Microsoft side as "a manual runbook covers v1." This asks whether that concession is
actually forced.

## Verdict

**No — but the gap is one specific step, not the chain.** The split is clean and lands on a
documented boundary:

| Layer | Automatable unattended? |
| --- | --- |
| Entra app registration + client secret | **Yes** — app-only supported |
| Azure Bot Service resource, MsTeams channel, messaging endpoint | **Yes** — `az` / Terraform, service principal |
| **Teams app package → tenant app catalog (publish, approve, scope)** | **No** — documented as requiring a *user* identity |
| Installing an already-published app for users/teams | **Yes** — app-only supported |

Everything that is **per-deployment** is automatable. The step that is not automatable is
**per-bot, one-time onboarding**. That distinction is what makes this tolerable rather than fatal —
see *What this means for the blueprint*.

One item is genuinely **unresolved and only a live test can settle it** — the Teams PowerShell
`New-TeamsApp` / `Set-TeamsApp` route. Documentation points both ways. Details below.

---

## The chain, step by step

The identity chain from `Teams Bot Setup - Findings 2026-04-06.md`, annotated with automation path.

### 1. Entra app registration + client secret — fully automatable, app-only ✓

`POST /applications` and `POST /applications/{id}/addPassword` both support **Application**
permissions:

| API | Application permission (least privileged) |
| --- | --- |
| `POST /applications` | `AppRegistration.Create` (also `Application.ReadWrite.OwnedBy`, `Application.ReadWrite.All`) |
| `POST /applications/{id}/addPassword` | `Application.ReadWrite.OwnedBy` |

Sources: [application-post-applications-permissions.md](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/application-post-applications-permissions.md),
[application-addpassword-permissions.md](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/application-addpassword-permissions.md).

`Application.ReadWrite.OwnedBy` is the right choice: it lets the pipeline's service principal manage
only applications it owns, not every app in Cornell's tenant. Worth insisting on — a CI credential
holding `Application.ReadWrite.All` over Cornell's tenant is a much bigger blast radius than this
blueprint warrants.

- **CLI:** `az ad app create`, `az ad app credential reset`
- **Terraform:** `azuread_application`, `azuread_service_principal`, `azuread_application_password`

**Caveat on Terraform for the secret.** `azuread_application_password` puts the generated secret in
Terraform **state**. That collides with "secrets live only in AWS Secrets Manager." Two ways out:
generate the secret with a script step that writes straight to Secrets Manager and never lands it in
state, or accept state as a secret store and encrypt/lock it accordingly. The first is the better
fit for this repo. This is a real design decision, not a detail.

**Prefer a certificate over a secret if the Entra side allows it** — it removes R-3 (secrets expire,
tracked by a person). Not free: the bot's outbound `client_credentials` call would need to sign a
client assertion rather than send a secret, which is more code in the Lambda.

### 2. Azure Bot Service resource — fully automatable, service principal ✓

`az bot create` takes everything needed:

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
```

`--app-type` accepts `SingleTenant`, which is what the 2026-04 research concluded is required
(multi-tenant bot creation was deprecated after 2025-07-31). `--tags` is supported, so the four
`cornell:*` tags can be applied here too.

- **Terraform:** `azurerm_bot_service_azure_bot` — `microsoft_app_type = "SingleTenant"`,
  `microsoft_app_id`, `microsoft_app_tenant_id`, `endpoint`, `sku`, `tags`. The provider docs carry
  the same deprecation note: *"Creation of `azurerm_bot_service_azure_bot` resources using the
  `MultiTenant` type is no longer supported by Azure."*
- Requires Azure **Contributor on the resource group** — an Azure RBAC role, not an Entra or Teams
  admin role. Cornell already has this arrangement (`jcb-it-webcloud`).
- Likely prerequisite to check on a fresh subscription: `az provider register --namespace
  Microsoft.BotService`. Not verified here.

### 3. Microsoft Teams channel on the bot — fully automatable ✓

`az bot msteams create --name <bot> --resource-group <rg>`

- **Terraform:** `azurerm_bot_channel_ms_teams`

### 4. Messaging endpoint updates — fully automatable ✓

`az bot update --name <bot> --resource-group <rg> --endpoint https://<new-url>/`

**This closes FR-7's accepted manual step.** `requirements.md` FR-7 says "it is accepted that
deleting and recreating the stack requires one manual update of the messaging endpoint in Azure."
It doesn't have to be manual — a post-deploy step can read the Lambda function URL from the stack
output and push it to the bot resource with one command. Worth revisiting when the blueprint is
built.

### 5. Teams app package (the zip) — fully automatable ✓

Building the zip is just `manifest.json` + two icons, zipped. No tool required; `atk package` will
do it, or a `zip` invocation will.

**This is strictly better than the Developer Portal GUI path.** The 2026-04 research hit a portal
bug where `supportsChannelFeatures: "tier1"` — required by the v1.25 schema for `team` scope — was
not exposed in the UI and was *rejected by the portal's own validator* when placed correctly.
Authoring the manifest as a file in git sidesteps that entirely, and makes the manifest reviewable
like everything else.

### 6. Publish to the tenant app catalog — **NOT automatable unattended** ✗

This is the wall. `POST /appCatalogs/teamsApps`:

| Permission type | Least privileged | Higher privileged |
| --- | --- | --- |
| Delegated (work or school account) | `AppCatalog.Submit` | `AppCatalog.ReadWrite.All`, `Directory.ReadWrite.All` |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| **Application** | **Not supported.** | **Not supported.** |

Identical table for `POST /appCatalogs/teamsApps/{id}/appDefinitions` (publishing a new version),
and **identical in `beta` as well as `v1.0`** — so this is not a v1.0 lag waiting on a beta
promotion. I checked beta specifically for that reason.

Two further constraints from the same docs:

- `AppCatalog.Submit` **submits for review only** — it cannot publish. Publishing needs
  `AppCatalog.ReadWrite.All` or `Directory.ReadWrite.All`, delegated.
- The update API adds: *"Only Teams Service admins or a higher privileged role can call this API."*

The `requiresReview` query parameter is what decides whether a submission needs a second human:
*"Users with admin privileges can submit apps without triggering a review… A user who has admin
privileges can opt not to set requiresReview or set the value to false and the app is approved and
immediately published."* So **a Teams-admin user token publishes in one call, no review queue** —
the two-step approve dance the 2026-04 research documented is avoidable. It still needs a user
token.

Approving a pending submission is also API-driven —
`PATCH /appCatalogs/teamsApps/{id}/appDefinitions/{defId}` with `{"publishingState":"published"}` —
but inherits the same delegated-only permissions.

### 7. App availability scoping and pre-installation — user-only via PowerShell ✗

`Update-M365TeamsApp` is the cmdlet for the post-deprecation per-app model (the 2026-04 research
found "Permission policies" deprecated in favour of per-app settings in Manage apps). It does
everything needed:

- `-AppAssignmentType Everyone | UsersAndGroups | Noone` — who can install
- `-IsBlocked` — app state
- `-AppInstallType` / `-InstallForUsers` / `-InstallForGroups` — **pre-install for named users/groups**

That last one is a capability the GUI research didn't surface: the bot can be pushed to users rather
than waiting for them to install it.

**But** `[Get|Update]-M365TeamsApp` is on the explicit exclusion list for app-based authentication in
the Teams PowerShell module. So is `Update-M365UnifiedCustomPendingApp` (approving pending custom
apps) and `[Get|Update]-M365UnifiedTenantSettings`. These require a signed-in user.

### 8. Installing a published app for users / teams — automatable, app-only ✓

`POST /users/{id}/teamwork/installedApps` **does** support Application permissions
(`TeamsAppInstallation.ReadWriteSelfForUser.All` and friends). So once an app is in the catalog,
distributing it is automatable app-only. The wall is publication, not installation.

*(The equivalent team-scoped install — `POST /teams/{id}/installedApps` — I did not verify the
permission table for. Assume app-only works, confirm before relying on it.)*

---

## Corroboration: Microsoft's own CI/CD template stops at the same line

The official [CI/CD templates](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/use-cicd-template)
page for Teams apps is worth reading as evidence. Its GitHub Actions pipeline does:

1. `atk auth login azure --service-principal true --interactive false` ← **Azure, app-only**
2. `atk deploy --interactive false`
3. `atk package`
4. `actions/upload-artifact` — uploads `appPackage.zip` **as a build artifact**

There is **no publish step and no M365 login step in the pipeline at all.** Microsoft's own
recommended automation produces the zip and hands it off. Two independent sources — the Graph
permission tables and Microsoft's reference pipeline — land on the same boundary. That is the
confirmation worth having.

---

## The one unresolved question — needs a test, not more reading

The Teams PowerShell module has `New-TeamsApp` and `Set-TeamsApp`:

```powershell
New-TeamsApp -DistributionMethod organization -Path ./appPackage.zip
Set-TeamsApp -Id <id> -Path ./appPackage.zip   # "Updates an app in the Teams tenant app store"
```

**Neither is on the app-based-auth exclusion list.** The doc's rule is *"All cmdlets are supported
now, except…"* followed by a list that names `[Get|Update]-M365TeamsApp` and
`Update-M365UnifiedCustomPendingApp` but **not** `New-TeamsApp` / `Set-TeamsApp`. Read literally,
that says catalog upload works with certificate-based app-only auth.

That contradicts the Graph table — and the contradiction is not obviously a doc bug, because **the
two authorization models are different**:

> "Teams PowerShell Module fetches the app-based token using the application ID, tenant ID and
> certificate thumbprint. The application object provisioned inside Microsoft Entra ID **has a
> Directory Role assigned to it**, which is returned in the access token. The session's role-based
> access control (RBAC) is configured using the directory role information that's available in the
> token."

Teams PowerShell app-only auth is **directory-role-based**, not Graph-app-permission-based. A service
principal holding the **Teams Administrator** directory role presents a token the Teams admin API
may treat as an admin principal — a path that genuinely could work where Graph application
permissions are refused.

**This is worth 30 minutes of testing, because it is the difference between "one manual step per
bot" and "fully automated."** The test:

1. Register an Entra app; attach a certificate; assign it the **Teams Administrator** directory role.
2. Grant Graph app permissions `Organization.Read.All` + `AppCatalog.ReadWrite.All` (per the
   app-auth doc's table for non-`*-Cs` cmdlets).
3. `Connect-MicrosoftTeams -CertificateThumbprint … -ApplicationId … -TenantId …`
4. `New-TeamsApp -DistributionMethod organization -Path ./appPackage.zip`

If that succeeds, steps 6 and 7 above collapse to automatable and the Microsoft side is fully
IaC-able except for availability scoping (`Update-M365TeamsApp`, which is definitively excluded).
If it fails, the finding stands as written. **Do this in the dev tenant, not Cornell's.**

Note the module runs on PowerShell 7 / Linux, so a CodeBuild step is plausible — but the
`-CertificateThumbprint` variant requires the cert in the user certificate store, so prefer the
`-Certificate` (X509Certificate2 object) variant, which can be fetched at runtime from Secrets
Manager.

---

## Escape hatches, ranked

If the `New-TeamsApp` test fails, the options for the catalog step are:

1. **Accept it as manual, one-time per bot.** Cheapest and honest. A runbook step, done once when a
   bot is onboarded, by whoever holds Teams Administrator. Everything per-deployment stays automated.
2. **ROPC with a dedicated service account.** A delegated user token obtained non-interactively via
   username/password against a no-MFA account. This *works technically* for delegated Graph scopes,
   and it is what earlier Teams Toolkit CI guidance leaned on. **Do not propose this to Cornell
   without expecting a no** — it means a Teams-admin-capable account exempted from MFA and
   Conditional Access, with its password in a secret store. That is a worse security posture than a
   manual step, and it should be described that way rather than as a clever workaround.
3. **Device-code flow with a cached refresh token.** Human authenticates once; pipeline refreshes.
   Fragile (refresh tokens expire, CA policies revoke) and it smuggles a user identity into CI.
   Not recommended.

My read: **option 1**, plus run the test in *The one unresolved question* first, because it may make
the whole discussion moot.

---

## What this means for the blueprint

The important reframing: **nothing on the Microsoft side is per-deployment except the messaging
endpoint**, and that one *is* automatable (step 4).

```
ONE-TIME, per bot                          EVERY DEPLOYMENT
─────────────────────                      ────────────────
Entra app + secret        [auto ✓]         Lambda + AgentCore   [CloudFormation]
Azure Bot + MsTeams ch.   [auto ✓]         Messaging endpoint   [az bot update ✓]
Publish to catalog        [MANUAL ✗]
Availability scoping      [MANUAL ✗]
```

So `requirements.md` §9's "manual runbook covers v1" is **the right call, for a sharper reason than
was recorded**: not "Terraform is out of scope for time," but "the Teams catalog boundary is
delegated-only by documented design, and the rest is one-time anyway." Worth recording that
distinction — it changes whether anyone should revisit the decision later. (They shouldn't, unless
Microsoft ships application permissions for `appCatalogs/teamsApps`.)

Two concrete follow-ons for the blueprint work, neither blocking:

- **FR-7 can be tightened.** The accepted manual endpoint update is avoidable (step 4).
- **The Terraform stage may not be worth building for this.** The repo reserves Terraform for
  non-AWS resources, but the automatable Microsoft surface here is ~4 resources created once. A
  small idempotent script invoked from CodeBuild is arguably a better fit than standing up a
  Terraform stage with remote state and a secret-in-state problem. If Terraform is wanted anyway:
  `azuread` + `azurerm` cover steps 1–4, and **no provider covers step 6** — Microsoft's new
  `microsoft/msgraph` provider (public preview) is "a very thin layer on top of the MSGraph REST
  APIs," so it inherits the delegated-only limitation *and* is unlikely to handle a
  `Content-Type: application/zip` binary upload.

---

## Sources

- Graph permission tables (authoritative, from doc source rather than rendered pages):
  [teamsapp-publish](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/teamsapp-publish-permissions.md),
  [teamsapp-update](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/teamsapp-update-permissions.md),
  [beta teamsapp-publish](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/beta/includes/permissions/teamsapp-publish-permissions.md),
  [applications](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/application-post-applications-permissions.md),
  [addPassword](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/application-addpassword-permissions.md),
  [user installedApps](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/includes/permissions/userteamwork-post-installedapps-permissions.md)
- [Publish teamsApp](https://learn.microsoft.com/en-us/graph/api/teamsapp-publish?view=graph-rest-1.0) — `requiresReview` semantics, approve-via-PATCH
- [Application-based authentication in Teams PowerShell Module](https://learn.microsoft.com/en-us/microsoftteams/teams-powershell-application-authentication) — exclusion list, directory-role model
- [`az bot`](https://learn.microsoft.com/en-us/cli/azure/bot?view=azure-cli-latest) / [`az bot msteams`](https://learn.microsoft.com/en-us/cli/azure/bot/msteams?view=azure-cli-latest)
- [`azurerm_bot_service_azure_bot`](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/bot_service_azure_bot)
- [`Update-M365TeamsApp`](https://learn.microsoft.com/en-us/powershell/module/teams/update-m365teamsapp), [`New-TeamsApp`](https://learn.microsoft.com/en-us/powershell/module/teams/new-teamsapp), [`Connect-MicrosoftTeams`](https://learn.microsoft.com/en-us/powershell/module/teams/connect-microsoftteams)
- [Teams app CI/CD templates](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/use-cicd-template)

All checked 2026-08-03. Nothing in this document was tested against a live tenant.
