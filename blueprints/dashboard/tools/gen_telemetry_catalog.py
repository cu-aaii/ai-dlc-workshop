#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Generate the declared-counter catalog from every blueprint's manifest (C-14).

**Why a generated, committed file rather than a runtime lookup.** FR-9.4 puts each blueprint's
telemetry declaration in its `blueprint.yaml`; FR-9.5.2 makes those declarations a closed allowlist
for the reader. But `blueprint.yaml` lives in git and the reader is a Lambda: it cannot read the
repository, and this repo has no runtime config distribution. So the declarations are collected here,
committed, and baked into the container image.

Drift is prevented by `tools/check`, which runs this with `--check` and fails if the committed file
disagrees with the manifests. That is the same bargain `uv.lock` makes: generated, committed, verified.

Two alternatives were rejected. Generating inside the container build would have to happen in
`ArmContainerBuildProject`, which is **shared by every blueprint** -- a dashboard-specific step there
would pollute a common project. Publishing each declaration to SSM at deploy time is fresher, but
needs a resource added to *every other blueprint's template*, which is cross-track work this pass
deliberately declined.

A **malformed** `telemetry:` block fails here (CAT-02) rather than degrading to `emits: false` --
otherwise a blueprint that intended to emit would silently vanish from the catalog.

Run through `tools/check`; `uv run` fetches pyyaml from the inline metadata above.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "v1-telemetry-catalog"
REPO_ROOT = Path(__file__).resolve().parents[3]
BLUEPRINTS = REPO_ROOT / "blueprints"
OUTPUT = REPO_ROOT / "blueprints/dashboard/src/dashboard/telemetry_catalog.json"


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def collect() -> dict[str, Any]:
    import yaml

    blueprints: dict[str, Any] = {}
    for manifest_path in sorted(BLUEPRINTS.glob("*/blueprint.yaml")):
        name = manifest_path.parent.name
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            _fail(f"{manifest_path} is not valid YAML: {exc}")
        telemetry = manifest.get("telemetry")
        if telemetry is None:
            # CAT-01: absence is a declaration. Recorded explicitly so the catalog lists every
            # blueprint rather than only the emitting ones -- a reader can then distinguish
            # "declared false" from "this blueprint does not exist".
            blueprints[name] = {"emits": False}
            continue
        if not isinstance(telemetry, dict):
            _fail(f"{manifest_path}: telemetry must be a mapping")
        if not telemetry.get("emits", False):
            blueprints[name] = {"emits": False}
            continue
        namespace = telemetry.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            _fail(f"{manifest_path}: an emitting blueprint must declare a namespace")
        counters = telemetry.get("counters")
        if not isinstance(counters, list) or not counters:
            _fail(f"{manifest_path}: an emitting blueprint must declare counters")
        parsed: list[dict[str, str]] = []
        for counter in counters:
            if not isinstance(counter, dict):
                _fail(f"{manifest_path}: each counter must be a mapping")
            for required in ("name", "unit", "description"):
                value = counter.get(required)
                if not isinstance(value, str) or not value:
                    _fail(
                        f"{manifest_path}: counter field '{required}' must be a non-empty string"
                    )
            parsed.append(
                {
                    "name": counter["name"],
                    "unit": counter["unit"],
                    "description": counter["description"],
                }
            )
        blueprints[name] = {
            "emits": True,
            "namespace": namespace,
            "counters": sorted(parsed, key=lambda c: c["name"]),
        }
    return {"schema_version": SCHEMA_VERSION, "blueprints": blueprints}


def render(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the telemetry counter catalog.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed catalog is out of date instead of rewriting it",
    )
    args = parser.parse_args()
    rendered = render(collect())
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(
                "error: telemetry_catalog.json is out of date.\n"
                "       regenerate: uv run blueprints/dashboard/tools/gen_telemetry_catalog.py",
                file=sys.stderr,
            )
            return 1
        print("telemetry catalog: up to date")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
