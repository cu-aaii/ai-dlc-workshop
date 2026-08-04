"""Read-mostly AWS operations for status, health, and restart.

Deliberately narrow: nothing here can create, update, or delete a blueprint stack -- the
pipeline's CloudFormation actions do that on merge, and only on merge (D4). The one write
this module performs is telling CodePipeline to run again at the version already on the
tracked branch (deployment_restart, Q4-A), which cannot change what is deployed.

Every function degrades to a {"error": ...} narrative instead of raising, so a demo
without AWS credentials shows a clear message rather than a stack trace (NFR7).
"""

from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import Settings
from .validation import safe_error

logger = logging.getLogger(__name__)

REQUIRED_TAGS = (
    "cornell:owner",
    "cornell:blueprint",
    "cornell:blueprint-version",
    "cornell:deployment-id",
)

HEALTHY_STACK_STATUSES = {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"}


def _client(settings: Settings, service: str):
    return boto3.client(service, region_name=settings.aws_region)


def _friendly(error: Exception, doing: str) -> dict[str, Any]:
    # SECURITY-09: the caller gets class + redacted one-liner; the detail goes to the
    # server-side log where the platform team can read it.
    logger.debug("AWS call failed while %s", doing, exc_info=True)
    return safe_error(error, f"AWS call while {doing}")


def stack_status(settings: Settings, stack_name: str) -> dict[str, Any]:
    try:
        cfn = _client(settings, "cloudformation")
        stacks = cfn.describe_stacks(StackName=stack_name)["Stacks"]
        stack = stacks[0]
        result: dict[str, Any] = {
            "stack": stack_name,
            "status": stack["StackStatus"],
            "healthy": stack["StackStatus"] in HEALTHY_STACK_STATUSES,
            "last_updated": str(stack.get("LastUpdatedTime") or stack.get("CreationTime")),
            "outputs": {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])},
        }
        if not result["healthy"]:
            events = cfn.describe_stack_events(StackName=stack_name)["StackEvents"][:10]
            result["recent_failures"] = [
                {
                    "resource": e["LogicalResourceId"],
                    "status": e["ResourceStatus"],
                    "reason": e.get("ResourceStatusReason", ""),
                }
                for e in events
                if "FAILED" in e["ResourceStatus"]
            ]
        return result
    except ClientError as error:
        if "does not exist" in str(error):
            return {
                "stack": stack_name,
                "status": "NOT_FOUND",
                "healthy": False,
                "hint": "The stack has not been deployed yet -- has the registration PR merged?",
            }
        return _friendly(error, f"describing stack {stack_name}")
    except BotoCoreError as error:
        return _friendly(error, f"describing stack {stack_name}")


def pipeline_state(settings: Settings) -> dict[str, Any]:
    try:
        cp = _client(settings, "codepipeline")
        state = cp.get_pipeline_state(name=settings.pipeline_name)
        stages = []
        for stage in state.get("stageStates", []):
            latest = stage.get("latestExecution", {})
            stages.append({"stage": stage["stageName"], "status": latest.get("status", "UNKNOWN")})
        return {"pipeline": settings.pipeline_name, "stages": stages}
    except (ClientError, BotoCoreError) as error:
        return _friendly(error, f"reading pipeline {settings.pipeline_name}")


def tagged_resources(settings: Settings, deployment_id: str) -> dict[str, Any]:
    """Inventory view: every resource carrying this cornell:deployment-id tag.

    This is the same query the Track E dashboard runs, so a deployment that shows up here
    is by construction visible to the observability work.
    """
    try:
        tagging = _client(settings, "resourcegroupstaggingapi")
        resources = tagging.get_resources(
            TagFilters=[{"Key": "cornell:deployment-id", "Values": [deployment_id]}]
        )["ResourceTagMappingList"]
        inventory = []
        for resource in resources:
            tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}
            inventory.append(
                {
                    "arn": resource["ResourceARN"],
                    "missing_required_tags": [t for t in REQUIRED_TAGS if t not in tags],
                }
            )
        return {"deployment_id": deployment_id, "resource_count": len(inventory), "resources": inventory}
    except (ClientError, BotoCoreError) as error:
        return _friendly(error, f"listing resources tagged {deployment_id}")


def restart(settings: Settings, dry_run: bool = True) -> dict[str, Any]:
    """Re-run the pipeline at the version already on the tracked branch (Q4-A).

    Retries the failed stage if one exists, otherwise starts a fresh execution. Never a
    version change -- changing what is deployed takes a PR and a merge.
    """
    state = pipeline_state(settings)
    if "error" in state:
        return state
    failed = [s for s in state["stages"] if s["status"] == "Failed"]
    plan = (
        f"retry failed stage {failed[0]['stage']!r} of pipeline {settings.pipeline_name}"
        if failed
        else f"start a fresh execution of pipeline {settings.pipeline_name} at the current branch head"
    )
    if dry_run:
        return {"dry_run": True, "would": plan, "stages": state["stages"]}
    try:
        cp = _client(settings, "codepipeline")
        if failed:
            full_state = cp.get_pipeline_state(name=settings.pipeline_name)
            stage = next(
                s for s in full_state["stageStates"] if s["stageName"] == failed[0]["stage"]
            )
            execution_id = stage["latestExecution"]["pipelineExecutionId"]
            cp.retry_stage_execution(
                pipelineName=settings.pipeline_name,
                stageName=failed[0]["stage"],
                pipelineExecutionId=execution_id,
                retryMode="FAILED_ACTIONS",
            )
        else:
            cp.start_pipeline_execution(name=settings.pipeline_name)
        return {"did": plan}
    except (ClientError, BotoCoreError) as error:
        return _friendly(error, plan)
