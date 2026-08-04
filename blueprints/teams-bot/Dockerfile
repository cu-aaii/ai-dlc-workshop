# Container image for teams-bot's Bot Framework front door, built by the pipeline's ARM
# CodeBuild project (pipeline/codebuild.yml) with CONTAINER_TARGET=teams-bot and
# CONTAINER_CONTEXT=blueprints/teams-bot -- see "Adding a container image build" in
# pipeline/README.md. The build context is THIS directory, so COPY paths are relative to it.
# Keep the named target: CONTAINER_TARGET selects it.
#
# There is no root Dockerfile in this repository (CLAUDE.md). Each component keeps its own
# here, and the Build action's CONTAINER_CONTEXT must agree with where the component lives --
# a stale context fails with a missing-path error that says nothing about the move.

# --- teams-bot: Bot Framework front door -------------------------------------------
# Lambda container contract: the AWS base image provides the runtime interface client, the
# handler lands in ${LAMBDA_TASK_ROOT}, and CMD names it. Built for linux/arm64 to match the
# function's Architectures.
#
# This base image, NOT the uv image builder-mcp uses: requirements.txt deliberately omits
# boto3 because the AWS Lambda Python base image ships it. Switching bases would break that
# assumption silently.
# ⚠️ UNPINNED BASE IMAGE — dated exception to SECURITY-10, expires 2026-08-05.
# See docs/decisions/0001-course-chatbot-base-image-unpinned-for-demo.md -- filename says
# course-chatbot because the decision was accepted under that name, before this blueprint moved.
#
# This tag is MUTABLE: AWS moves it as patches land, so two builds of this commit can differ. The
# deployed artifact is still immutable (the Build stage exports CONTAINER_DIGEST and the deploy pins
# by digest), and dependencies are pinned in requirements.lock -- the base layer is the only floating
# input. Close it with:
#   docker manifest inspect public.ecr.aws/lambda/python:3.13
# then append @sha256:<digest> below. One line, and this comment goes away with it.
FROM public.ecr.aws/lambda/python:3.13 AS teams-bot

# Dependencies first, so a handler edit does not re-resolve the dependency layer.
#
# Installs from requirements.LOCK, not requirements.txt: the lock carries exact pins for the whole
# transitive set, so two builds of this commit install byte-identical dependencies (SECURITY-10).
# requirements.txt declares intent as ranges and is the file a human edits; regenerate the lock from
# it with the uv pip compile line in the lock's own header.
COPY src/requirements.lock ${LAMBDA_TASK_ROOT}/requirements.lock
RUN python -m pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.lock

COPY src/handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY src/botframework.py ${LAMBDA_TASK_ROOT}/botframework.py

CMD ["handler.handler"]
