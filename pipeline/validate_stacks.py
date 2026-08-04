#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Check that pipeline/stacks.yml, the templates on disk, and pipeline.yml all agree.

Run this through `tools/check` rather than directly -- the inline script metadata above lets
`uv run` fetch pyyaml on demand, so there is nothing to install and no venv to activate.

Run with no arguments to validate; run with --list to print the registered template paths
(what PR checks feeds to cfn-lint).

Two invariants, each checked in both directions:

registry <-> filesystem
    A template nobody registered is a template nobody lints, and a registry entry with no
    file is a stack the pipeline fails to deploy at merge time rather than at review time.

registry <-> pipeline.yml
    A `deployed_by: pipeline` entry with no CloudFormation action deploys nothing, and does
    so *silently* -- PR checks pass, every pipeline stage reports Succeeded, and no stack
    appears. Adding the action is step 3 of "Adding a blueprint stack" in pipeline/README.md;
    this is what makes forgetting it a review-time error instead of a mystery.

terraform modules <-> pipeline.yml
    The same failure, one directory over. Terraform modules are not CloudFormation and so are
    not in the registry at all, which would leave a `blueprints/<name>/infra/azure/` directory
    with no Terraform action applying nothing while every stage still reported Succeeded.
    Checked in both directions against the TF_WORKING_DIR values in the pipeline's Terraform
    actions.

blueprints <-> blueprint manifests
    The third shape of the same failure, in the layer above the pipeline. The Cornell Builder
    MCP builds its catalog by globbing `blueprints/*/blueprint.yaml`, and a blueprint directory
    with no manifest is skipped with no error -- so the blueprint deploys perfectly and no
    builder can find it. `knowledgebase` was invisible this way, and an intent search for a
    knowledge base returned `tiny-chatbot` as its top hit: a confident wrong answer rather than
    an empty one.

    Checked in both directions against MANIFEST_EXEMPT -- a directory with no manifest and no
    exemption, and an exemption naming a directory that is gone -- plus the four ways a manifest
    can be present and still wrong: naming a template nobody registered, naming a template that
    does not exist, disagreeing with its own directory name, or drifting out of version lockstep
    with the BlueprintVersion default of the template it names.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / 'pipeline' / 'stacks.yml'
PIPELINE_PATH = REPO_ROOT / 'pipeline' / 'pipeline.yml'
BLUEPRINTS_DIR = REPO_ROOT / 'blueprints'

# CloudFormation deploy actions name their template as
# `TemplatePath: 'GitRepositoryArtifact::<repo-relative-path>'`. Matched by text scan for the
# same reason discover_templates() uses one: pipeline.yml is full of CloudFormation short tags
# (!Sub, !GetAtt) that yaml.safe_load cannot parse without a custom loader.
TEMPLATE_PATH_PATTERN = re.compile(r'GitRepositoryArtifact::([^\s\'"]+)')

# Terraform stage actions name their module as a CodeBuild environment-variable override,
# {"name":"TF_WORKING_DIR","value":"<repo-relative-path>",...}. Matched by text scan for the
# same reason as above: pipeline.yml cannot be yaml.safe_load'ed.
TF_WORKING_DIR_PATTERN = re.compile(r'"name"\s*:\s*"TF_WORKING_DIR"\s*,\s*"value"\s*:\s*"([^"]+)"')

# Terraform modules live alongside a blueprint's CloudFormation, per blueprints/README.md.
TF_MODULE_GLOB = 'blueprints/*/infra/azure'

# One blueprint per directory; the Cornell Builder MCP's catalog loader globs exactly this
# (packages/builder-mcp/src/builder_mcp/catalog.py, _load_local).
#
# The manifest-names-an-unregistered-template case below came from ef436 (adfd31b, merged in
# #15) and is kept verbatim in spirit. What it could not catch is the direction added here: it
# iterated the manifests that exist, so a blueprint directory with no manifest at all was
# invisible to it -- which is the failure that hid knowledgebase from blueprint_search. The two
# checks were separate functions with the same name after the merge; they are one function now.
BLUEPRINT_DIR_GLOB = 'blueprints/*'
MANIFEST_NAME = 'blueprint.yaml'

# Blueprint directories that deliberately have no manifest, and why. A blueprint belongs here
# only when it should not appear in the builder-facing catalog at all -- not merely because
# writing the manifest is outstanding work.
#
# The manifest's `template` field is a repo-relative CloudFormation path, and deployment_create
# renders a CloudFormation deploy action from it, so a Terraform-only blueprint cannot be
# expressed as a catalog entry today. Supporting one is a builder-mcp change (a manifest kind
# that renders a Terraform action instead), not something to fake with an empty template path.
MANIFEST_EXEMPT = {
    'entra-probe': (
        'Terraform-only and self-declared "a probe, not a building block. Nothing should '
        'depend on it." It creates one Entra application that grants nothing, and it has no '
        'CloudFormation template for a manifest to point at. Listing it in the catalog would '
        'offer builders a deployment that deployment_create cannot render an action for.'
    ),
    'course-chatbot': (
        'Scaffold that deploys nothing -- Lambda handler and READMEs only, with no template, '
        'no image target, no registry entry and no pipeline action. Withheld from the catalog '
        'on purpose so the Builder cannot offer a blueprint that cannot deploy; see '
        'blueprints/README.md. Delete this entry in the PR that adds its template.'
    ),
}

# The template's BlueprintVersion default, which the manifest's metadata.version must match
# (packages/builder-mcp/SPEC.md C1). Text scan, like everything else here, because a CloudFormation
# template full of !Sub and !GetAtt is not yaml.safe_load-able.
BLUEPRINT_VERSION_PATTERN = re.compile(
    r'^  BlueprintVersion:\s*$.*?^\s*Default:\s*[\'"]?([0-9]+\.[0-9]+\.[0-9]+)[\'"]?\s*$',
    re.MULTILINE | re.DOTALL,
)

# A YAML file is a CloudFormation template if it declares a template format version. Cheap
# text scan rather than a YAML parse, because CloudFormation short tags (!Sub, !GetAtt)
# are not loadable by yaml.safe_load without a custom loader.
TEMPLATE_MARKER = 'AWSTemplateFormatVersion'

# Directories with no deployable templates in them.
#
# outputs-preview/ is generated by packages/builder-mcp/devtools/preview_deploy.py and holds
# verbatim *copies* of blueprint templates, so the marker scan below would discover them as
# unregistered templates and fail the build. It is gitignored, but this scan walks the
# filesystem rather than git, so ignoring it there is not enough -- without this entry,
# running the preview tool breaks tools/check on that machine until the folder is deleted.
SKIP_DIRS = {
    '.git', '.github', 'node_modules', '.venv', '__pycache__', 'outputs-preview',
}

VALID_DEPLOYED_BY = {'pipeline', 'manual'}


def discover_templates() -> set[str]:
    """Every CloudFormation template in the repo, as repo-relative posix paths."""
    found = set()
    for path in REPO_ROOT.rglob('*'):
        if path.suffix not in {'.yml', '.yaml'} or not path.is_file():
            continue
        if SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts):
            continue
        try:
            if TEMPLATE_MARKER in path.read_text(encoding='utf-8'):
                found.add(path.relative_to(REPO_ROOT).as_posix())
        except UnicodeDecodeError:
            continue
    return found


def pipeline_deployed_templates() -> set[str]:
    """Every template path a CloudFormation action in pipeline/pipeline.yml deploys."""
    if not PIPELINE_PATH.is_file():
        return set()
    text = PIPELINE_PATH.read_text(encoding='utf-8')
    return set(TEMPLATE_PATH_PATTERN.findall(text))


def discover_tf_modules() -> set[str]:
    """Every Terraform module in the repo, as repo-relative posix paths.

    A directory only counts once it holds at least one .tf file -- an empty directory is
    something in progress, not a module the pipeline should be applying.
    """
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in REPO_ROOT.glob(TF_MODULE_GLOB)
        if path.is_dir() and any(path.glob('*.tf'))
    }


def pipeline_applied_tf_modules() -> set[str]:
    """Every Terraform module a Terraform action in pipeline/pipeline.yml applies."""
    if not PIPELINE_PATH.is_file():
        return set()
    text = PIPELINE_PATH.read_text(encoding='utf-8')
    return set(TF_WORKING_DIR_PATTERN.findall(text))


def check_tf_modules() -> list[str]:
    """Cross-check Terraform modules on disk against the pipeline's Terraform actions.

    Same silent failure as check_pipeline_actions, for the half of the deploy path that has no
    registry: a module nobody applies, or an action pointing at a directory that isn't there.
    """
    errors: list[str] = []
    on_disk = discover_tf_modules()
    applied = pipeline_applied_tf_modules()

    for orphan in sorted(on_disk - applied):
        errors.append(
            f'Terraform module {orphan} has no TF_WORKING_DIR action in pipeline/pipeline.yml '
            '-- it would apply nothing, silently. Add a Terraform stage action (see "Adding a '
            'Terraform module" in pipeline/README.md), or delete the module.'
        )

    for missing in sorted(applied - on_disk):
        path = REPO_ROOT / missing
        why = 'directory does not exist' if not path.is_dir() else 'directory contains no .tf files'
        errors.append(
            f'pipeline/pipeline.yml applies Terraform in {missing}, but that {why} '
            '-- the Terraform stage would fail after merge.'
        )

    return errors


def discover_blueprint_dirs() -> set[str]:
    """Every blueprint directory, by name. `blueprints/README.md` is a file, not a blueprint."""
    return {
        path.name
        for path in REPO_ROOT.glob(BLUEPRINT_DIR_GLOB)
        if path.is_dir() and path.name not in SKIP_DIRS
    }


def template_blueprint_version(template: str) -> str | None:
    """The BlueprintVersion default declared by a template, or None if it declares none."""
    path = REPO_ROOT / template
    if not path.is_file():
        return None
    match = BLUEPRINT_VERSION_PATTERN.search(path.read_text(encoding='utf-8'))
    return match.group(1) if match else None


def check_blueprint_manifests(declared: dict[str, str]) -> list[str]:
    """Cross-check blueprint directories against their builder-catalog manifests.

    The silent failure here is one layer above the pipeline: no manifest means the blueprint is
    absent from blueprint_search, which fails by returning a *wrong* top hit rather than an
    empty result. Checked in both directions, plus the ways a manifest can be present but lie.
    """
    errors: list[str] = []
    on_disk = discover_blueprint_dirs()

    for stale in sorted(set(MANIFEST_EXEMPT) - on_disk):
        errors.append(
            f'MANIFEST_EXEMPT in {Path(__file__).name} lists {stale!r}, but '
            f'blueprints/{stale}/ does not exist -- drop the exemption.'
        )

    for name in sorted(on_disk):
        manifest_path = REPO_ROOT / 'blueprints' / name / MANIFEST_NAME
        exempt_reason = MANIFEST_EXEMPT.get(name)

        if not manifest_path.is_file():
            if exempt_reason is None:
                errors.append(
                    f'blueprint {name} has no blueprints/{name}/{MANIFEST_NAME} -- it would be '
                    'invisible to the Cornell Builder MCP\'s blueprint_search, silently, while '
                    'deploying perfectly. Add the manifest (packages/builder-mcp/SPEC.md, C1), or add '
                    f'{name!r} to MANIFEST_EXEMPT with the reason it should not be in the '
                    'catalog.'
                )
            continue

        if exempt_reason is not None:
            errors.append(
                f'blueprint {name} is in MANIFEST_EXEMPT but has a {MANIFEST_NAME} -- the '
                'exemption says it should not be in the builder catalog while the manifest '
                'puts it there. Remove one of the two.'
            )

        if TEMPLATE_MARKER in manifest_path.read_text(encoding='utf-8'):
            errors.append(
                f'blueprints/{name}/{MANIFEST_NAME} contains the string {TEMPLATE_MARKER}, so '
                'discover_templates() reads it as a CloudFormation template and cfn-lint will '
                'be handed a manifest. Do not name that key in a manifest, even in a comment '
                '(packages/builder-mcp/SPEC.md, C1).'
            )
            continue

        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding='utf-8')) or {}
        except yaml.YAMLError as error:
            errors.append(f'blueprints/{name}/{MANIFEST_NAME} is not valid YAML: {error}')
            continue
        if not isinstance(manifest, dict):
            errors.append(f'blueprints/{name}/{MANIFEST_NAME}: expected a mapping at the top level')
            continue

        metadata = manifest.get('metadata') or {}
        declared_name = metadata.get('name') if isinstance(metadata, dict) else None
        if declared_name != name:
            errors.append(
                f'blueprints/{name}/{MANIFEST_NAME}: metadata.name is {declared_name!r} but the '
                f'directory is {name!r} -- the catalog keys deployments off metadata.name, so '
                'the two must agree.'
            )

        template = manifest.get('template')
        if not template:
            errors.append(
                f'blueprints/{name}/{MANIFEST_NAME}: missing "template" -- deployment_create '
                'renders its CloudFormation action from this path and would emit a broken one.'
            )
            continue
        if not (REPO_ROOT / template).is_file():
            errors.append(
                f'blueprints/{name}/{MANIFEST_NAME}: template does not exist: {template}'
            )
            continue
        if template not in declared:
            errors.append(
                f'blueprints/{name}/{MANIFEST_NAME}: names {template}, which is not registered '
                'in pipeline/stacks.yml -- the catalog would offer a blueprint whose template '
                'PR checks do not lint.'
            )

        # SPEC C1: manifest metadata.version stays in lockstep with the template's
        # BlueprintVersion default. Out of lockstep, the version a builder sees in the catalog
        # is not the version the cornell:blueprint-version tag records on the deployed stack.
        manifest_version = str(metadata.get('version')) if isinstance(metadata, dict) else None
        template_version = template_blueprint_version(template)
        if template_version is not None and manifest_version != template_version:
            errors.append(
                f'blueprints/{name}/{MANIFEST_NAME}: metadata.version is {manifest_version!r} '
                f'but {template} declares BlueprintVersion default {template_version!r} -- bump '
                'both in the same PR, or the catalog and the cornell:blueprint-version tag '
                'disagree about what is deployed.'
            )

    return errors


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        sys.exit(f'missing registry: {REGISTRY_PATH.relative_to(REPO_ROOT)}')
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding='utf-8')) or {}
    entries = registry.get('templates')
    if not isinstance(entries, list) or not entries:
        sys.exit('pipeline/stacks.yml must define a non-empty "templates" list')
    return entries


def validate(entries: list[dict]) -> list[str]:
    errors: list[str] = []
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    # template path -> deployed_by, for the pipeline.yml cross-check below.
    declared: dict[str, str] = {}

    for index, entry in enumerate(entries):
        where = f'templates[{index}]'
        if not isinstance(entry, dict):
            errors.append(f'{where}: expected a mapping, got {type(entry).__name__}')
            continue

        name = entry.get('name')
        template = entry.get('template')
        deployed_by = entry.get('deployed_by')

        if not name:
            errors.append(f'{where}: missing "name"')
        elif name in seen_names:
            errors.append(f'{where}: duplicate name {name!r}')
        else:
            seen_names.add(name)

        if deployed_by not in VALID_DEPLOYED_BY:
            errors.append(
                f'{where} ({name}): deployed_by must be one of '
                f'{sorted(VALID_DEPLOYED_BY)}, got {deployed_by!r}'
            )

        if not template:
            errors.append(f'{where} ({name}): missing "template"')
            continue
        if template in seen_paths:
            errors.append(f'{where} ({name}): duplicate template path {template!r}')
        seen_paths.add(template)
        declared[template] = deployed_by

        path = REPO_ROOT / template
        if not path.is_file():
            errors.append(f'{where} ({name}): registered template does not exist: {template}')
        elif TEMPLATE_MARKER not in path.read_text(encoding='utf-8'):
            errors.append(
                f'{where} ({name}): {template} has no {TEMPLATE_MARKER} '
                'and so is not a CloudFormation template'
            )

    for orphan in sorted(discover_templates() - seen_paths):
        errors.append(
            f'unregistered CloudFormation template: {orphan} '
            '-- add it to pipeline/stacks.yml so PR checks lint it'
        )

    errors.extend(check_pipeline_actions(declared))
    errors.extend(check_tf_modules())
    errors.extend(check_blueprint_manifests(declared))

    return errors


def check_pipeline_actions(declared: dict[str, str]) -> list[str]:
    """Cross-check the registry against the CloudFormation actions in pipeline/pipeline.yml.

    Catches the silent failure: a blueprint registered as `deployed_by: pipeline` with no
    action deploys nothing while every check and every pipeline stage still reports success.
    """
    errors: list[str] = []
    deployed = pipeline_deployed_templates()

    for template, deployed_by in sorted(declared.items()):
        if deployed_by == 'pipeline' and template not in deployed:
            errors.append(
                f'{template} is registered deployed_by: pipeline but no CloudFormation '
                'action in pipeline/pipeline.yml deploys it -- it would deploy nothing, '
                'silently. Add a BlueprintDeploy action (step 3 of "Adding a blueprint '
                'stack" in pipeline/README.md), or register it as deployed_by: manual.'
            )
        if deployed_by == 'manual' and template in deployed:
            errors.append(
                f'{template} is registered deployed_by: manual but pipeline/pipeline.yml '
                'deploys it -- change deployed_by to pipeline, or remove the action.'
            )

    for template in sorted(deployed - set(declared)):
        errors.append(
            f'pipeline/pipeline.yml deploys {template}, which is not in pipeline/stacks.yml '
            '-- register it so PR checks lint it before it reaches a deploy.'
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--list',
        action='store_true',
        help='print registered CloudFormation template paths, one per line, instead of validating',
    )
    parser.add_argument(
        '--list-tf',
        action='store_true',
        help='print Terraform module directories, one per line, instead of validating',
    )
    args = parser.parse_args()

    # Kept out of the registry-loading path: tools/check calls this to find directories to
    # fmt and validate, and a broken stacks.yml should not stop Terraform from being linted.
    if args.list_tf:
        for module in sorted(discover_tf_modules()):
            print(module)
        return 0

    entries = load_registry()

    if args.list:
        # LF regardless of platform. tools/check word-splits this output into cfn-lint's
        # arguments, and on Windows print() would emit CRLF -- leaving a trailing carriage
        # return on every path but the last. cfn-lint then reports 'E0003 <template> could not
        # be processed by glob.glob', which reads like a broken template rather than a broken
        # path, and tools/check cannot pass on a Windows checkout at all.
        sys.stdout.reconfigure(newline='\n')
        for entry in entries:
            if isinstance(entry, dict) and entry.get('template'):
                print(entry['template'])
        return 0

    errors = validate(entries)
    if errors:
        print(f'stack and module registry: {len(errors)} problem(s)', file=sys.stderr)
        for error in errors:
            print(f'  - {error}', file=sys.stderr)
        return 1

    print(f'pipeline/stacks.yml: {len(entries)} template(s) registered and present')
    deployed = pipeline_deployed_templates()
    for entry in entries:
        # Showing which templates an action actually deploys makes step 3 of "Adding a
        # blueprint stack" visible rather than something you find out by its absence.
        wired = ' <- deployed by a pipeline action' if entry['template'] in deployed else ''
        print(f"  {entry['deployed_by']:<9} {entry['template']}{wired}")

    modules = discover_tf_modules()
    applied = pipeline_applied_tf_modules()
    print(f'terraform: {len(modules)} module(s) present')
    for module in sorted(modules):
        wired = ' <- applied by a pipeline action' if module in applied else ''
        print(f'  {"terraform":<9} {module}{wired}')

    # Which blueprints the builder can actually find, printed for the same reason the pipeline
    # wiring is: a missing manifest is otherwise only visible as an absence.
    blueprints = discover_blueprint_dirs()
    print(f'blueprints: {len(blueprints)} directory(ies) present')
    for name in sorted(blueprints):
        if name in MANIFEST_EXEMPT:
            state = 'not in the builder catalog (exempt)'
        else:
            state = 'in the builder catalog'
        print(f'  {"blueprint":<9} blueprints/{name} <- {state}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
