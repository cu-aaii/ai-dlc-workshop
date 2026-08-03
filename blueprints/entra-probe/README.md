# entra-probe

Proves the Terraform-from-CodeBuild path reaches the Entra tenant, the way `hello-world` proves
the CloudFormation path reaches AWS. It creates exactly one thing: an Entra application
registration named `aidlc-main-entra-probe`.

It is a probe, not a building block. Nothing should depend on it.

```
entra-probe/
└── infra/azure/          Terraform. No infra/ -- this blueprint creates no AWS resources.
    ├── versions.tf       provider + S3 backend (partial config)
    ├── main.tf           one azuread_application
    └── .terraform.lock.hcl
```

## What it deploys

An `azuread_application` that **grants nothing**: no `required_resource_access`, no client
secret or certificate, and no service principal. Nothing can authenticate as it. That is
deliberate — the point is to prove the chain works, not to create a usable identity.

The chain it proves, in order: the credential resolves out of Secrets Manager → the `azuread`
provider authenticates to the tenant → state reads and writes to S3 with a native lock → apply
creates a real directory object.

## Tags do not follow the usual shape here, and cannot

Every AWS resource in this repo carries the four `cornell:*` values as key/value tags. Entra
applications have no such field. The Graph `application` resource type takes `tags` as a **flat
list of strings**, so the values are encoded as `key=value` entries instead:

```
cornell:owner=ai-sei
cornell:blueprint=entra-probe
cornell:blueprint-version=0.1.0
cornell:deployment-id=aidlc-main-entra-probe
```

This keeps them greppable — `GET /applications?$filter=tags/any(t:t eq 'cornell:blueprint=entra-probe')`
— which is what the inventory and cost work needs. But anything that parses AWS-shaped tags
will not read these, and there is no cost data behind an Entra object anyway. Expect the same
encoding on every future Entra resource; it is a property of the API, not a shortcut.

## Deploy

Through the pipeline, on merge to `main` — the `Terraform` stage's `EntraProbeTerraform` action.

By hand, for debugging, with the same backend the pipeline uses:

```sh
cd blueprints/entra-probe/infra/azure

export ARM_TENANT_ID=...        # from the aidlc/main/azure/terraform-credentials secret
export ARM_CLIENT_ID=...
export ARM_CLIENT_SECRET=...

terraform init \
  -backend-config="bucket=aidlc-main-tfstate-<account>" \
  -backend-config="key=aidlc/main/entra-probe.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="use_lockfile=true"

terraform plan
```

Same module, same state, whether it runs here or in CodeBuild — the variables have defaults so
a manual run needs none, and the pipeline passes them explicitly regardless.

## Teardown

```sh
terraform destroy     # after the init above
```

Then remove the `EntraProbeTerraform` action from `pipeline/pipeline.yml` and this directory, in
one PR — `pipeline/validate_stacks.py` fails if the action and the directory disagree in either
direction. The state object stays in the bucket until deleted by hand.
