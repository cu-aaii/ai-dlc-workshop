"""Blueprint catalog: load blueprint.yaml manifests and match intent against them.

Whole catalog goes into model context (proposal D2) -- search here is a cheap ranking so
the model sees the best candidates first, not a filter that hides anything. Breaks
somewhere past 75-100 blueprints; revisit then, don't pre-build vector search.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from .config import Settings

logger = logging.getLogger(__name__)


class CatalogError(Exception):
    """Catalog could not be loaded. The message is a caller-safe narrative: tools
    surface it verbatim as {"error": ...} instead of an empty, silent catalog."""


@dataclass
class Blueprint:
    name: str
    version: str
    summary: str
    maturity: str
    maintainer: str
    matches: list[str]
    inputs: dict[str, dict[str, Any]]
    template: str                      # repo-relative path of the CFN template
    pipeline_parameters: dict[str, str] = field(default_factory=dict)
    singleton: bool = False
    cost: dict[str, Any] = field(default_factory=dict)
    data_classification: list[str] = field(default_factory=list)
    state: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_manifest(cls, raw: dict[str, Any]) -> "Blueprint":
        meta = raw.get("metadata", {})
        return cls(
            name=meta.get("name", "unnamed"),
            version=str(meta.get("version", "0.0.0")),
            summary=str(raw.get("summary", "")).strip(),
            maturity=meta.get("maturity", "experimental"),
            maintainer=meta.get("maintainer", "unknown"),
            matches=list(raw.get("matches", [])),
            inputs=dict(raw.get("inputs", {})),
            template=raw.get("template", ""),
            pipeline_parameters=dict(raw.get("pipeline_parameters", {})),
            singleton=bool(raw.get("singleton", False)),
            cost=dict(raw.get("cost", {})),
            data_classification=list(raw.get("data_classification", [])),
            state=list(raw.get("state", [])),
        )

    def summary_dict(self) -> dict[str, Any]:
        """What blueprint_search returns for one blueprint -- the whole contract."""
        return {
            "name": self.name,
            "version": self.version,
            "maturity": self.maturity,
            "summary": self.summary,
            "matches": self.matches,
            "inputs": self.inputs,
            "singleton": self.singleton,
            "cost": self.cost,
            "data_classification": self.data_classification,
        }


def load_catalog(settings: Settings) -> list[Blueprint]:
    """Local checkout when available, GitHub contents API otherwise (AgentCore)."""
    if settings.repo_root is not None:
        return _load_local(settings.repo_root)
    return _load_remote(settings)


def _load_local(repo_root: Path) -> list[Blueprint]:
    blueprints_dir = repo_root / "blueprints"
    if not blueprints_dir.is_dir():
        raise CatalogError(
            f"blueprint catalog unavailable: no 'blueprints' directory under "
            f"{repo_root} — check BUILDER_MCP_REPO_ROOT points at a workshop checkout"
        )
    blueprints = []
    for manifest in sorted(blueprints_dir.glob("*/blueprint.yaml")):
        blueprints.append(Blueprint.from_manifest(yaml.safe_load(manifest.read_text(encoding="utf-8"))))
    logger.debug("loaded %d blueprints from %s", len(blueprints), blueprints_dir)
    return blueprints

def _load_remote(settings: Settings) -> list[Blueprint]:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    try:
        with httpx.Client(base_url="https://api.github.com", headers=headers, timeout=15) as client:
            listing = client.get(f"/repos/{settings.workshop_repo_full}/contents/blueprints")
            if listing.status_code != 200:
                raise CatalogError(
                    f"blueprint catalog unavailable: GitHub returned HTTP "
                    f"{listing.status_code} listing blueprints/ in "
                    f"{settings.workshop_repo_full}"
                    + (
                        " (likely the anonymous rate limit; configure a token)"
                        if listing.status_code == 403
                        else ""
                    )
                )
            blueprints = []
            for entry in listing.json():
                if entry.get("type") != "dir":
                    continue
                raw = client.get(
                    f"/repos/{settings.workshop_repo_full}/contents/blueprints/{entry['name']}/blueprint.yaml",
                    headers={"Accept": "application/vnd.github.raw+json"},
                )
                if raw.status_code == 200:
                    blueprints.append(Blueprint.from_manifest(yaml.safe_load(raw.text)))
            logger.debug("loaded %d blueprints from GitHub", len(blueprints))
            return blueprints
    except httpx.HTTPError as error:  # network/timeout — never a silent empty catalog
        raise CatalogError(
            "blueprint catalog unavailable: could not reach GitHub "
            f"({error.__class__.__name__})"
        ) from error


def search(catalog: list[Blueprint], query: str) -> list[tuple[float, Blueprint]]:
    """Rank blueprints against a plain-language query. Returns every blueprint, best first."""
    query_lower = query.lower()
    query_tokens = set(query_lower.split())
    ranked = []
    for blueprint in catalog:
        score = 0.0
        for phrase in blueprint.matches:
            phrase_lower = phrase.lower()
            if phrase_lower in query_lower or query_lower in phrase_lower:
                score += 10.0
            score += 2.0 * len(query_tokens & set(phrase_lower.split()))
        haystack = f"{blueprint.name} {blueprint.summary}".lower()
        score += 1.0 * len(query_tokens & set(haystack.split()))
        ranked.append((score, blueprint))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked


def validate_inputs(blueprint: Blueprint, provided: dict[str, Any]) -> list[str]:
    """Manifest-level input validation. UX only -- governance stays at the gate (Q7-A)."""
    problems = []
    for input_name, spec in blueprint.inputs.items():
        if spec.get("required") and input_name not in provided:
            problems.append(f"missing required input {input_name!r}: {spec.get('description', '')}")
        if input_name in provided and spec.get("type") == "enum":
            allowed = spec.get("values", [])
            if provided[input_name] not in allowed:
                problems.append(f"input {input_name!r} must be one of {allowed}, got {provided[input_name]!r}")
    for provided_name in provided:
        if provided_name not in blueprint.inputs:
            problems.append(f"unknown input {provided_name!r}; this blueprint takes {sorted(blueprint.inputs)}")
    return problems
