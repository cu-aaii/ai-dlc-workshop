"""Render a deployment spec for a chosen audience (FR7).

One data model, six renderings. The audiences came from the mob on 2026-08-03, in
priority order: coder, narrative, security, transfer, user, offboarding.
"""

from __future__ import annotations

from typing import Any

AUDIENCES = ("coder", "narrative", "security", "transfer", "user", "offboarding")


def render_spec(audience: str, spec: dict[str, Any]) -> str:
    if audience not in AUDIENCES:
        raise ValueError(f"audience must be one of {AUDIENCES}, got {audience!r}")
    blueprint = spec["blueprint"]
    deployment = spec["deployment"]
    header = (
        f"# {deployment['name']} — {audience} spec\n\n"
        f"Deployment of blueprint **{blueprint['name']}** v{blueprint['version']} "
        f"({blueprint['maturity']}), owned by `{deployment['owner']}`.\n\n"
    )
    sections = {
        "coder": _coder,
        "narrative": _narrative,
        "security": _security,
        "transfer": _transfer,
        "user": _user,
        "offboarding": _offboarding,
    }
    return header + sections[audience](spec)


def _kv(mapping: dict[str, Any]) -> str:
    return "\n".join(f"- **{key}**: `{value}`" for key, value in mapping.items()) or "- (none)"


def _coder(spec: dict[str, Any]) -> str:
    b, d = spec["blueprint"], spec["deployment"]
    return (
        "## For validation by another developer\n\n"
        f"- CloudFormation template: `{b['template']}` (referenced at pinned version "
        f"v{b['version']}, never copied)\n"
        f"- Stack: `{d['stack']}` in us-east-1, deployed by pipeline `{d['pipeline']}` on merge\n"
        f"- Deployment repo: {d.get('repo', '(pending)')}\n\n"
        "### Parameters\n" + _kv(d["parameters"]) + "\n\n"
        "### Manifest inputs contract\n" + _kv({k: v.get("type", "?") for k, v in b["inputs"].items()}) + "\n\n"
        "### Live status\n" + _kv(spec.get("status", {"status": "not fetched"}))
    )


def _narrative(spec: dict[str, Any]) -> str:
    b, d = spec["blueprint"], spec["deployment"]
    return (
        "## What this system does, in plain language\n\n"
        f"{b['summary']}\n\n"
        f"It was created by asking the Cornell Builder for it; nobody wrote cloud "
        f"configuration by hand. The running system is called `{d['name']}` and belongs to "
        f"`{d['owner']}`. It was built from a governed, reusable blueprint "
        f"(**{b['name']}**, version {b['version']}) maintained by {b['maintainer']}.\n\n"
        "Every change to it goes through a reviewed pull request — that review is the "
        "governance gate. When the platform improves the blueprint, this deployment "
        "receives the improvement as a proposed update to accept or decline.\n\n"
        f"Estimated baseline cost: ${b.get('cost', {}).get('baseline_monthly_usd', '?')}/month."
    )


def _security(spec: dict[str, Any]) -> str:
    b, d = spec["blueprint"], spec["deployment"]
    return (
        "## Security & authentication review sheet\n\n"
        f"- Data classification permitted by this blueprint: {b.get('data_classification', [])}\n"
        f"- Credential boundary: the builder holds no git or AWS credential; a platform-held "
        "credential (GitHub App target state) performs all writes\n"
        "- Deploy trigger: merge to the tracked branch only; branch protection enforces one "
        "human approval; there is no out-of-band deploy path\n"
        f"- Tagging: all resources must carry cornell:owner / cornell:blueprint / "
        f"cornell:blueprint-version / cornell:deployment-id (deployment id `{d['stack']}`)\n"
        f"- Stateful resources declared by the blueprint: {b.get('state', []) or 'none (stateless)'}\n"
        f"- Secrets: none in the repo; runtime credentials come from AWS Secrets Manager\n\n"
        "### Live tag audit\n" + _kv(spec.get("tag_audit", {"audit": "not fetched"}))
    )


def _transfer(spec: dict[str, Any]) -> str:
    b, d = spec["blueprint"], spec["deployment"]
    return (
        "## Rebuilding this elsewhere\n\n"
        f"1. Obtain the blueprint source: `{b['template']}` at v{b['version']} from the "
        "catalog repo.\n"
        f"2. Deploy the CloudFormation template with these parameters:\n\n" + _kv(d["parameters"]) + "\n\n"
        "3. The template is self-contained IaC — any AWS account can run it, minus the "
        "Cornell pipeline and tagging conventions, which you may keep or strip.\n"
        f"4. Recover any stateful data per the blueprint's state contract: "
        f"{b.get('state', []) or 'nothing to migrate (stateless)'}.\n"
    )


def _user(spec: dict[str, Any]) -> str:
    d = spec["deployment"]
    status = spec.get("status", {})
    outputs = status.get("outputs", {})
    return (
        "## Using this deployment as-is\n\n"
        f"Owner: `{d['owner']}` — contact them for access.\n\n"
        "### Endpoints and outputs\n" + _kv(outputs or {"outputs": "not fetched or none"}) + "\n\n"
        "To request changes, ask the owner; changes arrive via reviewed pull requests, "
        "typically within the review SLA."
    )


def _offboarding(spec: dict[str, Any]) -> str:
    return (
        "## Off-boarding package (leaving Cornell)\n\n"
        "This combines the transfer spec with data export. Steps:\n\n"
        "1. Follow the transfer spec to stand up the infrastructure elsewhere.\n"
        "2. Export authoritative data (see the blueprint's `state:` contract) — buckets "
        "sync out with standard S3 tooling; databases restore from the final snapshot.\n"
        "3. Ask the platform team to deregister the deployment (registry entry + pipeline "
        "action removal PR) once the copy is verified.\n\n"
        + _transfer(spec)
    )
