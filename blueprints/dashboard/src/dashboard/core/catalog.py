"""The declared-counter catalog parser (C-14).

Pure: takes bytes, returns a catalog. **Reads no file and no network** (CAT-04) -- the caller supplies
the content, which is what lets this stay inside U-01's boundary while the loading lives in U-02.

**Why this module exists at all.** FR-9.4 requires a blueprint to declare its usage counters in its
`blueprint.yaml`, and FR-9.5.2 requires the reader to treat those declarations as a closed allowlist.
But `blueprint.yaml` lives in **git** and the reader is a **Lambda**: it cannot read the repository,
and this repo has no runtime config distribution. The requirement specified both ends of the contract
and no middle. The middle is a generated catalog, committed and checked for drift by `tools/check`,
and baked into the container image -- this module parses it.

`emits: false`, and a manifest with no `telemetry:` block at all, are **first-class states** (CAT-01),
not errors and not unknowns. A blueprint that reports nothing is still fully inventoried and
cost-attributed; it is simply shown as not instrumented.

Rules CAT-01, CAT-03, CAT-04, CAT-05 live in
`aidlc-docs/construction/fr9-fr10/functional-design/business-rules.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from dashboard.core.errors import CoreError

__all__ = [
    "Catalog",
    "DeclaredCounter",
    "MalformedCatalog",
    "declared_counters",
    "emits",
    "parse_catalog",
]

CATALOG_SCHEMA_VERSION = "v1-telemetry-catalog"
"""Own version string, kept separate from the snapshot's SCHEMA_VERSION.

The catalog is not part of a snapshot -- it is build-time metadata with an independent lifecycle, so
sharing a version with the snapshot would couple two things that change for unrelated reasons.
"""


class MalformedCatalog(CoreError):
    """The catalog could not be parsed. Carries no fragment of the input (NFR-S1)."""


@dataclass(frozen=True, eq=True, slots=True, order=True)
class DeclaredCounter:
    """One counter a blueprint says it emits.

    All three fields are required (CAT-03) because the UI renders **generically** from them: a new
    emitting blueprint must light up with no dashboard code change, and it cannot do that if the
    dashboard has to know what the counter means.
    """

    name: str
    unit: str
    description: str


@dataclass(frozen=True, eq=True)
class Catalog:
    """Declared counters per blueprint, plus every blueprint the generator saw.

    `known` carries **every** blueprint including the non-emitting ones, and that is load-bearing
    rather than tidy: FR-9.7.3 requires the UI to *name* which blueprints are not instrumented, and a
    catalog holding only emitters cannot answer that -- it would render a blank panel instead of
    "these seven blueprints report nothing". `entries` holds only emitters, so `emits()` stays a
    simple membership test.
    """

    entries: Mapping[str, tuple[DeclaredCounter, ...]] = field(default_factory=dict)
    namespaces: Mapping[str, str] = field(default_factory=dict)
    known: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", dict(self.entries))
        object.__setattr__(self, "namespaces", dict(self.namespaces))
        object.__setattr__(self, "known", tuple(sorted(set(self.known) | set(self.entries))))

    def __hash__(self) -> int:
        return hash(
            (
                tuple(sorted(self.entries.items(), key=lambda kv: kv[0])),
                tuple(sorted(self.namespaces.items(), key=lambda kv: kv[0])),
                self.known,
            )
        )

    @property
    def emitting_blueprints(self) -> tuple[str, ...]:
        return tuple(sorted(self.entries))

    @property
    def not_instrumented(self) -> tuple[str, ...]:
        """Blueprints the generator saw that declare no counters (CAT-05, FR-9.7.3)."""
        return tuple(name for name in self.known if name not in self.entries)


def parse_catalog(raw: str | bytes) -> Catalog:
    """Parse the generated catalog.

    Malformed input raises (CAT-02's runtime half). Degrading to an empty catalog would turn "the
    generator produced something broken" into "no blueprint emits anything" -- a plausible state
    hiding a fixable fault, which is the failure mode this whole increment is written against.
    """
    try:
        payload: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedCatalog("catalog is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise MalformedCatalog("catalog must be a JSON object")

    version = payload.get("schema_version")
    if version != CATALOG_SCHEMA_VERSION:
        raise MalformedCatalog("catalog schema version is not recognised")

    raw_blueprints = payload.get("blueprints", {})
    if not isinstance(raw_blueprints, dict):
        raise MalformedCatalog("catalog blueprints must be an object")

    entries: dict[str, tuple[DeclaredCounter, ...]] = {}
    namespaces: dict[str, str] = {}
    known: list[str] = []
    for name, entry in raw_blueprints.items():
        if not isinstance(name, str) or not name:
            raise MalformedCatalog("blueprint name must be a non-empty string")
        if not isinstance(entry, dict):
            raise MalformedCatalog("blueprint entry must be an object")
        known.append(name)
        if not entry.get("emits", False):
            # emits: false is a declaration, not an omission (CAT-01). Recorded by absence from
            # `entries`, which is what makes NOT_INSTRUMENTED the natural result downstream.
            continue
        namespace = entry.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            raise MalformedCatalog("an emitting blueprint must declare a namespace")
        counters = entry.get("counters", [])
        if not isinstance(counters, list) or not counters:
            raise MalformedCatalog("an emitting blueprint must declare counters")
        parsed: list[DeclaredCounter] = []
        for counter in counters:
            if not isinstance(counter, dict):
                raise MalformedCatalog("counter must be an object")
            missing = {"name", "unit", "description"} - set(counter)
            if missing:
                raise MalformedCatalog("counter is missing required fields")
            for value in (counter["name"], counter["unit"], counter["description"]):
                if not isinstance(value, str) or not value:
                    raise MalformedCatalog("counter fields must be non-empty strings")
            parsed.append(
                DeclaredCounter(
                    name=counter["name"],
                    unit=counter["unit"],
                    description=counter["description"],
                )
            )
        entries[name] = tuple(sorted(parsed))
        namespaces[name] = namespace
    return Catalog(entries=entries, namespaces=namespaces, known=tuple(known))


def emits(catalog: Catalog, blueprint: str) -> bool:
    """Whether a blueprint declares that it emits usage counters (CAT-01, CAT-05)."""
    return blueprint in catalog.entries


def declared_counters(catalog: Catalog, blueprint: str) -> tuple[DeclaredCounter, ...]:
    """The closed allowlist for one blueprint (FR-9.5.2, NFR-T5).

    An empty result means read nothing for that blueprint -- never "read everything".
    """
    return catalog.entries.get(blueprint, ())
