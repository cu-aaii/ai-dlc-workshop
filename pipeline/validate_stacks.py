#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Check that pipeline/stacks.yml and the CloudFormation templates on disk agree.

Run this through `tools/check` rather than directly -- the inline script metadata above lets
`uv run` fetch pyyaml on demand, so there is nothing to install and no venv to activate.

Run with no arguments to validate; run with --list to print the registered template paths
(what PR checks feeds to cfn-lint).

The point of the two-way check is that a template nobody registered is a template nobody
lints, and a registry entry with no file is a stack the pipeline will fail to deploy at
merge time rather than at review time.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / 'pipeline' / 'stacks.yml'

# A YAML file is a CloudFormation template if it declares a template format version. Cheap
# text scan rather than a YAML parse, because CloudFormation short tags (!Sub, !GetAtt)
# are not loadable by yaml.safe_load without a custom loader.
TEMPLATE_MARKER = 'AWSTemplateFormatVersion'

# Directories with no deployable templates in them.
SKIP_DIRS = {'.git', '.github', 'node_modules', '.venv', '__pycache__'}

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

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--list',
        action='store_true',
        help='print registered template paths, one per line, instead of validating',
    )
    args = parser.parse_args()

    entries = load_registry()

    if args.list:
        for entry in entries:
            if isinstance(entry, dict) and entry.get('template'):
                print(entry['template'])
        return 0

    errors = validate(entries)
    if errors:
        print(f'pipeline/stacks.yml: {len(errors)} problem(s)', file=sys.stderr)
        for error in errors:
            print(f'  - {error}', file=sys.stderr)
        return 1

    print(f'pipeline/stacks.yml: {len(entries)} template(s) registered and present')
    for entry in entries:
        print(f"  {entry['deployed_by']:<9} {entry['template']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
