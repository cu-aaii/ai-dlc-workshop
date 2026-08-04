# Runbook: a Bedrock managed knowledge base with SharePoint as the ingestion source

A generalized walkthrough, written after building this twice — once by
discovery, once as a teardown-and-rebuild from notes. The ordering matters:
most of the failure modes below are things that only surface two steps later,
so a step that looks skippable usually isn't.

Scope: a Bedrock **managed** knowledge base whose content comes from one or
more SharePoint Online sites, authenticated with a certificate
(`ENTRA_ID_APP_ONLY`). Everything here has been observed on a live tenant, not
inferred from documentation.

## Status in this repo: reference only

**This changes no template and unpins nothing.** `../infra/knowledgebase.yml` still
deploys the S3 connector alone, and SharePoint stays pinned for the scope reason
in `decisions.md` — a second data source needs the verifier extended, or it can
go green while SharePoint is empty. Read this as the missing evidence for step 1
of *Unpinning it* in `../infra/azure/README.md` ("decide the auth story"), not as
a change of state.

It was validated on a **separate tenant and AWS account**, with its own Entra app
registration and its own certificate — not against
`dev/workshop/entra/sharepoint`, and not against the quick-start data source
`GBHYGKPMYL`. It contains no credentials and no account-specific identifiers;
every value is a placeholder. Keep it that way, since this repo is public and has
secret scanning disabled by org policy.

### What it settles

`decisions.md` records two retractions about SharePoint and closes with a
hypothesis for whoever unpins it: that the quick-start data source's scope
failure —

```
SharePoint app is missing required scopes: Missing required permissions:
[GroupMember.Read.All, User.Read.All,
 one of [Sites.FullControl.All, Sites.Selected, Sites.Read.All]]
```

— comes from `aclEnabled: true` plus `crawlIdentities: true`, and that turning
identity crawling off "should drop the requirement to a Sites scope alone."

**Confirmed.** The build documented here ingested successfully holding
`Sites.Selected` and nothing else, on both Microsoft Graph and the SharePoint
REST API. Neither `GroupMember.Read.All` nor `User.Read.All` was granted, and no
scope error occurred. Setting `aclEnabled: false` is sufficient —
`crawlIdentities` then defaults to `false` without being set explicitly, which
the service confirms in its echo of `connectorParameters`.

So the consent ask for an unpinning PR is `Sites.Selected` on two resource
applications plus one per-site grant (§6), not the five-permission ask the
quick-start failure implies. That is small enough to be a realistic request of an
Entra admin.

Three other findings bear directly on documents already in this directory:

- **`aclEnabled` is immutable after creation** (§1, §9). Since a second data
  source would arrive via CloudFormation, getting it wrong means a data-source
  replacement, not an update.
- **`connectorParameters` being unvalidated** is the same hazard `warnings.md`
  describes for the S3 connector, and it is worse here: the SharePoint body is
  larger, and §9 sets out which fields sit *inside* `connectorParameters`
  (opaque, unchecked) versus *beside* it (typed, checked).
- **`retrieve-and-generate` is not supported on a managed KB** (§11). The managed
  policy at `/aidlc/main/knowledgebase/retrieval-policy-arn` grants
  `bedrock:RetrieveAndGenerate`; a consumer calling it will fail regardless of
  IAM. Track C's bot needs the Retrieve-then-Converse shape.

**Observed timings**, so you can tell "slow" from "hung":

| Step | Duration |
|---|---|
| Entra app + consent | seconds |
| Deleting an `azuread_application_password` | ~20 s (slow enough to look hung) |
| KB `CREATING` → `ACTIVE` | 1–2 min |
| Data source `CREATING` → `AVAILABLE` | < 1 min |
| First sync, ~25 small documents | ~3 min |
| Data source `DELETING` → gone | ~4 min |
| Data source `UPDATING` | < 1 min |

---

## 0. The decision that governs everything else

Bedrock has two kinds of knowledge base:

| | Customer-managed | Managed |
|---|---|---|
| Config | `{"type":"VECTOR", "vectorKnowledgeBaseConfiguration":{...}}` + `storageConfiguration` | `{"type":"MANAGED"}`, no storage config |
| Vector store | Yours (OpenSearch Serverless, Aurora, Pinecone…) | Service-managed |
| Data sources | **S3 and Custom only** | S3, SharePoint, Confluence, Web Crawler, Google Drive, OneDrive, Custom |
| Embedding | You pick the model | Service-managed |
| Retrieve config | `vectorSearchConfiguration` | `managedSearchConfiguration` |
| Retrieve-and-generate | Supported | **Not supported** |
| Floor cost | OpenSearch OCUs (~$350/mo idle) | None |

**SharePoint requires a managed KB.** If you attach a SharePoint data source to
a customer-managed KB, creation succeeds and the *sync* fails — and the error
is misleading (`"secret has an invalid format or missing values"`, or
`"Failed to connect to the URL of your data source"`), because Bedrock is
failing partway down a path it cannot service. You will waste hours rewriting
the secret. Don't; check the KB type first.

A created managed KB echoes back
`knowledgeBaseConfiguration: {"type": "MANAGED", "managedKnowledgeBaseConfiguration": {"embeddingModelType": "MANAGED"}}`
and no `storageConfiguration` at all. That echo is the cheapest way to confirm
what you actually built, and `get-knowledge-base` is the cheapest way to find
out what kind someone else built.

Corollary: a managed KB has no OpenSearch Serverless collection, so it has no
OCU floor. A customer-managed KB stands up a collection that bills in the
hundreds of USD/month whether or not anything is indexed. If you built one by
mistake, tear it down the moment you know.

## 1. Decisions to lock before you start

Several of these are **immutable after creation** or expensive to change. Decide
them deliberately rather than discovering the default.

| Decision | Options | Changeable later? |
|---|---|---|
| KB type | `MANAGED` (required for SharePoint) | No — recreate the KB |
| `aclEnabled` | `true` / `false` | **No — recreate the data source** |
| Auth type | `ENTRA_ID_APP_ONLY` / `OAUTH2_APP` | Yes, via `update-data-source` |
| Permission scope | `Sites.Selected` / `Sites.Read.All` | Yes, in Entra |
| `crawlFiles` / `crawlPages` | booleans | Yes — but **narrowing does not purge** (§12) |
| `imageExtractionStatus` | `ENABLED` (default) / `DISABLED` | Yes — but existing captions persist until recreate |
| `dataDeletionPolicy` | `DELETE` / `RETAIN` | Set at create; `DELETE` is what makes recreation safe |
| Certificate lifetime | your `-days` | Rotation is a real procedure (§13) |

Parameters to fill in for a new build:

```sh
AWS_REGION=us-east-1
ACCOUNT_ID=…
TENANT_ID=…                 # Entra tenant (directory) ID
SITE_URL=https://<tenant>.sharepoint.com/sites/<site>
APP_NAME=bedrock-kb-<purpose>-connector
SECRET_NAME=bedrock/<purpose>-sharepoint-cert
CERT_BUCKET=bedrock-sharepoint-certs-${ACCOUNT_ID}
CERT_KEY=certs/certificate.p12
ROLE_NAME=bedrock-<purpose>-kb-role
KB_NAME=<purpose>-sharepoint-kb
```

**`SITE_URL` has a validated format.** It must start with `https://`, and the
path must begin with `/sites/`, `/teams/`, or `/personal/`. A tenant root URL
or a deep path to a subfolder is rejected — the connector takes *site* URLs and
crawls downward. To index one folder rather than a whole site, point at the
site and use `filterConfiguration`, or put the content in its own site.

## 2. Dead ends — what not to do

The AWS documentation contains two generations of SharePoint connector docs and
the older one leads nowhere. This list exists because each item cost real time.

1. **Don't follow the legacy connector page**
   (`…/bedrock/latest/userguide/sharepoint-data-source-connector.html`). It
   describes the preview connector for *vector* KBs (`"type": "SHAREPOINT"`
   with `sharePointConfiguration`). Follow the managed pages instead:
   `kb-managed-ds-sharepoint*.html` and
   `kb-managed-sharepoint-entra-setup.html`.
2. **Don't use `OAUTH2_SHAREPOINT_APP_ONLY_CLIENT_CREDENTIALS`.** It depends on
   Azure ACS, which Microsoft retired **2 April 2026**. It does not function at
   all any more, regardless of configuration.
3. **Don't use `OAUTH2_CLIENT_CREDENTIALS`** — it appears in older provider
   schemas and docs, but belongs to the legacy customer-managed connector. Its
   documentation claims a secret of just `clientId` + `clientSecret` works;
   against a managed KB the sync fails even when those same credentials work
   perfectly against Microsoft Graph directly.
4. **Don't use `OAUTH2_APP` (username/password ROPC)** unless you have no
   alternative: it cannot satisfy MFA or Conditional Access and does not
   support document-level ACLs.
5. **Don't create a client secret for the connector app.** Certificate auth
   uses only the certificate; a leftover secret is unused attack surface.
6. **Don't upload the `.p12` or the private key to Entra.** Entra gets the
   public `.cer` only. The `.p12` goes to S3 for Bedrock.
7. **Don't put `username`/`password` in the secret** for certificate auth. It is
   exactly `clientId` + `certificatePassword`, nothing else.
8. **Don't trust `az ad app permission admin-consent`.** It can silently fail to
   create the app-role assignment (§5).
9. **Don't query a managed KB with `vectorSearchConfiguration`**, and don't
   reach for `retrieve-and-generate` — both are rejected (§10, §11).

## 3. Tooling prerequisites

**Entra:** an account that can register applications and grant admin consent —
Global Administrator, Privileged Role Administrator, or Cloud Application
Administrator plus an admin who can consent.

**AWS:** permissions for Bedrock, Secrets Manager, S3, and IAM.

**AWS CLI / SDK must be recent.** `MANAGED_KNOWLEDGE_BASE_CONNECTOR` and
`--knowledge-base-configuration '{"type":"MANAGED"}'` do not exist in older
builds, and an old SDK silently funnels you into the broken legacy path — the
`authType` enum simply stops at `OAUTH2_SHAREPOINT_APP_ONLY_CLIENT_CREDENTIALS`
and there is no `MANAGED` KB type at all. Observed boundaries: CLI **2.17 and
2.35.18 lack it, 2.36.15 has it**; boto3 **1.43.40 lacks it, 1.43.63 has it**.

Cheap CLI check:

```sh
aws bedrock-agent create-data-source help | grep -c MANAGED_KNOWLEDGE_BASE_CONNECTOR
```

More robust, and the one to use in a script — interrogate the service model
rather than help text:

```sh
python3 -m venv /tmp/kbvenv && /tmp/kbvenv/bin/pip install -q --upgrade boto3
/tmp/kbvenv/bin/python -c "
import botocore.session
m = botocore.session.get_session().get_service_model('bedrock-agent')
assert 'MANAGED' in m.shape_for('KnowledgeBaseType').enum, 'boto3 too old'
assert 'MANAGED_KNOWLEDGE_BASE_CONNECTOR' in m.shape_for('DataSourceType').enum, 'boto3 too old'
print('SDK OK')
"
```

Upgrading the CLI needs no sudo:

```sh
curl -sS https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip
cd /tmp && unzip -qo awscliv2.zip
./aws/install --install-dir "$HOME/.local/aws-cli" --bin-dir "$HOME/.local/bin"
```

This leaves the system install alone, which also means **a fresh shell may still
resolve `aws` to the old one**. Record in your README which path to use, and
consider using an absolute path (`~/.local/bin/aws`) in scripts. A hybrid also
works well: the new binary or a venv for `bedrock-agent*` calls, the system CLI
for S3/IAM/Secrets Manager where the version is irrelevant.

**Terraform cannot express a managed KB.** The AWS provider (through at least
5.100) only offers `vector_knowledge_base_configuration` under
`knowledge_base_configuration` — customer-managed only. So Terraform owns the
dependencies (Entra app, certificate, S3, Secrets Manager, IAM role) and the KB
plus data source are created with the CLI or SDK. Record the resulting IDs in a
README so the split is obvious to the next person, and remember that
`terraform destroy` will leave the KB running.

**Shell notes**, both of which bit during validation:
- Snippets assume **bash**. Pasted into interactive zsh without
  `setopt interactive_comments`, `#` comment lines fail with
  `command not found: #`. Run as a script, or strip comments.
- If you work across separate shell sessions, **persist `APP_ID` and
  `SECRET_ARN`** (append `export` lines to an env file you `source`). Losing
  `APP_ID` mid-run is what produces half-configured apps.

## 4. Choose the SharePoint auth type

| | `ENTRA_ID_APP_ONLY` | `OAUTH2_APP` |
|---|---|---|
| Credentials | Certificate (`.p12` in S3) + client ID | Client ID/secret **plus a real user's username and password** (ROPC) |
| MFA / Conditional Access | Fine | Must be disabled for that user |
| ACL support | Yes | No |

Use `ENTRA_ID_APP_ONLY`. `OAUTH2_APP` requires a human account with MFA off,
which is usually a non-starter, and forecloses ACLs permanently.

Secret shapes differ:

```json
{"clientId": "…", "certificatePassword": "…"}                          // ENTRA_ID_APP_ONLY
{"clientId": "…", "clientSecret": "…", "username": "…", "password": "…"} // OAUTH2_APP
```

## 5. Entra ID app registration

### Permissions — two resource apps, not one

The connector talks to **both** Microsoft Graph and the SharePoint REST API.
These are separate resource applications and each needs its own grant:

| Resource | App ID |
|---|---|
| Microsoft Graph | `00000003-0000-0000-c000-000000000000` |
| SharePoint REST | `00000003-0000-0ff1-ce00-000000000000` |

Granting only Graph gets you a token that works for site metadata and fails on
content. Verify both audiences before blaming Bedrock (§8).

### Least privilege: `Sites.Selected`

`Sites.Read.All` reads every site in the tenant. `Sites.Selected` reads only
sites explicitly granted to the app. Prefer `Sites.Selected` — the extra work is
one API call per site (§6). Use `Sites.Read.All` only when the KB genuinely
should follow content across an unbounded set of sites.

A `Sites.*` scope on both resource applications is the **whole** permission set
needed, provided `aclEnabled` is `false`. Turn ACLs on and the connector also
crawls identities, which raises the ask to `GroupMember.Read.All` and
`User.Read.All` — tenant-wide group-membership and user-profile reads, a far
harder consent conversation. Bedrock validates granted scopes *before* it reaches
the site, so an ACL-enabled source missing those fails every sync with

```
SharePoint app is missing required scopes: Missing required permissions:
[GroupMember.Read.All, User.Read.All, one of [Sites.FullControl.All,
 Sites.Selected, Sites.Read.All]]
```

and zero documents scanned — which looks like a site-URL or certificate problem
and is neither. Decide ACLs against that cost, remembering it is immutable (§1).

**Look up app role IDs from your own tenant rather than copying them from notes
or memory.** Several are near-identical by eye and a wrong GUID silently grants
something else — this is exactly how a `Sites.Read.All` + `User.Read.All`
(tenant-wide user profile read) over-grant happens when you meant
`Files.Read.All`:

```sh
az ad sp show --id 00000003-0000-0000-c000-000000000000 \
  --query "appRoles[?value=='Sites.Selected'].{v:value,id:id}" -o json
az ad sp show --id 00000003-0000-0ff1-ce00-000000000000 \
  --query "appRoles[?value=='Sites.Selected'].{v:value,id:id}" -o json
```

Query with `-o json`, not `-o table` — the table renderer drops the `id` column
silently, which looks like the role having no ID rather than a formatting
artifact.

First-party app role IDs are stable across tenants, so these are useful as a
cross-check, but confirm rather than trust:

| Role | Resource | ID |
|---|---|---|
| `Sites.Selected` | Graph | `883ea226-0bf2-4a8f-9f9d-92c9162a727d` |
| `Sites.Selected` | SharePoint REST | `20d37865-089c-4dee-8c41-6967602d4ac8` |
| `Sites.Read.All` | Graph | `332a536c-c7ef-4017-ab91-336970924f0d` |
| `Sites.Read.All` | SharePoint REST | `d13f72ca-a275-4b96-b789-48ebcc4da984` |
| `Sites.FullControl.All` | Graph | `a82116e5-55eb-4c41-a434-62fe8a61c773` |

Then decode the token you actually get and confirm the `roles` claim matches
what you intended.

### Terraform shape

```hcl
resource "azuread_application" "connector" {
  display_name     = var.app_name
  sign_in_audience = "AzureADMyOrg"

  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000" # Graph
    resource_access {
      id   = local.graph_sites_selected
      type = "Role"                                          # application, not delegated
    }
  }

  required_resource_access {
    resource_app_id = "00000003-0000-0ff1-ce00-000000000000" # SharePoint REST
    resource_access {
      id   = local.sp_sites_selected
      type = "Role"
    }
  }
}

resource "azuread_service_principal" "connector" {
  client_id = azuread_application.connector.client_id
}

# Admin consent for an application permission. NOT
# azuread_service_principal_delegated_permission_grant — that is delegated-only
# and silently fails to consent a type="Role" permission.
resource "azuread_app_role_assignment" "graph" {
  app_role_id         = local.graph_sites_selected
  principal_object_id = azuread_service_principal.connector.object_id
  resource_object_id  = data.azuread_service_principal.msgraph.object_id
}
# …and the same again against the SharePoint REST service principal.
```

No `azuread_application_password` — certificate auth means the app should have
no client secret at all.

Removing an over-grant is just deleting its `azuread_app_role_assignment` from
the config; the next apply destroys the assignment.

### Azure CLI shape (if not using Terraform)

Use a **lookup-or-create** pattern. Two `az` behaviours make the naive version
fragile, both observed: `az ad app create` silently *patches* an existing app
with the same display name instead of failing, and `az ad sp create` errors with
`service principal name … is already in use` when the SP already exists from a
partial earlier run.

```sh
APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name "$APP_NAME" \
    --sign-in-audience AzureADMyOrg --query appId -o tsv)
fi
az ad sp show --id "$APP_ID" --output none 2>/dev/null || \
  az ad sp create --id "$APP_ID" --output none
```

Add the permissions, then consent. **Do not rely on
`az ad app permission admin-consent`** — it is unreliable for application
permissions and fails quietly. POST the `appRoleAssignments` directly, which is
also idempotent enough to re-run:

```sh
az ad app permission add --id "$APP_ID" \
  --api 00000003-0000-0000-c000-000000000000 --api-permissions "$GRAPH_ROLE=Role"
az ad app permission add --id "$APP_ID" \
  --api 00000003-0000-0ff1-ce00-000000000000 --api-permissions "$SPO_ROLE=Role"

SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
GRAPH_SP=$(az ad sp show --id 00000003-0000-0000-c000-000000000000 --query id -o tsv)
SPO_SP=$(az ad sp show --id 00000003-0000-0ff1-ce00-000000000000 --query id -o tsv)

for pair in "$GRAPH_SP:$GRAPH_ROLE" "$SPO_SP:$SPO_ROLE"; do
  RES="${pair%%:*}"; ROLE="${pair##*:}"
  az rest --method POST \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID/appRoleAssignments" \
    --body "{\"principalId\":\"$SP_ID\",\"resourceId\":\"$RES\",\"appRoleId\":\"$ROLE\"}" \
    --output none 2>/dev/null || echo "(already assigned: $ROLE)"
done

# Verify — expect BOTH role IDs. This check is the point of the exercise.
az rest --method GET \
  --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID/appRoleAssignments" \
  --query "value[].appRoleId" -o json
```

### Certificate

```sh
umask 077
mkdir -p .certs && chmod 700 .certs
openssl rand -base64 32 > .certs/p12_password      # write to file; never echo it
openssl req -x509 -newkey rsa:2048 -nodes -days 730 \
  -keyout .certs/private_key.pem -out .certs/certificate.cer \
  -subj "/CN=bedrock-sharepoint-connector"
openssl pkcs12 -export -out .certs/certificate.p12 \
  -inkey .certs/private_key.pem -in .certs/certificate.cer \
  -passout file:.certs/p12_password
openssl pkcs12 -in .certs/certificate.p12 -nokeys -passin file:.certs/p12_password >/dev/null \
  && echo "p12 opens with stored password"
```

Choose `-days` deliberately and write the expiry somewhere you will see it: an
expired certificate fails every sync, with no warning beforehand.

Upload the **public** `.cer` to the app registration:

```hcl
resource "azuread_application_certificate" "connector" {
  application_id = azuread_application.connector.id
  type           = "AsymmetricX509Cert"
  encoding       = "pem"
  value          = file("${path.module}/.certs/certificate.cer")
  end_date       = var.cert_end_date  # must be <= the cert's notAfter, or Entra rejects it
}
```

Or via CLI — **`--append` is essential**, since without it the command replaces
every existing credential on the app:

```sh
az ad app credential reset --id "$APP_ID" \
  --cert "@.certs/certificate.cer" --append --output none
az ad app show --id "$APP_ID" \
  --query "keyCredentials[].{type:type,end:endDateTime}" -o json
```

Gitignore `.certs/`, `*.tfstate*`, and `terraform.tfvars` — the `.p12` password
lands in both `.certs/` and Terraform state. If you generated the cert in a temp
directory instead, delete it once the `.p12` is in S3 and the password is in
Secrets Manager; nothing local is needed afterwards.

## 6. Per-site grant (only if using `Sites.Selected`)

`Sites.Selected` on its own grants **nothing**. Each site needs an explicit
grant, issued by a principal holding Graph `Sites.FullControl.All`. Create a
throwaway app for that, use it, then delete it — the grant survives the
granter's deletion (confirmed by re-running §8 afterwards).

```
POST https://graph.microsoft.com/v1.0/sites/{siteId}/permissions
{
  "roles": ["read"],
  "grantedToIdentities": [
    {"application": {"id": "<connector client id>", "displayName": "<app name>"}}
  ]
}
```

Resolve `{siteId}` with `GET /v1.0/sites/{host}:{server-relative-path}` — e.g.
`/v1.0/sites/contoso.sharepoint.com:/sites/kb`. It returns a compound
`host,siteGuid,webGuid` triple.

The response echoes the grant under both `grantedToIdentities` and
`grantedToIdentitiesV2`. `GET` the same path to list every grant on the site,
which is the check worth running before assuming a permission problem is
elsewhere. Newly-consented granter apps work immediately — no propagation wait
was needed.

Gate the granter behind a variable so removing it is one flag flip:

```hcl
resource "azuread_application" "granter" {
  count = var.create_granter ? 1 : 0
  # … Sites.FullControl.All …
}
```

## 7. AWS side

**S3** — private bucket, SSE-AES256, public access blocked, versioning on,
holding the `.p12`. The connector fetches it itself; it is never passed inline.

**Secrets Manager** — for `ENTRA_ID_APP_ONLY`, exactly two camelCase keys:

```json
{"clientId": "…", "certificatePassword": "…"}
```

Wrong key names produce the same generic `"invalid format or missing values"`
error as a wrong KB type, so this is worth getting right the first time.

**IAM role** — trust policy scoped to the service *and* the account and KB ARN,
which is what prevents a confused-deputy across tenants:

```json
{
  "Effect": "Allow",
  "Principal": {"Service": "bedrock.amazonaws.com"},
  "Action": "sts:AssumeRole",
  "Condition": {
    "StringEquals": {"aws:SourceAccount": "<account-id>"},
    "ArnLike": {"aws:SourceArn": "arn:aws:bedrock:<region>:<account-id>:knowledge-base/*"}
  }
}
```

Permissions: `secretsmanager:GetSecretValue` on the secret, `s3:ListBucket` on
the bucket, `s3:GetObject` on the certificate. The connector also probes for a
sibling `<key>.metadata.json`, so either grant the two exact keys or the
prefix — the explicit pair is tighter:

```json
"Resource": [
  "arn:aws:s3:::<bucket>/certs/certificate.p12",
  "arn:aws:s3:::<bucket>/certs/certificate.p12.metadata.json"
]
```

Add `"Condition": {"StringEquals": {"aws:ResourceAccount": "<account-id>"}}` to
the S3 statements so the role cannot be steered at a same-named bucket in
another account.

No `bedrock:InvokeModel` is needed: embedding is service-managed.

## 8. Verify Entra before touching Bedrock

Do this as a standalone script. It separates "Entra is misconfigured" from
"Bedrock is misconfigured", which is the single biggest time sink in this build,
and it turns an opaque sync failure into a concrete error. Sign a client
assertion with the private key (RS256; needs `PyJWT` and `cryptography`) and
request both audiences:

- `https://graph.microsoft.com/.default`
- `https://{tenant}.sharepoint.com/.default`

Decode each token and assert the `roles` claim contains what you granted — the
roles you assigned and the roles Entra actually attaches are not always the same
set. A correct result is `roles: ['Sites.Selected']` on both, with `aud` being
`https://graph.microsoft.com` and `00000003-0000-0ff1-ce00-000000000000`
respectively.

Then exercise each audience against a real endpoint, because minting a token is
weaker evidence than using one:

- Graph: resolve the site, then `GET /sites/{siteId}/drive/root/children`.
- SharePoint REST: `GET {SITE_URL}/_api/web/title`.

Assertion claims: `aud` = the token endpoint, `iss` = `sub` = client ID, plus
`jti`, `nbf`, `exp`; header carries `x5t` = base64url of the certificate's SHA-1
DER digest.

Two gotchas that cost time:
- `GET /sites/{host}:{path}:/drive/root/children` returns
  `"Url specified is invalid."` — resolve the site ID first, then use
  `GET /sites/{siteId}/drive/root/children`.
- Python < 3.12 rejects backslashes inside f-string expressions, so
  `f"{d[\"id\"]}"` in a `python3 -c` one-liner is a `SyntaxError`. Use plain
  concatenation or `%` formatting in shell-embedded snippets. This bites
  repeatedly; it is not a one-off.

Re-run this script after deleting the granter app, to confirm the per-site grant
outlived it. Keep it around — it is also the first thing to run when a
previously working sync starts failing.

## 9. Create the KB and data source

```sh
aws bedrock-agent create-knowledge-base \
  --name "$KB_NAME" \
  --role-arn "$ROLE_ARN" \
  --knowledge-base-configuration '{"type":"MANAGED"}'
```

Poll to `ACTIVE` (1–2 min), then create the data source. **Creation is
asynchronous for managed connectors**: status goes `CREATING` → `AVAILABLE`, so
poll that too rather than assuming a successful create call means a usable
source.

```json
{
  "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
  "managedKnowledgeBaseConnectorConfiguration": {
    "mediaExtractionConfiguration": {
      "imageExtractionConfiguration": {"imageExtractionStatus": "DISABLED"}
    },
    "connectorParameters": {
      "type": "SHAREPOINT",
      "version": "1",
      "aclEnabled": false,
      "connectionConfiguration": {
        "secretArn": "<secret arn>",
        "tenantId": "<entra tenant id>",
        "authType": "ENTRA_ID_APP_ONLY",
        "certificateS3Path": {
          "s3BucketName": "<bucket>",
          "s3KeyName": "certs/certificate.p12"
        }
      },
      "dataEntityConfiguration": {
        "crawlFiles": true,
        "crawlPages": false,
        "siteUrls": ["https://<tenant>.sharepoint.com/sites/<site>"]
      }
    }
  }
}
```

```sh
aws bedrock-agent create-data-source \
  --knowledge-base-id "$KB_ID" --name sharepoint-source \
  --data-deletion-policy DELETE \
  --data-source-configuration file://ds.json
```

Note the structure carefully — it is easy to get wrong:

- **`connectorParameters` is an opaque *document*.** The CLI and SDK do not
  validate its shape, so field-name typos surface at sync time, not create time.
  The service fills in defaults (`filterConfiguration.maxFileSizeInMegaBytes`,
  `crawlIdentities`) and echoes the whole thing back **as a JSON string** —
  read that echo to confirm what it understood.
- **`mediaExtractionConfiguration` is a sibling of `connectorParameters`, not
  inside it**, and unlike `connectorParameters` it *is* a typed shape, so
  misplacing it is caught. It accepts
  `imageExtractionConfiguration` / `audioExtractionConfiguration` /
  `videoExtractionConfiguration`, each `ENABLED` | `DISABLED`. See §11 for why
  you may want image extraction off.
- **`certificateS3Path` is required for `ENTRA_ID_APP_ONLY`** even when
  `aclEnabled` is `false`.
- **`aclEnabled` cannot be changed after creation.** Getting it wrong means
  recreating the data source.
- **`dataDeletionPolicy: DELETE`** makes deleting the data source remove its
  indexed content, which is what makes the recreate-to-purge procedure in §12
  work. Set it now.

Set **`crawlPages: false`** unless you actually want site pages. With it on,
`SitePages/*.aspx` get indexed and retrieve as web-part JSON and ASP.NET
scaffolding rather than prose — noise that competes with your real documents.
Getting this right at create time avoids the purge problem in §12.

## 10. Sync and verify

```sh
JOB=$(aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" \
  --query 'ingestionJob.ingestionJobId' --output text)
```

Poll `get-ingestion-job` to a terminal state (`COMPLETE` / `FAILED` /
`STOPPED`); ~3 min for a couple of dozen documents.

**Check the statistics block, not just `status: COMPLETE`** — a job with
`numberOfNewDocumentsIndexed: 0` is a failure wearing a success label. You want
a nonzero indexed count and `numberOfDocumentsFailed: 0`. Also read
`failureReasons`; some are benign, notably
`Document cannot be synced since it contains no content` — empty files count as
failed documents and will never succeed.

The statistics are also the only authoritative document count you get. There is
**no enumeration API** for connector-backed KBs:

```
ValidationException: Invalid data source type [SHAREPOINTV3] provided.
Only S3 and Custom data source supported for document level request.
```

That rejects `list-knowledge-base-documents` as well as
`delete-knowledge-base-documents`, so summing
`numberOfNewDocumentsIndexed − numberOfDocumentsDeleted` across jobs is how you
know how much is indexed. Probing with retrieval samples the corpus but never
proves completeness — don't present it as an inventory.

Then a real retrieval:

```sh
aws bedrock-agent-runtime retrieve --knowledge-base-id "$KB_ID" \
  --retrieval-query '{"text":"…"}' \
  --retrieval-configuration '{"managedSearchConfiguration":{"numberOfResults":10}}'
```

`vectorSearchConfiguration` is rejected on a managed KB — the API tells you to
use `managedSearchConfiguration` instead.

Verify with a question a human would actually ask, and read the chunks rather
than just counting them. Two things this surfaces that a smoke test won't:

- **Rank 1 is often not the answer.** Asking "how do I submit assignments?"
  ranked a chunk about academic-integrity policy above the chunk naming the
  actual submission system — the first merely repeats the query's vocabulary.
  Fine when an LLM reads the whole result set; misleading if anything downstream
  trusts the top hit alone. Retrieve ~10–12 passages and let the model judge.
- **Grouping hits by source URL** is the fastest way to confirm a scope change
  took effect. Counting chunks per document tells you what's in the index; a
  single overall count doesn't.

## 11. Retrieval and generation quality

**`retrieve-and-generate` is not supported** on a managed KB:
`ValidationException: This operation is not supported for managed knowledge
bases.` A chatbot over one of these must drive both halves itself — `Retrieve`
for passages, then `Converse` with the passages injected into the prompt. Two
things that matter when you build that loop:

- Append only the *question* to conversation history, not the retrieved
  passages. Otherwise context grows by N chunks per turn and stale passages
  compete with fresh ones.
- Model access is gated separately from the KB. Anthropic models can return
  `ResourceNotFoundException: Model use case details have not been submitted for
  this account` from `Converse` — intermittently, and independently of the
  script calling them. Amazon Nova profiles are not gated. Make the model an
  environment variable so a gating problem is a config change, not a code
  change, and on generation failure still show the retrieved passages rather
  than losing the turn.

**Image extraction is on by default and it writes content into your index.**
With `imageExtractionStatus: ENABLED` (the default when you omit
`mediaExtractionConfiguration` entirely), figures are captioned by a vision
model and those captions become retrievable chunks, wrapped in
`<analysis>` / `<description>` / `<data>` tags. Observed on a technical corpus:
captions containing numeric tables explicitly labelled *"estimated data points
based on visual inspection"* — model inferences from pixels, indistinguishable
at retrieval time from text the author actually wrote.

Decide deliberately:

| Corpus | Recommendation |
|---|---|
| Diagrams/screenshots carry meaning, approximate is fine | Leave `ENABLED` |
| Quantitative, regulatory, or anything cited as fact | Set `DISABLED` |

If you leave it on, have the answering prompt distinguish figure-derived
content from authored text. And note that disabling it later does not remove
captions already indexed — that needs the §12 recreate.

**Extraction loses mathematics.** On PDFs with numbered equations, the formulas
did not survive chunking: cross-references like "see Eq. (51)" came through as
bare numbers with the equation itself gone. A KB over technical PDFs can answer
about structure and prose while being unable to reproduce the equations, which
is a failure mode worth stating up front rather than discovering in an answer.
There is no connector-side fix; it needs a different ingestion path (extract to
Markdown/LaTeX yourself and index that via S3).

## 12. Changing configuration later

`update-data-source` requires the **full** configuration, not a patch. Read the
current config, mutate the one field, send it all back — otherwise you silently
reset the service-filled defaults:

```sh
aws bedrock-agent get-data-source --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" \
  | jq '.dataSource.dataSourceConfiguration' > cfg.json
# edit connectorParameters (it comes back as a JSON *string*; parse, mutate, re-embed as an object)
aws bedrock-agent update-data-source --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" \
  --name sharepoint-source --data-source-configuration file://cfg.json
```

`--name` is required on update even when unchanged. The data source sits in
`UPDATING` for well under a minute.

**Narrowing scope does not retroactively purge.** Turning `crawlPages` from true
to false means the connector no longer *sees* those pages, so it cannot diff
them as deleted. Observed directly: the post-change sync reported
`numberOfDocumentsScanned: 1, numberOfDocumentsDeleted: 0`, and the two
`SitePages/*.aspx` documents were still returned by `retrieve` afterwards. Since
document-level deletion is unavailable (§10), there is no surgical fix.

The same reasoning applies to anything else that only shrinks what gets
scanned — a narrowed `siteUrls`, a tightened `filterConfiguration`, or
`imageExtractionStatus: DISABLED`.

So to purge, **delete and recreate the data source** (with
`dataDeletionPolicy: DELETE`, deleting it removes its indexed content), then
re-sync. Confirmed end to end: after recreation with `crawlPages: false` and a
fresh sync, the same query that previously matched both pages returned only
document-library chunks. Budget ~4 minutes in `DELETING`, and poll until
`get-data-source` fails with a not-found error rather than expecting a terminal
status. **The data source ID changes** — update wherever you recorded it
(README, scripts, bot config).

Adding a site: flip `create_granter` back to `true`, apply, run the grant script
for the new site, flip it back, then add the URL to `siteUrls` and re-sync.
Widening scope this way *does* work without a recreate — only narrowing is the
problem.

## 13. Operational notes

**Certificate rotation** is a hard deadline, and the order avoids downtime:

1. Generate a new cert / `.p12`.
2. **Append** the new `.cer` to the Entra app (both credentials valid at once).
3. Upload the new `.p12` to S3, same key.
4. Update `certificatePassword` in the secret.
5. Re-sync to confirm, *then* remove the old certificate from Entra.

Under Terraform, steps 2–4 are one `apply` (it replaces both the Entra
certificate and the S3 object) followed by a re-sync. Either way, put the expiry
date somewhere you will actually see it.

Other things worth knowing:

- **Mask credentials by value, not by key-name heuristics.** A filter that only
  matches keys containing `secret`/`password`/`pass` will happily print
  `privateKey` in full — and for this auth type, that key *is* the credential.
  If one leaks to a terminal or transcript, it is compromised; rotate it.
- Deleting a stale secret from a failed attempt: `delete-secret
  --force-delete-without-recovery`, or Terraform's `recovery_window_in_days = 0`
  for throwaway dev secrets. Otherwise the name stays reserved for 7–30 days and
  recreating it fails.
- **AWS SSO sessions expire mid-build** and the failure reads as a credential
  problem (`Token has expired and refresh failed`). Re-run `aws sso login
  --profile <profile>` before concluding anything is misconfigured.
- The KB and data source living outside Terraform means `terraform destroy`
  leaves them running. Delete them explicitly, KB last.
- Record in the project README: KB ID, data source ID, site URL, connector app
  ID, region/account, certificate expiry, and which `aws` binary to use. The
  Terraform/CLI split is invisible otherwise, and the data source ID changes
  every time you purge.
