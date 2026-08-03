"""Verify the deployed AgentCore runtime end to end: OAuth token -> MCP handshake ->
list tools -> live blueprint_search call. The demo-day proof, runnable any time.

    uv run python deploy/verify.py --stack aidlc-main-builder-mcp --region us-east-1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.parse

import boto3
import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def stack_outputs(stack: str, region: str) -> dict[str, str]:
    cfn = boto3.client("cloudformation", region_name=region)
    outputs = cfn.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def client_secret(user_pool_id: str, client_id: str, region: str) -> str:
    idp = boto3.client("cognito-idp", region_name=region)
    described = idp.describe_user_pool_client(UserPoolId=user_pool_id, ClientId=client_id)
    return described["UserPoolClient"]["ClientSecret"]


def bearer_token(token_endpoint: str, client_id: str, secret: str) -> str:
    response = httpx.post(
        token_endpoint,
        auth=(client_id, secret),
        data={"grant_type": "client_credentials", "scope": "cornell-builder/invoke"},
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
    headers = {"Authorization": f"Bearer {token}"}
    async with streamable_http_client(url, headers=headers) as (read, write):
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
    missing = {"TokenEndpoint", "ClientId", "UserPoolId", "RuntimeArn"} - set(outputs)
    if missing:
        print(f"stack {args.stack} is missing outputs {sorted(missing)} -- "
              "has phase 3 of deploy.ps1 run?", file=sys.stderr)
        return 1

    secret = client_secret(outputs["UserPoolId"], outputs["ClientId"], args.region)
    token = bearer_token(outputs["TokenEndpoint"], outputs["ClientId"], secret)
    print("OAUTH OK: client-credentials token obtained")
    url = mcp_url(outputs["RuntimeArn"], args.region)
    print("ENDPOINT:", url)
    asyncio.run(exercise(url, token))
    print("VERIFIED: the Cornell Builder is live on AgentCore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
