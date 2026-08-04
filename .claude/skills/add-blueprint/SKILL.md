---
name: add-blueprint
description: Add a new blueprint stack (or any new CloudFormation template) to this repo. Use whenever creating a template under blueprints/*/infra/, registering a stack in pipeline/stacks.yml, adding a BlueprintDeploy action, or when a newly added stack deploys nothing. Covers the three-file mirror, the four cornell:* tags, stack naming, and the blueprint.yaml manifest.
---

# Adding a blueprint stack

Adding a stack is **three files edited in one PR**. Steps 2 and 3 are mirrored by hand on
purpose — generating stages from the registry is the framework the workshop spec says not to
build.

Skipping step 3 is the expensive mistake: the PR goes green, all pipeline stages report
`Succeeded`, and **no stack appears**. `validate_stacks.py` now catches it at review time, but
only if you run `tools/check`.

## Step 1 — the template

Location: `blueprints/<name>/infra/<name>.yml`.

Model it on `blueprints/hello-world/infra/hello-world.yml`. Required parameter block:

```yaml
Parameters:

  # Metadata Parameters

  Application:
    Default: 'aidlc'
    AllowedPattern: '[a-z0-9-]{1,10}'
    Description: 'Name used for billing and other tracking/identification purposes'
    Type: 'String'

  Environment:
    Default: 'main'
    AllowedPattern: '[a-z0-9]{1,4}'
    Description: 'Name of the deployment branch'
    Type: 'String'

  # Tagging Convention Parameters

  Owner:
    Default: 'ai-sei'
    AllowedPattern: '.{1,128}'
    Description: 'Who owns this deployment (cornell:owner)'
    Type: 'String'

  BlueprintVersion:
    Default: '0.1.0'
    AllowedPattern: '[0-9]+\.[0-9]+\.[0-9]+'
    Description: 'Version of the <name> blueprint (cornell:blueprint-version)'
    Type: 'String'
```

`Environment` is capped at **four characters, no hyphens**. It is a component of every stack
name and of the `stack/${Application}-${Environment}*` prefix `BuildPipelineRole` scopes to.
Do not widen the pattern in one template — it has to change in `pipeline.yml` and every
blueprint template together.

### The four tags, on every resource

`cornell:owner`, `cornell:blueprint`, `cornell:blueprint-version`, `cornell:deployment-id`.
An untagged resource is invisible to inventory and the cost dashboard.

Owner and deployment id arrive as parameters. **Blueprint name and version belong to the
template** — hardcode the name, bump the `BlueprintVersion` default in the PR that changes
the blueprint.

Normal (list) form:

```yaml
      Tags:
        - Key: 'Application'
          Value: !Ref 'Application'
        - Key: 'Environment'
          Value: !Ref 'Environment'
        - Key: 'Resource'
          Value: 's3-bucket-<name>'
        - Key: 'cornell:owner'
          Value: !Ref 'Owner'
        - Key: 'cornell:blueprint'
          Value: '<name>'
        - Key: 'cornell:blueprint-version'
          Value: !Ref 'BlueprintVersion'
        - Key: 'cornell:deployment-id'
          Value: !Sub '${Application}-${Environment}-<name>'
```

**`AWS::SSM::Parameter` is the exception — it takes `Tags` as a map:**

```yaml
      Tags:
        Application: !Ref 'Application'
        Environment: !Ref 'Environment'
        Resource: 'ssm-parameter-<name>'
        'cornell:owner': !Ref 'Owner'
        'cornell:blueprint': '<name>'
        'cornell:blueprint-version': !Ref 'BlueprintVersion'
        'cornell:deployment-id': !Sub '${Application}-${Environment}-<name>'
```

Every other resource in this repo uses the list form. Getting this backwards is a cfn-lint
failure that reads like a schema problem.

### Don't hardcode a singleton by accident

`hello-world` hardcodes its bucket name and deployment id to `<app>-<env>-hello-world`, so
only one deployment can exist per app/environment — it is marked `singleton: true` for that
reason. A real blueprint should take a `DeploymentName` parameter and interpolate it, so the
same blueprint can be deployed more than once.

## Step 2 — register it in `pipeline/stacks.yml`

Registering is what makes PR checks lint it.

```yaml
  - name: '<name>'
    template: 'blueprints/<name>/infra/<name>.yml'
    deployed_by: 'pipeline'
    description: 'One line on what it deploys and anything unusual about how.'
```

`deployed_by` is `pipeline` or `manual`. Use `manual` only for chicken-and-egg bootstrap, and
say why in the `description`.

## Step 3 — add the deploy action in `pipeline/pipeline.yml`

Add to the `BlueprintDeploy` stage, modelled on `HelloWorldCloudFormation`:

```yaml
            - Name: '<Name>CloudFormation'
              Namespace: '<Name>CloudFormation'
              RunOrder: 1
              InputArtifacts:
                - Name: 'GitRepositoryArtifact'
              ActionTypeId:
                Category: 'Deploy'
                Owner: 'AWS'
                Provider: 'CloudFormation'
                Version: '1'
              Configuration:
                ActionMode: 'CREATE_UPDATE'
                Capabilities: 'CAPABILITY_NAMED_IAM'
                RoleArn: !Sub 'arn:${AWS::Partition}:iam::${AWS::AccountId}:role/cloudformation-deploy-role'
                StackName: !Sub '${Application}-${Environment}-<name>'
                TemplatePath: 'GitRepositoryArtifact::blueprints/<name>/infra/<name>.yml'
                ParameterOverrides: !Sub >-
                  {
                  "Application": "${Application}",
                  "Environment": "${Environment}",
                  "Owner": "${Owner}",
                  "SourceCommitId": "#{GitRepository.CommitId}"
                  }
```

Two things that are load-bearing here:

- **`StackName` must be `<application>-<environment>-<name>`.** `BuildPipelineRole` scopes
  CloudFormation permissions to `arn:...:stack/${Application}-${Environment}*`. A stack named
  outside the convention produces an **opaque authorization failure**, not a naming complaint.
- **Pass every parameter explicitly.** Template defaults exist so a stack can be deployed by
  hand for debugging; they are not the real values. A blueprint should deploy identically by
  hand and by pipeline.

If the blueprint needs a container image, see the `add-container-build` skill — the image
digest is passed in here as `#{<Namespace>.CONTAINER_DIGEST}`.

## Step 4 (blueprints only) — the `blueprint.yaml` manifest

`blueprints/<name>/blueprint.yaml` is the contract the Builder MCP reads. It is **not** a
CloudFormation template — it declares no `AWSTemplateFormatVersion`, which is what keeps
`validate_stacks.py` and cfn-lint away from it. Do not add that key, even in a comment: the
check is a text scan.

Model it on `blueprints/hello-world/blueprint.yaml`. Keep `metadata.version` in lockstep with
the `BlueprintVersion` default in the template.

## Verify

```bash
tools/check
```

The registry section prints `<- deployed by a pipeline action` next to each wired template.
**Confirm your new stack shows that marker** — its absence is exactly the silent step-3 miss.

Never run bare `cfn-lint` or `python pipeline/validate_stacks.py`; they fail on a clean
machine. `tools/check` is what CI runs.

## Authoring note

`validate_stacks.py` rglobs the entire repo for `*.yml`/`*.yaml` containing
`AWSTemplateFormatVersion`, and its `SKIP_DIRS` is only
`.git`, `.github`, `node_modules`, `.venv`, `__pycache__`. So a scratch or example template
saved anywhere else — including `.claude/` or `docs/` — fails `tools/check` as an
unregistered template. Keep examples inside markdown fences.
