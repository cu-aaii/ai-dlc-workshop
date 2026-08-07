"""Load the generated counter catalog from the installed package (C-14, CAT-04).

The parser is pure and lives in `dashboard.core.catalog`; **this** module does the filesystem read,
which is why it sits in U-02. The core boundary grep would reject a file read under `core/`, and
rightly: the catalog is data the deployment supplies, not domain logic.

The catalog is a generated, committed file baked into the container image. `tools/check` regenerates
it and fails on drift, so it cannot silently disagree with the manifests it came from.
"""

from __future__ import annotations

from importlib import resources

from dashboard.core import Catalog, parse_catalog

CATALOG_RESOURCE = "telemetry_catalog.json"


def load_catalog() -> Catalog:
    """Read and parse the baked catalog.

    A missing catalog is a packaging fault, not a runtime state, so it propagates rather than
    degrading to "nobody emits" -- which would look exactly like the ordinary not-instrumented case.
    """
    raw = (resources.files("dashboard") / CATALOG_RESOURCE).read_bytes()
    return parse_catalog(raw)
