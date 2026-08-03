"""Verify the deployed AgentCore runtime end to end: Entra ID OAuth token -> MCP
handshake -> list tools -> live blueprint_search call. The demo-day proof, runnable any
time.

    uv run python deploy/verify.py --stack aidlc-main-builder-mcp --region us-east-1

The Entra client secret comes from the BUILDER_MCP_ENTRA_CLIENT_SECRET env var, falling
back to the Secrets Manager secret aidlc/main/builder-mcp/entra-client-secret.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.parse

import boto3
import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ENTRA_SECRET_ENV = "BUILDER_MCP_ENTRA_CLIENT_SECRET"
ENTRA_SECRET_NAME = "aidlc/main/builder-mcp/entra-client-secret"


def stack_outputs(stack: str, region: str) -> dict[str, str]:
    cfn = boto3.client("cloudformation", region_name=region)
    outputs = cfn.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def entra_client_secret(region: str) -> str:
    """Entra client secret: env var first, Secrets Manager fallback."""
    from_env = os.environ.get(ENTRA_SECRET_ENV)
    if from_env:
        return from_env
    try:
        sm = boto3.client("secretsmanager", region_name=region)
        return sm.get_secret_value(SecretId=ENTRA_SECRET_NAME)["SecretString"]
    except Exception as exc:  # noqa: BLE001 - any failure gets the same friendly hint
        raise SystemExit(
            f"no Entra client secret: set {ENTRA_SECRET_ENV} or create the Secrets "
            f"Manager secret {ENTRA_SECRET_NAME!r} (see deploy/HANDOFF.md pre-flight). "
            f"Secrets Manager lookup failed with: {exc}"
        ) from exc


def bearer_token(token_endpoint: str, client_id: str, secret: str) -> str:
    """Entra ID client-credentials grant. The scope is the app registration's own
    Application ID URI + /.default, which yields a token whose aud the runtime's JWT
    authorizer accepts (api://<client-id>)."""
    response = httpx.post(
        token_endpoint,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": f"api://{client_id}/.default",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def mcp_url(runtime_arn: str, region: str) -> str:
    encoded = urllib.parse.quote(runtime_arn, safe="")
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com"
        f"/runtimes/{encoded}/invocations?qualifier=DEFAULT"
    )


EXPECTED_TOOL_COUNT = 8  # SPEC C3: blueprint_search, deployment_create/read/update/
                         # health/restart/delete, spec_export


async def exercise(url: str, token: str) -> None:
    # streamable_http_client takes no headers kwarg in the pinned SDK; auth rides on the
    # underlying httpx client instead (same pattern as validate_endpoints.py).
    from mcp.client.streamable_http import create_mcp_http_client

    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    async with streamable_http_client(url, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            print(f"TOOLS ({len(names)}):", ", ".join(names))
            if len(names) != EXPECTED_TOOL_COUNT:
                raise SystemExit(
                    f"expected {EXPECTED_TOOL_COUNT} tools (SPEC C3), got {len(names)} "
                    "-- is the deployed image current?"
                )
            result = await session.call_tool(
                "blueprint_search", {"query": "prove the deploy path"}
            )
            payload = json.loads(result.content[0].text)
            top = payload["results"][0]
            print(f"LIVE CALL OK: blueprint_search -> {top['name']} (score {top['match_score']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", default="aidlc-main-builder-mcp")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    outputs = stack_outputs(args.stack, args.region)
    missing = {"EntraTokenEndpoint", "EntraClientId", "RuntimeArn"} - set(outputs)
    if missing:
        print(f"stack {args.stack} is missing outputs {sorted(missing)} -- "
              "has the pipeline deployed the Entra-authorizer template?", file=sys.stderr)
        return 1

    secret = entra_client_secret(args.region)
    token = bearer_token(outputs["EntraTokenEndpoint"], outputs["EntraClientId"], secret)
    print("OAUTH OK: Entra client-credentials token obtained")
    url = mcp_url(outputs["RuntimeArn"], args.region)
    print("ENDPOINT:", url)
    asyncio.run(exercise(url, token))
    print("VERIFIED: the Cornell Builder is live on AgentCore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
